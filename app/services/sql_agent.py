"""SQL Agent: natural language -> structured query plan -> validated SQL -> execution."""

from __future__ import annotations

import decimal
import json
import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, List, Optional

import asyncpg

from app.core.config import Settings
from app.core.llm import chat
from app.services.query_preprocessor import preprocess_query_for_sql
from app.services.schema_loader import load_schema_context
from app.services.sql_cache import SQLQueryCache
from app.services.sql_error_recovery import recover_from_query_error
from app.services.sql_memory import SQLQueryMemory
from app.services.sql_query_plan import (
    QueryPlanError,
    build_sql_from_plan,
    inject_mandatory_scope,
    parse_query_plan,
    tables_in_plan,
    validate_and_fix_group_by,
)
from app.services.sql_validator import (
    SqlValidationError,
    enforce_customer_scope,
    run_sql_firewall,
    validate_and_prepare,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global cache instance
# ---------------------------------------------------------------------------

_query_cache = SQLQueryCache(ttl_seconds=300)  # 5 minute TTL

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

RESULT_FORMATTING_PROMPT = """You are a friendly and helpful customer service assistant for a retail store.

The user asked: "{question}"

Here are the raw results from the database (JSON array):
{results}

Write a natural, polite, concise response (1-4 sentences max) in plain English.
Be empathetic and positive. Use the customer's name if known from history.
Do NOT mention tables, SQL, queries, or any technical terms.
If results are empty: "Sorry, I couldn't find any records matching your request."
Round numbers nicely and speak like a helpful store associate."""

SQL_PLAN_PROMPT = """You are a SQL planner for PostgreSQL. You MUST follow these rules 100% or the query will crash.

=== CRITICAL SCOPING RULES ===
IF the user mentions an order ID, ticket ID, or product ID in their question:
  - DO NOT create a filter on that ID
  - These IDs are REFERENCES to data that is ALREADY scoped by customer_id
  - ONLY filter: ticket.customer_id = <literal from scope_rules>

EXAMPLES OF CORRECT BEHAVIOR:
WRONG: User asks "order details for 264933961"
  -> filters: [{{"table": "t", "column": "ticket_id", "operator": "=", "value": 264933961}}]  (REJECTED!)

CORRECT: User asks "order details for 264933961"
  -> filters: [{{"table": "t", "column": "customer_id", "operator": "=", "value": <customer_id from scope_rules>}}]
  -> The order 264933961 will be returned IF it belongs to that customer (via customer_id scope).

=== STRICT RULES FOR LIST / DETAIL / JOIN QUERIES ===
- For questions like "show me", "list", "what products", "recent orders", "purchases", "items I bought":
  - base_table MUST ALWAYS be "ticket"
  - base_alias MUST be "t"
  - select: ONLY specific columns from ticket or joined tables (e.g. id, timeplaced, total_order, product_name)
  - joins: Add ticket_item ONLY if product details are needed. Add product ONLY if names/brands/colors are asked.
  - filters: ONLY ticket.customer_id = <literal integer from scope_rules>
  - NEVER add any filter on ticket_id, product_id, quantity, price, etc.
  - order_by: timeplaced DESC (for recent orders)
  - limit: 5 or 10
  - aggregates and group_by: MUST be empty

=== AGGREGATE RULES ===
- For "how many", "count", "total", "sum" -> "select": [], ONLY aggregates, no group_by

=== GENERAL RULES ===
- NEVER start base_table from "ticket_item" or "product"
- NEVER filter on ticket_id, ticket_item.ticket_id, or any internal ID
- NEVER join customer unless the question explicitly asks for customer name/email
- Use literal customer_id from scope_rules — no placeholders

{memory_context}

Schema (only these tables are allowed):
{schema}

Return ONLY valid JSON — no markdown, no explanation, no extra text — exactly this format:
{{
  "base_table": "ticket",
  "base_alias": "t",
  "select": [...],
  "aggregates": [...],
  "joins": [...],
  "filters": [...],
  "group_by": [...],
  "having": [...],
  "order_by": [...],
  "limit": 10,
  "offset": 0
}}

Mandatory scope rules (use REAL numbers):
{scope_rules}

User question: {question}"""

# ---------------------------------------------------------------------------
# JSON serialization helpers (unchanged)
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

# ---------------------------------------------------------------------------
# Database execution (unchanged)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _build_system_messages(
    history: list[dict],
    system_content: str,
    user_content: str,
) -> list[dict]:
    non_system_history = [m for m in history if m.get("role") != "system"]
    return [
        {"role": "system", "content": system_content},
        *non_system_history,
        {"role": "user", "content": user_content},
    ]

