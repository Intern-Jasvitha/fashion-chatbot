"""SQL validation and policy guardrails using sqlglot - CUSTOMER CHATBOT SAFETY LAYER."""

import logging
import re
from typing import Optional

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = {
    "DELETE", "UPDATE", "INSERT", "DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE",
}

MAX_LIMIT = 50
FORBIDDEN_TABLE_PREFIXES = ("finance", "hr", "admin", "analytics", "knowledge", "golden", "canary")

CUSTOMER_POLICY_MESSAGE = (
    "I can only share your own account information (your profile, orders, and purchases). "
    "I can't provide company-wide metrics or other customers' data."
)


class SqlValidationError(Exception):
    """Raised when SQL fails validation or security checks."""
    pass


# ---------------------------------------------------------------------------
# SQL structural validation
# ---------------------------------------------------------------------------

def validate_and_prepare(sql: str) -> str:
    """Validate SQL and return a safe SELECT query with LIMIT 50.

    - Rejects comments, multiple statements, non-SELECT statements
    - Applies hard LIMIT 50
    - Uses sqlglot for syntax validation
    """
    sql = (sql or "").strip()
    if not sql:
        raise SqlValidationError("Empty query.")

    # Reject comments (common injection/obfuscation vector)
    if "--" in sql or "/*" in sql or "*/" in sql:
        raise SqlValidationError("SQL comments are not allowed.")

    statements = sqlglot.parse(sql, dialect="postgres")
    if not statements:
        raise SqlValidationError("Could not parse SQL.")
    if len(statements) > 1:
        raise SqlValidationError("Only one SELECT statement is allowed.")

    stmt = statements[0]

    if not isinstance(stmt, exp.Select):
        raise SqlValidationError("Only SELECT queries are allowed.")

    # Secondary check for dangerous keywords anywhere
    sql_upper = sql.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", sql_upper):
            raise SqlValidationError(f"Statement type '{kw}' is not allowed.")

    result_sql = stmt.sql(dialect="postgres")
    return _enforce_limit_string(result_sql, MAX_LIMIT)


# ---------------------------------------------------------------------------
# Customer / user scope enforcement (called after inject_mandatory_scope)
# ---------------------------------------------------------------------------
def enforce_customer_scope(
    sql: str,
    customer_id: Optional[int],
    user_id: Optional[int] = None,
) -> str:
    """Final safety net - blocks invalid joins/filters that LLM still generates."""
    try:
        stmt = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as e:
        raise SqlValidationError("Could not parse SQL for customer scope check.") from e

    # Block dangerous or useless filters that LLM still adds
    for eq in stmt.find_all(exp.EQ):
        col_name = getattr(eq.this, 'name', '').lower() if hasattr(eq.this, 'name') else ''
        if col_name in ("ticket_id", "product_id", "numseq", "ccexpdate"):
            raise SqlValidationError(f"Invalid filter on {col_name}. Only customer_id is allowed for scoping.")

    alias_map = _table_aliases(stmt)
    tables = set(alias_map.keys())

    if "ticket_item" in tables and "ticket" not in tables:
        raise SqlValidationError("Queries using order items must join ticket and filter by customer_id.")

    errors: list[str] = []

    # BLOCK INVALID ticket_id filters (only in WHERE clause, not in JOINs)
    where_clause = stmt.find(exp.Where)
    if where_clause:
        for eq in where_clause.find_all(exp.EQ):
            for side in (eq.this, eq.expression):
                if isinstance(side, exp.Column) and side.name.lower() == "ticket_id":
                    raise SqlValidationError("Invalid filter: ticket_id cannot be used directly. Use customer_id instead.")

    # Standard customer scoping
    if "ticket" in tables:
        if customer_id is None:
            raise SqlValidationError("Missing customer context for ticket query.")
        try:
            _assert_expected_filter(
                stmt=stmt,
                expected_value=int(customer_id),
                column_name="customer_id",
                table_aliases=alias_map.get("ticket", {"ticket"}),
                label="ticket.customer_id",
                allow_unqualified=True,
            )
        except SqlValidationError as exc:
            errors.append(str(exc))

    if "customer" in tables:
        if customer_id is None:
            raise SqlValidationError("Missing customer context for customer query.")
        try:
            _assert_expected_filter(
                stmt=stmt,
                expected_value=int(customer_id),
                column_name="id",
                table_aliases=alias_map.get("customer", {"customer"}),
                label="customer.id",
                allow_unqualified=len(tables) == 1,
            )
        except SqlValidationError as exc:
            errors.append(str(exc))

    if errors:
        raise SqlValidationError(" | ".join(errors))

    return sql
# ---------------------------------------------------------------------------
# Final SQL firewall (last line of defense)
# ---------------------------------------------------------------------------

def run_sql_firewall(
    sql: str,
    *,
    customer_id: Optional[int],
    user_id: Optional[int],
) -> str:
    """Final firewall before execution."""
    try:
        stmt = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as e:
        raise SqlValidationError("Could not parse SQL for firewall.") from e

    _reject_forbidden_tables(stmt)
    _reject_broad_cross_user_aggregates(stmt, customer_id=customer_id, user_id=user_id)

    logger.debug("SQL FIREWALL | Passed for customer_id=%s", customer_id)
    return sql


# ---------------------------------------------------------------------------
# Helper: LIMIT enforcement
# ---------------------------------------------------------------------------

