"""Simple SQL Agent: LLM generates SQL directly, no JSON plan nonsense."""

from __future__ import annotations

import decimal
import json
import logging
import re
import time as time_module
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Optional

import asyncpg
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.llm import chat
from app.services.schema_rag import retrieve_schema_context, SchemaRAGError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SQL_GENERATION_PROMPT = """You are a PostgreSQL expert for a retail database. Generate a SELECT query based on the user's question.

=== CRITICAL RULES ===
1. ONLY generate SELECT queries (no INSERT, UPDATE, DELETE, DROP, etc.)
2. ALWAYS filter by customer_id = {customer_id} in the WHERE clause
3. Use these table aliases:
   - ticket AS t (base table for orders)
   - ticket_item AS ti (for product details in orders)
   - product AS p (for product info; has product_name, brand_id, type_id — no brand_name, no category_id)
   - brand AS b (for brand names; has brand_name — join when user asks for brand)
   - type AS ty (product type; has type_name, category_id — join p.type_id = ty.id for category)
   - category AS cat (has category_name — join via type: ty.category_id = cat.id)
   - customer AS c (only if explicitly asked; has firstname, lastname — no customer_name)

=== SCHEMA ===
{schema_context}

=== EXAMPLES ===

User: "Show me my recent orders"
SQL: SELECT t.id, t.timeplaced, t.total_order FROM ticket t WHERE t.customer_id = {customer_id} ORDER BY t.timeplaced DESC LIMIT 10;

User: "What's my total spending?"
SQL: SELECT SUM(t.total_order) as total_spent FROM ticket t WHERE t.customer_id = {customer_id};

User: "What products did I buy?"
SQL: SELECT DISTINCT p.product_name FROM ticket t JOIN ticket_item ti ON t.id = ti.ticket_id JOIN product p ON ti.product_id = p.id WHERE t.customer_id = {customer_id} ORDER BY p.product_name LIMIT 20;

User: "What brands have I bought from?" / "Show my orders with brand names"
SQL: SELECT DISTINCT b.brand_name FROM ticket t JOIN ticket_item ti ON t.id = ti.ticket_id JOIN product p ON ti.product_id = p.id JOIN brand b ON p.brand_id = b.id WHERE t.customer_id = {customer_id} ORDER BY b.brand_name;

User: "Show my orders with product category"
SQL: SELECT t.id, t.timeplaced, p.product_name, cat.category_name, ti.quantity FROM ticket t JOIN ticket_item ti ON t.id = ti.ticket_id JOIN product p ON ti.product_id = p.id JOIN type ty ON p.type_id = ty.id JOIN category cat ON ty.category_id = cat.id WHERE t.customer_id = {customer_id} ORDER BY t.timeplaced DESC LIMIT 10;

=== IMPORTANT ===
- Return ONLY the SQL query, nothing else
- Always end with semicolon
- Use customer_id = {customer_id} (literal value, not placeholder)
- Brand name: use brand table (b.brand_name), never p.brand_name (product has only brand_id)
- Customer name: use c.firstname and c.lastname (e.g. c.firstname || ' ' || c.lastname), never c.customer_name
- Product category: product has type_id only (no category_id); join type ty ON p.type_id = ty.id, then category cat ON ty.category_id = cat.id; use cat.category_name
- Keep it simple and readable

User question: {question}

SQL:"""

