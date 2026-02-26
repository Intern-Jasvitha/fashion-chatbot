"""SQL Agent v2: Plan → Generate → Execute & Correct workflow with schema RAG."""

from __future__ import annotations

import decimal
import json
import logging
import time as time_module
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Optional

import asyncpg
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.llm import chat
from app.services.query_preprocessor import preprocess_query_for_sql
from app.services.schema_rag import retrieve_schema_context, SchemaRAGError
from app.services.sql_cache import SQLQueryCache
from app.services.sql_query_plan import (
    QueryPlanError,
    build_sql_from_plan,
    inject_mandatory_scope,
    parse_query_plan,
    validate_and_fix_group_by,
)
from app.services.sql_validator import (
    SqlValidationError,
    enforce_customer_scope,
    run_sql_firewall,
    validate_and_prepare,
)

logger = logging.getLogger(__name__)

_query_cache = SQLQueryCache(ttl_seconds=300)


def _convert_plan_to_dict(plan: Any) -> Optional[dict[str, Any]]:
    """Convert a QueryPlan (or any Pydantic model) to a dict for API response."""
    if plan is None:
        return None
    if hasattr(plan, 'model_dump'):
        return plan.model_dump(exclude_none=True)
    if hasattr(plan, 'dict'):
        return plan.dict(exclude_none=True)
    if isinstance(plan, dict):
        return {k: v for k, v in plan.items() if v is not None}
    return None

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_GENERATION_PROMPT = """You are a SQL planning assistant. Based on the user's question and available schema, create a logical plan in 2-3 sentences describing:
1. What data needs to be retrieved
2. Which tables should be queried
3. What filters/aggregations are needed

User question: {question}

Available schema:
{schema_context}

Respond with ONLY the logical plan, no preamble."""

SQL_GENERATION_PROMPT = """You are a SQL query builder for PostgreSQL. You MUST follow these rules 100% or the query will crash.

=== CRITICAL SCOPING RULES ===
- ALWAYS filter by ticket.customer_id = {customer_id} (use this exact literal).
- NEVER filter on ticket_id, product_id, or any ID from the user's question.
- base_table MUST be "ticket" with base_alias "t" for list/detail/aggregate queries.

=== AGGREGATE RULES ===
- For "how many", "count", "total", "sum" -> "select": [], ONLY aggregates, no group_by.

=== JOIN FORMAT ===
- Each JOIN must have "on" with proper format:
  {{"left_table": "t", "left_column": "id", "right_table": "ti", "right_column": "ticket_id"}}
- Example: To join ticket_item: 
  {{"table": "ticket_item", "alias": "ti", "join_type": "inner", "on": [{{"left_table": "t", "left_column": "id", "right_table": "ti", "right_column": "ticket_id"}}]}}

Schema (only these tables/columns are allowed):
{schema_context}

Return ONLY valid JSON — no markdown, no explanation — exactly this format:
{{
  "base_table": "ticket",
  "base_alias": "t",
  "select": [],
  "aggregates": [{{"func": "sum", "table": "ti", "column": "product_amount", "alias": "total_amount"}}],
  "joins": [{{"table": "ticket_item", "alias": "ti", "join_type": "inner", "on": [{{"left_table": "t", "left_column": "id", "right_table": "ti", "right_column": "ticket_id"}}]}}],
  "filters": [{{"table": "t", "column": "customer_id", "operator": "=", "value": {customer_id}}}],
  "group_by": [],
  "having": [],
  "order_by": [],
  "limit": 50,
  "offset": null
}}

Scope rules: customer_id = {customer_id}, user_id = {user_id}

Logical Plan: {plan}

User question: {question}"""

ERROR_CORRECTION_PROMPT = """Your previous SQL query failed with this error:
{error_message}

Original question: {question}
Failed SQL: {failed_sql}

Schema context:
{schema_context}

CRITICAL: JOIN format must be:
{{"table": "ticket_item", "alias": "ti", "join_type": "inner", "on": [{{"left_table": "t", "left_column": "id", "right_table": "ti", "right_column": "ticket_id"}}]}}

Analyze the error and generate a corrected JSON query plan. Use the same format as before.
Return ONLY the JSON object — no markdown, no explanation."""