def _enforce_limit_string(sql: str, max_limit: int) -> str:
    """Append or cap LIMIT 50 (case-insensitive, handles OFFSET)."""
    sql = sql.strip().rstrip(";")
    match = re.search(
        r"\s+LIMIT\s+(\d+)(?:\s+OFFSET\s+\d+)?\s*$",
        sql,
        re.IGNORECASE,
    )
    if match:
        existing = int(match.group(1))
        if existing <= max_limit:
            return sql
        # Replace only the number
        return re.sub(
            r"(\s+LIMIT\s+)\d+",
            lambda m: m.group(1) + str(max_limit),
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
    return sql + f" LIMIT {max_limit}"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _table_aliases(stmt: exp.Expression) -> dict[str, set[str]]:
    """{table_name_lower → {alias_lower, table_name_lower}}"""
    aliases: dict[str, set[str]] = {}
    for table in stmt.find_all(exp.Table):
        table_name = (table.name or "").lower()
        if not table_name:
            continue
        alias = (table.alias_or_name or table_name).lower()
        aliases.setdefault(table_name, set()).update({table_name, alias})
    return aliases


def _reject_forbidden_tables(stmt: exp.Expression) -> None:
    for table in stmt.find_all(exp.Table):
        name = (table.name or "").lower()
        if any(name.startswith(prefix) for prefix in FORBIDDEN_TABLE_PREFIXES):
            raise SqlValidationError(f"Table '{name}' is not allowed.")


def _reject_broad_cross_user_aggregates(
    stmt: exp.Expression,
    *,
    customer_id: Optional[int],
    user_id: Optional[int],
) -> None:
    """Block aggregates that ignore customer scoping."""
    if not any(True for _ in stmt.find_all(exp.AggFunc)):
        return

    alias_map = _table_aliases(stmt)
    tables = set(alias_map.keys())
    if not (tables & {"ticket", "ticket_item", "customer"}):
        return

    # Reuse the full scope check
    try:
        enforce_customer_scope(stmt.sql(dialect="postgres"), customer_id, user_id)
    except SqlValidationError as exc:
        raise SqlValidationError(
            f"Broad aggregate detected without customer scoping: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Filter assertion helpers (unchanged - already robust)
# ---------------------------------------------------------------------------

def _column_matches(
    expr_node: exp.Expression,
    *,
    column_name: str,
    table_aliases: set[str],
    allow_unqualified: bool,
) -> bool:
    if not isinstance(expr_node, exp.Column):
        return False
    if (expr_node.name or "").lower() != column_name.lower():
        return False
    table_ref = (expr_node.table or "").lower()
    if not table_ref:
        return allow_unqualified
    return table_ref in table_aliases


def _extract_int_literal(expr_node: exp.Expression) -> Optional[int]:
    if isinstance(expr_node, exp.Paren):
        return _extract_int_literal(expr_node.this)
    if isinstance(expr_node, (exp.Cast, exp.TryCast)):
        return _extract_int_literal(expr_node.this)
    if isinstance(expr_node, exp.Neg):
        inner = _extract_int_literal(expr_node.this)
        return -inner if inner is not None else None
    if isinstance(expr_node, exp.Literal):
        try:
            return int(str(expr_node.this))
        except (TypeError, ValueError):
            return None
    return None


def _extract_expected_value_from_eq(
    eq_node: exp.EQ,
    *,
    column_name: str,
    table_aliases: set[str],
    allow_unqualified: bool,
) -> Optional[int]:
    left = eq_node.this
    right = eq_node.expression
    if isinstance(left, exp.Expression) and _column_matches(
        left, column_name=column_name, table_aliases=table_aliases, allow_unqualified=allow_unqualified
    ):
        return _extract_int_literal(right) if isinstance(right, exp.Expression) else None
    if isinstance(right, exp.Expression) and _column_matches(
        right, column_name=column_name, table_aliases=table_aliases, allow_unqualified=allow_unqualified
    ):
        return _extract_int_literal(left) if isinstance(left, exp.Expression) else None
    return None


def _extract_expected_values_from_in(
    in_node: exp.In,
    *,
    column_name: str,
    table_aliases: set[str],
    allow_unqualified: bool,
) -> Optional[list[int]]:
    left = in_node.this
    if not isinstance(left, exp.Expression):
        return None
    if not _column_matches(
        left, column_name=column_name, table_aliases=table_aliases, allow_unqualified=allow_unqualified
    ):
        return None
    values: list[int] = []
    for candidate in in_node.expressions:
        parsed = _extract_int_literal(candidate)
        if parsed is None:
            return None
        values.append(parsed)
    return values if values else None


def _assert_expected_filter(
    *,
    stmt: exp.Expression,
    expected_value: int,
    column_name: str,
    table_aliases: set[str],
    label: str,
    allow_unqualified: bool,
) -> None:
    """Walk AST and ensure column = expected_value exists."""
    found_expected = False

    for eq_node in stmt.find_all(exp.EQ):
        found = _extract_expected_value_from_eq(
            eq_node,
            column_name=column_name,
            table_aliases=table_aliases,
            allow_unqualified=allow_unqualified,
        )
        if found is None:
            continue
        if found != expected_value:
            raise SqlValidationError(f"Query must be scoped to {label} = {expected_value}.")
        found_expected = True

    for in_node in stmt.find_all(exp.In):
        values = _extract_expected_values_from_in(
            in_node,
            column_name=column_name,
            table_aliases=table_aliases,
            allow_unqualified=allow_unqualified,
        )
        if values is None:
            continue
        if any(v != expected_value for v in values):
            raise SqlValidationError(f"Query must be scoped to {label} = {expected_value}.")
        found_expected = True

    if not found_expected:
        raise SqlValidationError(f"Query must include a filter: {label} = {expected_value}.")