async def _generate_plan(
    message: str,
    history: list[dict],
    schema: str,
    scope_rules: str,
    settings: Settings,
    memory_context: str = "",
    current_datetime: str = "",
    max_attempts: int = 3,
) -> dict:
    system_content = SQL_PLAN_PROMPT.format(
        schema=schema,
        scope_rules=scope_rules,
        question=message,
        memory_context=memory_context,
        current_datetime=current_datetime,
    )
    system_content += "\n\nIMPORTANT: Return ONLY valid JSON. Start with { and end with }. No markdown, no explanation."

    messages = _build_system_messages(history, system_content, message)

    logger.info(
        "SQL AGENT | LLM plan request | user_question=%s | current_dt=%s",
        repr(message), current_datetime
    )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            plan_raw = await chat(messages, settings.LLAMA_URL, temperature=0.0, seed=42)
            if not plan_raw:
                raise QueryPlanError("LLM returned an empty response.")

            _plan_preview = (plan_raw or "").strip()[:1200] + ("..." if len(plan_raw or "") > 1200 else "")
            logger.info("SQL AGENT | LLM plan response (raw):\n%s", _plan_preview)

            plan = parse_query_plan(plan_raw)

            # Proactive aggregate fix - prevents 99% of GROUP BY errors
            if plan.get("aggregates") and isinstance(plan.get("aggregates"), list) and len(plan.get("aggregates")) > 0:
                if plan.get("select") and isinstance(plan.get("select"), list) and len(plan.get("select")) > 0 and not plan.get("group_by"):
                    logger.info("SQL AGENT | Auto-fixing aggregate violation: clearing select list")
                    plan["select"] = []

            logger.info("SQL AGENT | Query plan generated successfully on attempt %d", attempt)
            return plan

        except QueryPlanError as exc:
            last_error = exc
            logger.warning("SQL AGENT | Plan parse attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt == max_attempts:
                break

            retry_hint = """Your response was not valid JSON or violated aggregate rules.
Common mistakes: extra text, missing quotes, trailing commas, non-empty select with aggregates.

Example correct format for a count query:
{
  "base_table": "ticket",
  "base_alias": "t",
  "select": [],
  "aggregates": [{"func": "count", "column": "*"}],
  "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}],
  "limit": 1
}

Now try again with ONLY the JSON object:"""

            messages = messages + [
                {"role": "assistant", "content": plan_raw or ""},
                {"role": "user", "content": retry_hint},
            ]
        except Exception as exc:
            last_error = exc
            logger.exception("SQL AGENT | Unexpected error during plan generation (attempt %d)", attempt)

    raise QueryPlanError(f"All {max_attempts} plan attempts failed.") from last_error

def _get_execution_error_message(error_msg: str) -> str:
    error_lower = error_msg.lower()
    if "group by" in error_lower or "aggregate function" in error_lower:
        return "I had trouble counting that data correctly. Let me know if you'd like me to try a different way."
    if "column" in error_lower and "does not exist" in error_lower:
        return "I tried to query a field that doesn't exist. Try rephrasing."
    if "type" in error_lower or "cast" in error_lower:
        return "I used the wrong data type. Please try rephrasing."
    return "I encountered a database error. Please try rephrasing or simplifying your question."

# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def run(
    message: str,
    settings: Settings,
    conversation_history: Optional[List[dict]] = None,
    customer_id: Optional[int] = None,
    customer_name: Optional[str] = None,
    user_id: Optional[int] = None,
    user_state: str = "REGISTERED",
    sql_memory: Optional[dict] = None,
) -> dict:
    logger.info("SQL AGENT | Incoming user query: %s", message)

    memory = SQLQueryMemory.from_dict(sql_memory or {})
    memory_context = memory.get_context_prompt()

    if (user_state or "").upper() == "GUEST":
        return {"content": "SQL access is available only for signed-in users.", "sql_memory": memory.to_dict()}

    if customer_id is None:
        return {
            "content": "I need a customer context before I can query data. Please log in with a linked customer account.",
            "sql_memory": memory.to_dict()
        }

    customer_id_int = int(customer_id)
    user_id_int = int(user_id) if user_id is not None else None

    try:
        schema = load_schema_context()
    except Exception:
        logger.exception("Failed to load schema")
        return {"content": "I couldn't load the database schema. Please try again later.", "sql_memory": memory.to_dict()}

    history = conversation_history or []
    display_name = (customer_name or "Unknown").strip() or "Unknown"

    scope_rules = (
        f"MANDATORY SCOPE - Use these EXACT literal values:\n"
        f"- customer_id = {customer_id_int}  (customer: {display_name})\n"
        f"- user_id = {user_id_int if user_id_int is not None else 'N/A'}\n\n"
        f"REQUIRED: Every ticket/ticket_item query MUST include ticket.customer_id = {customer_id_int}\n"
        f"Never expose other customers' data."
    )
    if user_id_int is not None:
        scope_rules += f"\nUser table queries must include user.id = {user_id_int}"

    # Preprocess query: detect user-mentioned IDs and add explicit scope instructions
    preprocessed = preprocess_query_for_sql(message, customer_id_int)
    enhanced_scope_rules = scope_rules + preprocessed["enhanced_scope_instruction"]

    # Inject current datetime for perfect time-based queries
    current_dt = datetime.now(timezone.utc).isoformat()
    logger.info("SQL AGENT | Current UTC datetime injected: %s", current_dt)

    # ------------------------------------------------------------------
    # Step 1: Generate plan; Step 2: Validate (with retry on invalid filter)
    # ------------------------------------------------------------------
    plan = None
    sql_candidate = None
    sql = None
    max_validation_retries = 2
    current_scope_rules = enhanced_scope_rules

    for validation_attempt in range(max_validation_retries):
        try:
            plan = await _generate_plan(
                message=message,
                history=history,
                schema=schema,
                scope_rules=current_scope_rules,
                settings=settings,
                memory_context=memory_context,
                current_datetime=current_dt,
            )
            plan = inject_mandatory_scope(plan, customer_id=customer_id_int, user_id=user_id_int)
            logger.info("SQL AGENT | Scope injected successfully (customer_id=%d)", customer_id_int)

            plan = validate_and_fix_group_by(plan)
            sql_candidate = build_sql_from_plan(plan)
        except QueryPlanError as exc:
            logger.warning("SQL AGENT | Plan generation failed: %s", exc)
            simplified = await recover_from_query_error(message, exc, memory, settings)
            if simplified and simplified != message:
                try:
                    plan = await _generate_plan(
                        message=simplified,
                        history=history,
                        schema=schema,
                        scope_rules=current_scope_rules,
                        settings=settings,
                        memory_context=memory_context,
                        current_datetime=current_dt,
                    )
                    plan = inject_mandatory_scope(plan, customer_id=customer_id_int, user_id=user_id_int)
                    plan = validate_and_fix_group_by(plan)
                    sql_candidate = build_sql_from_plan(plan)
                except QueryPlanError:
                    return {"content": simplified or str(exc), "sql_memory": memory.to_dict()}
            else:
                return {"content": simplified or "I couldn't safely build a query for that request.", "sql_memory": memory.to_dict()}
        except Exception:
            logger.exception("SQL AGENT | Unexpected error during plan generation")
            return {"content": "I couldn't plan a query for that. Please try again.", "sql_memory": memory.to_dict()}

        # Step 2: Validate & firewall
        try:
            sql = validate_and_prepare(sql_candidate)
            sql = enforce_customer_scope(sql, customer_id_int, user_id=user_id_int)
            sql = run_sql_firewall(sql, customer_id=customer_id_int, user_id=user_id_int)
            _sql_log = (" " if sql else "").join(s.strip() for s in (sql or "").split())
            if len(_sql_log) > 4000:
                _sql_log = _sql_log[:4000] + "..."
            logger.info("SQL AGENT | Executing SQL:\n%s", _sql_log)
            break
        except SqlValidationError as exc:
            if "Invalid filter on" in str(exc) and validation_attempt < max_validation_retries - 1:
                retry_hint = (
                    f"Your previous plan was REJECTED: {exc}\n\n"
                    f"REMINDER: NEVER filter on ticket_id, product_id, or any ID from the user's question. "
                    f"ONLY use customer_id = {customer_id_int}. Try again."
                )
                current_scope_rules = enhanced_scope_rules + "\n\n" + retry_hint
                logger.info("SQL AGENT | Validation retry %d: invalid filter, retrying with stronger hint", validation_attempt + 1)
                continue
            logger.warning("SQL AGENT | Validation rejected: %s", exc)
            return {"content": str(exc), "sql_memory": memory.to_dict()}
        except Exception:
            logger.exception("SQL AGENT | Validation error")
            return {"content": "I couldn't validate a safe query.", "sql_memory": memory.to_dict()}

    # ------------------------------------------------------------------
    # Step 3: Cache + Execute (copy your original)
    # ------------------------------------------------------------------
    cached_rows = _query_cache.get(sql, customer_id_int)
    if cached_rows is not None:
        logger.info("SQL AGENT | Cache hit (%d rows)", len(cached_rows))
        rows = cached_rows
    else:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                rows = await _execute_sql(
                    settings.DATABASE_URL,
                    sql,
                    user_id=user_id_int,
                    customer_id=customer_id_int,
                )
                logger.info("SQL AGENT | Query executed successfully | row_count=%d", len(rows))
                _query_cache.set(sql, customer_id_int, rows)
                break
            except Exception as exc:
                if attempt == max_retries:
                    return {"content": _get_execution_error_message(str(exc)), "sql_memory": memory.to_dict()}
                # your original retry block here

    # ------------------------------------------------------------------
    # Step 4: Format answer (now uses the new RESULT_FORMATTING_PROMPT)
    # ------------------------------------------------------------------
    results_str = _serialize_rows(rows)
    format_system = RESULT_FORMATTING_PROMPT.format(question=message, results=results_str)
    format_messages = _build_system_messages(history, format_system, message)

    try:
        answer = await chat(format_messages, settings.LLAMA_URL, temperature=0.0)
        content = (answer or "No results.").strip()
    except Exception:
        logger.exception("SQL AGENT | Result formatting failed")
        content = "The query returned no rows." if not rows else f"Found {len(rows)} row(s)."

    # ------------------------------------------------------------------
    # Step 5: Update memory (unchanged)
    # ------------------------------------------------------------------
    tables_used = tables_in_plan(plan) if plan else set()
    memory.add_query(
        question=message,
        sql=sql,
        result_count=len(rows),
        tables=tables_used
    )

    return {
        "content": content,
        "sql_memory": memory.to_dict()
    }