RESULT_FORMATTING_PROMPT = """You are a friendly customer service assistant.

The user asked: "{question}"

Database results (JSON):
{results}

Write a natural, helpful response (1-3 sentences). Be concise and friendly.
If no results: "I couldn't find any matching records."
Round numbers nicely. Don't mention SQL or technical terms."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

def _is_safe_select_query(sql: str) -> bool:
    """Validate SQL is a safe SELECT query."""
    sql_normalized = " ".join(sql.strip().split()).upper()
    
    # Must start with SELECT
    if not sql_normalized.startswith("SELECT"):
        return False
    
    # Block dangerous keywords
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    for keyword in dangerous:
        if f" {keyword} " in f" {sql_normalized} ":
            return False
    
    # Must have WHERE clause (to enforce scoping)
    if "WHERE" not in sql_normalized:
        logger.warning("SQL rejected: missing WHERE clause")
        return False
    
    # Must reference customer_id in WHERE
    if "CUSTOMER_ID" not in sql_normalized:
        logger.warning("SQL rejected: missing customer_id filter")
        return False
    
    return True

def _extract_sql(llm_response: str) -> str:
    """Extract SQL from LLM response (handle markdown code blocks)."""
    text = llm_response.strip()
    
    # Remove markdown code blocks
    sql_block_match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if sql_block_match:
        return sql_block_match.group(1).strip()
    
    code_block_match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()
    
    # Remove "SQL:" prefix if present
    if text.upper().startswith("SQL:"):
        text = text[4:].strip()
    
    return text

async def _execute_sql(
    database_url: str,
    sql: str,
    customer_id: int,
    user_id: Optional[int],
) -> list[dict[str, Any]]:
    """Execute SQL with RLS context."""
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

def _build_messages(system_prompt: str, user_message: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

# ---------------------------------------------------------------------------
# Main Agent
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
    Simple SQL Agent: LLM → SQL → Execute → Format
    No complex JSON plans, just direct SQL generation.
    """
    start_time = time_module.perf_counter()
    logger.info(
        "SQL Agent | Starting request | message=%r | customer_id=%s",
        message,
        customer_id,
    )
    
    # Step 1: Get schema context via RAG
    try:
        schema_context = await retrieve_schema_context(
            query=message,
            qdrant=qdrant,
            settings=settings,
            top_k=10,
        )
        logger.info("Simple SQL Agent | Schema retrieved: %d chars", len(schema_context))
    except SchemaRAGError as e:
        logger.exception("Simple SQL Agent | Schema RAG failed: %s", e)
        return {
            "content": "Schema retrieval failed. Please check the sql-agent collection is populated.",
            "sql": None,
            "plan": None,
            "metadata": {"error": str(e), "row_count": 0},
        }
    
    # Step 2: Generate SQL directly from LLM
    max_attempts = 3
    sql = None
    last_error = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Simple SQL Agent | Generate attempt %d/%d", attempt, max_attempts)
            
            prompt = SQL_GENERATION_PROMPT.format(
                schema_context=schema_context,
                customer_id=customer_id,
                question=message,
            )
            messages = _build_messages(prompt, message)
            
            llm_response = await chat(messages, settings.LLAMA_URL, temperature=0.0, seed=42)
            if not llm_response:
                raise ValueError("LLM returned empty response")
            
            sql = _extract_sql(llm_response)
            logger.info("Simple SQL Agent | Generated SQL:\n%s", sql)
            
            # Validate it's a safe SELECT query
            if not _is_safe_select_query(sql):
                raise ValueError("Generated SQL failed safety validation")
            
            logger.info("Simple SQL Agent | SQL passed validation")
            break
            
        except Exception as e:
            last_error = str(e)
            logger.warning("Simple SQL Agent | Attempt %d failed: %s", attempt, e)
            if attempt == max_attempts:
                return {
                    "content": "I couldn't generate a valid SQL query. Please try rephrasing your question.",
                    "sql": None,
                    "plan": None,
                    "metadata": {"error": last_error, "row_count": 0},
                }
    
    # Step 3: Execute SQL
    exec_start = time_module.perf_counter()
    try:
        rows = await _execute_sql(settings.DATABASE_URL, sql, customer_id, user_id)
        execution_time_ms = (time_module.perf_counter() - exec_start) * 1000
        logger.info("Simple SQL Agent | Query executed: %d rows in %.2fms", len(rows), execution_time_ms)
    except Exception as e:
        logger.exception("Simple SQL Agent | Execution failed: %s", e)
        return {
            "content": "Database error occurred. Please try rephrasing your question.",
            "sql": sql,
            "plan": None,
            "metadata": {"error": str(e), "row_count": 0},
        }
    
    # Step 4: Format response
    results_str = _serialize_rows(rows)
    format_prompt = RESULT_FORMATTING_PROMPT.format(question=message, results=results_str)
    format_messages = _build_messages(format_prompt, message)
    
    try:
        content = await chat(format_messages, settings.LLAMA_URL, temperature=0.0)
        content = (content or "No results found.").strip()
    except Exception as e:
        logger.warning("Simple SQL Agent | Formatting failed: %s", e)
        content = "No results found." if not rows else f"Found {len(rows)} result(s)."
    
    total_time_ms = (time_module.perf_counter() - start_time) * 1000
    logger.info("Simple SQL Agent | Complete in %.2fms", total_time_ms)
    
    return {
        "content": content,
        "sql": sql,
        "plan": None,
        "metadata": {
            "row_count": len(rows),
            "execution_time_ms": round(execution_time_ms, 2),
            "total_time_ms": round(total_time_ms, 2),
        },
    }