RESULT_FORMATTING_PROMPT = """You are a friendly customer service assistant for a retail store.

The user asked: "{question}"

Here are the raw results from the database (JSON array):
{results}

Write a natural, polite, concise response (1-4 sentences max) in plain English.
Do NOT mention tables, SQL, or technical terms. If results are empty: "Sorry, I couldn't find any records matching your request."
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCALAR_TYPES = (str, int, float, bool, type(None))


def _json_default(obj: Any) -> Any:
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _serialize_rows(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, default=_json_default, indent=2)


async def _execute_sql(
    database_url: str,
    sql: str,
    *,
    user_id: Optional[int],
    customer_id: int,
) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.customer_id', $1, true)", str(customer_id))
            await conn.execute(
                "SELECT set_config('app.user_id', $1, true)",
                str(int(user_id)) if user_id is not None else "",
            )
            rows = await conn.fetch(sql)
            return [dict(r) for r in rows]
    finally:
        await conn.close()


def _build_messages(system: str, user_content: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------

async def _generate_logical_plan(
    question: str,
    schema_context: str,
    settings: Settings,
) -> str:
    system = PLAN_GENERATION_PROMPT.format(
        question=question,
        schema_context=schema_context[:8000],
    )
    messages = _build_messages(system, question)
    plan = await chat(messages, settings.LLAMA_URL, temperature=0.0, seed=42)
    return (plan or "").strip()


async def _generate_json_plan(
    question: str,
    logical_plan: str,
    schema_context: str,
    scope_rules: str,
    customer_id: int,
    user_id: Optional[int],
    settings: Settings,
):
    """Returns QueryPlan Pydantic model (not dict)."""
    user_id_str = str(user_id) if user_id is not None else "N/A"
    system = SQL_GENERATION_PROMPT.format(
        schema_context=schema_context[:8000],
        customer_id=customer_id,
        user_id=user_id_str,
        plan=logical_plan,
        question=question,
    )
    messages = _build_messages(system, question)
    raw = await chat(messages, settings.LLAMA_URL, temperature=0.0, seed=42)
    if not raw:
        raise QueryPlanError("LLM returned an empty response.")
    plan = parse_query_plan(raw)
    
    # Proactive aggregate fix (access Pydantic model attributes)
    if plan.aggregates and plan.select and not plan.group_by:
        logger.info("SQL Agent v2 | Auto-fixing: clearing select when aggregates present")
        plan.select = []
    
    return plan


async def _generate_corrected_plan(
    question: str,
    failed_sql: str,
    error_message: str,
    schema_context: str,
    settings: Settings,
):
    """Returns QueryPlan Pydantic model (not dict)."""
    system = ERROR_CORRECTION_PROMPT.format(
        error_message=error_message,
        question=question,
        failed_sql=failed_sql,
        schema_context=schema_context[:6000],
    )
    messages = _build_messages(system, question)
    raw = await chat(messages, settings.LLAMA_URL, temperature=0.0, seed=42)
    if not raw:
        raise QueryPlanError("LLM returned an empty correction.")
    return parse_query_plan(raw)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_sql_agent(
    message: str,
    settings: Settings,
    qdrant: QdrantClient,
    customer_id: int,
    user_id: Optional[int],
    customer_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute Plan → Generate → Execute & Correct workflow.
    Returns {"content": str, "sql": str | None, "plan": dict | None, "metadata": dict}.
    """
    start_time = time_module.perf_counter()
    customer_id_int = int(customer_id)
    user_id_int = int(user_id) if user_id is not None else None
    display_name = (customer_name or "Unknown").strip() or "Unknown"

    scope_rules = (
        f"MANDATORY: customer_id = {customer_id_int} (customer: {display_name}), "
        f"user_id = {user_id_int if user_id_int is not None else 'N/A'}. "
        f"Every ticket query MUST include ticket.customer_id = {customer_id_int}."
    )
    preprocessed = preprocess_query_for_sql(message, customer_id_int)
    scope_rules += preprocessed["enhanced_scope_instruction"]

    # Step 0: Retrieve schema via RAG (no fallback to static schema)
    try:
        logger.info("SQL Agent v2 | Retrieving schema context via RAG for query: %s", message[:100])
        schema_context = await retrieve_schema_context(message, settings, qdrant)
        logger.info("SQL Agent v2 | Schema context retrieved: %d chars", len(schema_context))
    except SchemaRAGError as e:
        logger.error("SQL Agent v2 | Schema RAG failed: %s", e)
        return {
            "content": (
                "Schema retrieval failed. The sql-agent collection may not be populated. "
                "Please run: python scripts/load_sql_schema_embeddings.py"
            ),
            "sql": None,
            "plan": None,
            "metadata": {"error": str(e), "row_count": 0},
        }
    except Exception as e:
        logger.exception("SQL Agent v2 | Unexpected error during schema RAG: %s", e)
        return {
            "content": "Schema retrieval encountered an unexpected error. Please check the logs.",
            "sql": None,
            "plan": None,
            "metadata": {"error": str(e), "row_count": 0},
        }

    # Step 1: Plan
    logger.info("SQL Agent v2 | Starting Step 1: Logical Plan Generation")
    try:
        logical_plan = await _generate_logical_plan(message, schema_context, settings)
        logger.info("SQL Agent v2 | Plan generated: %s", logical_plan[:200])
        if len(logical_plan) > 200:
            logger.info("SQL Agent v2 | Full plan: %s", logical_plan)
    except Exception as e:
        logger.exception("SQL Agent v2 | Plan generation failed: %s", e)
        return {
            "content": "I couldn't create a query plan for that. Please try rephrasing.",
            "sql": None,
            "plan": None,
            "metadata": {"error": str(e), "row_count": 0},
        }

    # Step 2: Generate JSON plan
    logger.info("SQL Agent v2 | Starting Step 2: Generate JSON Query Plan")
    plan = None
    sql = None
    max_correct_attempts = 2
    last_error: Optional[str] = None

    for attempt in range(max_correct_attempts + 1):
        logger.info("SQL Agent v2 | Generate attempt %d/%d", attempt + 1, max_correct_attempts + 1)
        try:
            if attempt == 0:
                logger.info("SQL Agent v2 | Generating initial JSON plan from logical plan")
                plan = await _generate_json_plan(
                    message, logical_plan, schema_context, scope_rules,
                    customer_id_int, user_id_int, settings,
                )
            else:
                logger.info("SQL Agent v2 | Generating corrected plan after error: %s", last_error[:200])
                plan = await _generate_corrected_plan(
                    message, sql or "", last_error or "", schema_context, settings,
                )

            logger.info("SQL Agent v2 | Injecting mandatory scope (customer_id=%d)", customer_id_int)
            plan = inject_mandatory_scope(plan, customer_id=customer_id_int, user_id=user_id_int)
            
            logger.info("SQL Agent v2 | Validating and fixing GROUP BY")
            plan = validate_and_fix_group_by(plan)
            
            logger.info("SQL Agent v2 | Building SQL from plan")
            sql_candidate = build_sql_from_plan(plan)
            logger.info("SQL Agent v2 | SQL candidate: %s", sql_candidate[:500])
            
            logger.info("SQL Agent v2 | Validating SQL syntax")
            sql = validate_and_prepare(sql_candidate)
            
            logger.info("SQL Agent v2 | Enforcing customer scope")
            sql = enforce_customer_scope(sql, customer_id_int, user_id=user_id_int)
            
            logger.info("SQL Agent v2 | Running SQL firewall")
            sql = run_sql_firewall(sql, customer_id=customer_id_int, user_id=user_id_int)
            
            logger.info("SQL Agent v2 | SQL validation passed. Final SQL: %s", sql[:500])
            break
        except (QueryPlanError, SqlValidationError) as e:
            last_error = str(e)
            logger.warning("SQL Agent v2 | Generate/validate attempt %d failed: %s", attempt + 1, e)
            if attempt == max_correct_attempts:
                return {
                    "content": str(e),
                    "sql": None,
                    "plan": _convert_plan_to_dict(plan) if plan else None,
                    "metadata": {"error": last_error, "row_count": 0},
                }
        except Exception as e:
            logger.exception("SQL Agent v2 | Unexpected error: %s", e)
            return {
                "content": "I couldn't build a safe query. Please try again.",
                "sql": None,
                "plan": None,
                "metadata": {"error": str(e), "row_count": 0},
            }

    if not sql or not plan:
        return {
            "content": "I couldn't generate a valid query.",
            "sql": None,
            "plan": None,
            "metadata": {"row_count": 0},
        }

    # Step 3: Execute (with retry on execution error → Correct)
    logger.info("SQL Agent v2 | Starting Step 3: Execute SQL")
    rows: list[dict[str, Any]] = []
    exec_start = time_module.perf_counter()

    for exec_attempt in range(max_correct_attempts + 1):
        logger.info("SQL Agent v2 | Execute attempt %d/%d", exec_attempt + 1, max_correct_attempts + 1)
        try:
            cached = _query_cache.get(sql, customer_id_int)
            if cached is not None:
                rows = cached
                logger.info("SQL Agent v2 | Cache hit (%d rows)", len(rows))
            else:
                logger.info("SQL Agent v2 | Executing SQL against database")
                rows = await _execute_sql(
                    settings.DATABASE_URL,
                    sql,
                    user_id=user_id_int,
                    customer_id=customer_id_int,
                )
                logger.info("SQL Agent v2 | Execution successful, returned %d rows", len(rows))
                _query_cache.set(sql, customer_id_int, rows)
            break
        except Exception as e:
            last_error = str(e)
            logger.warning("SQL Agent v2 | Execution failed (attempt %d): %s", exec_attempt + 1, e)
            if exec_attempt < max_correct_attempts:
                try:
                    plan = await _generate_corrected_plan(
                        message, sql, last_error, schema_context, settings,
                    )
                    plan = inject_mandatory_scope(plan, customer_id=customer_id_int, user_id=user_id_int)
                    plan = validate_and_fix_group_by(plan)
                    sql = build_sql_from_plan(plan)
                    sql = validate_and_prepare(sql)
                    sql = enforce_customer_scope(sql, customer_id_int, user_id=user_id_int)
                    sql = run_sql_firewall(sql, customer_id=customer_id_int, user_id=user_id_int)
                except Exception as retry_e:
                    logger.warning("SQL Agent v2 | Correction failed: %s", retry_e)
                    return {
                        "content": "I encountered a database error. Please try rephrasing.",
                        "sql": sql,
                        "plan": _convert_plan_to_dict(plan),
                        "metadata": {"error": last_error, "row_count": 0},
                    }
            else:
                return {
                    "content": "I encountered a database error. Please try rephrasing or simplifying your question.",
                    "sql": sql,
                    "plan": _convert_plan_to_dict(plan),
                    "metadata": {"error": last_error, "row_count": 0},
                }

    execution_time_ms = (time_module.perf_counter() - exec_start) * 1000
    total_time_ms = (time_module.perf_counter() - start_time) * 1000
    logger.info("SQL Agent v2 | Execution time: %.2fms, Total time: %.2fms", execution_time_ms, total_time_ms)

    # Step 4: Format response
    logger.info("SQL Agent v2 | Starting Step 4: Format Natural Language Response")
    results_str = _serialize_rows(rows)
    logger.info("SQL Agent v2 | Serialized %d rows to JSON (%d chars)", len(rows), len(results_str))
    
    format_system = RESULT_FORMATTING_PROMPT.format(question=message, results=results_str)
    format_messages = _build_messages(format_system, message)
    try:
        logger.info("SQL Agent v2 | Calling LLM for result formatting")
        content = await chat(format_messages, settings.LLAMA_URL, temperature=0.0)
        content = (content or "No results.").strip()
        logger.info("SQL Agent v2 | Formatted response: %s", content[:200])
    except Exception as e:
        logger.warning("SQL Agent v2 | Result formatting failed: %s", e)
        content = "No records found." if not rows else f"Found {len(rows)} row(s)."

    logger.info("SQL Agent v2 | Request complete - returning response with %d rows", len(rows))
    return {
        "content": content,
        "sql": sql,
        "plan": _convert_plan_to_dict(plan),
        "metadata": {
            "row_count": len(rows),
            "execution_time_ms": round(execution_time_ms, 2),
            "total_time_ms": round(total_time_ms, 2),
        },
    }
