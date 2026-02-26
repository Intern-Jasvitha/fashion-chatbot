"""Structured SQL query plan contract and builder - CUSTOMER CHATBOT EDITION."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

import sqlglot
from pydantic import BaseModel, Field, ValidationError, field_validator

MAX_LIMIT = 50
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class QueryPlanError(ValueError):
    """Raised when a query plan is invalid or cannot be built safely."""


# ---------------------------------------------------------------------------
# Identifier safety
# ---------------------------------------------------------------------------

def _safe_ident(value: str) -> str:
    token = (value or "").strip()
    if not _IDENT_RE.match(token):
        raise QueryPlanError(f"Invalid SQL identifier: {value!r}")
    return token


def _ident(token: str) -> str:
    return _safe_ident(token)


# SQL expression patterns the LLM is allowed to emit as raw (unquoted) SQL.
_SQL_EXPR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^(NOW\(\)|CURRENT_TIMESTAMP|CURRENT_DATE|CURRENT_TIME)"
        r"(\s*[\+\-]\s*INTERVAL\s*'.+')?\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^INTERVAL\s*'.+'$", re.IGNORECASE),
    re.compile(r"^DATE_TRUNC\s*\(.*\)$", re.IGNORECASE),
]


def _is_sql_expression(value: str) -> bool:
    return any(p.match(value.strip()) for p in _SQL_EXPR_PATTERNS)


def _coerce_filter_value(value: Any) -> Any:
    """Coerce LLM values (especially string IDs) and block placeholders."""
    if not isinstance(value, str):
        return value

    stripped = value.strip()

    # Block placeholders (LLM should never emit these)
    if re.match(r'^[{]+[^}]+[}]+$', stripped):
        raise QueryPlanError(
            f"Filter value contains unresolved placeholder: {value!r}. "
            f"Use the literal integer from scope_rules."
        )

    if _is_sql_expression(value):
        return value

    if stripped.lstrip("-").isdigit():
        try:
            return int(stripped)
        except ValueError:
            pass
    return value


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if _is_sql_expression(value):
            return value
        return "'" + value.replace("'", "''") + "'"
    raise QueryPlanError(f"Unsupported filter literal type: {type(value).__name__}")


# ---------------------------------------------------------------------------
# Plan models (unchanged)
# ---------------------------------------------------------------------------

class JoinCondition(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str

    @field_validator("left_table", "left_column", "right_table", "right_column")
    @classmethod
    def _v(cls, v: str) -> str:
        return _safe_ident(v)


class SelectField(BaseModel):
    table: str
    column: str
    alias: Optional[str] = None

    @field_validator("table", "column")
    @classmethod
    def _v(cls, v: str) -> str:
        return v if v == "*" else _safe_ident(v)

    @field_validator("alias")
    @classmethod
    def _va(cls, v: Optional[str]) -> Optional[str]:
        return _safe_ident(v) if v else v


class AggregateSpec(BaseModel):
    func: Literal["count", "sum", "avg", "min", "max"]
    table: Optional[str] = None
    column: str = "*"
    alias: Optional[str] = None
    distinct: bool = False

    @field_validator("table")
    @classmethod
    def _vt(cls, v: Optional[str]) -> Optional[str]:
        return _safe_ident(v) if v else v

    @field_validator("column")
    @classmethod
    def _vc(cls, v: str) -> str:
        return v if v == "*" else _safe_ident(v)

    @field_validator("alias")
    @classmethod
    def _va(cls, v: Optional[str]) -> Optional[str]:
        return _safe_ident(v) if v else v


class JoinSpec(BaseModel):
    table: str
    alias: Optional[str] = None
    join_type: Literal["inner", "left", "right", "full"] = "inner"
    on: list[JoinCondition] = Field(default_factory=list)

    @field_validator("table")
    @classmethod
    def _vt(cls, v: str) -> str:
        return _safe_ident(v)

    @field_validator("alias")
    @classmethod
    def _va(cls, v: Optional[str]) -> Optional[str]:
        return _safe_ident(v) if v else v


_FILTER_OPS = Literal[
    "=", "!=", ">", ">=", "<", "<=",
    "in", "not in",
    "like", "ilike",
    "is null", "is not null",
]


class FilterSpec(BaseModel):
    table: str
    column: str
    operator: _FILTER_OPS
    value: Any = None

    @field_validator("table", "column")
    @classmethod
    def _v(cls, v: str) -> str:
        return _safe_ident(v)


class HavingSpec(BaseModel):
    func: Literal["count", "sum", "avg", "min", "max"]
    table: Optional[str] = None
    column: str = "*"
    operator: Literal["=", "!=", ">", ">=", "<", "<="]
    value: Any

    @field_validator("table")
    @classmethod
    def _vt(cls, v: Optional[str]) -> Optional[str]:
        return _safe_ident(v) if v else v

    @field_validator("column")
    @classmethod
    def _vc(cls, v: str) -> str:
        return v if v == "*" else _safe_ident(v)


class GroupByField(BaseModel):
    table: str
    column: str

    @field_validator("table", "column")
    @classmethod
    def _v(cls, v: str) -> str:
        return _safe_ident(v)


class SortSpec(BaseModel):
    table: str
    column: str
    direction: Literal["asc", "desc"] = "asc"

    @field_validator("table", "column")
    @classmethod
    def _v(cls, v: str) -> str:
        return _safe_ident(v)


class QueryPlan(BaseModel):
    base_table: str
    base_alias: Optional[str] = None
    select: list[SelectField] = Field(default_factory=list)
    aggregates: list[AggregateSpec] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    group_by: list[GroupByField] = Field(default_factory=list)
    having: list[HavingSpec] = Field(default_factory=list)
    order_by: list[SortSpec] = Field(default_factory=list)
    limit: Optional[int] = MAX_LIMIT
    offset: Optional[int] = None

    @field_validator("base_table")
    @classmethod
    def _vbt(cls, v: str) -> str:
        return _safe_ident(v)

    @field_validator("limit")
    @classmethod
    def _vlimit(cls, v: Optional[int]) -> int:
        if v is None:
            return MAX_LIMIT
        return max(1, min(int(v), MAX_LIMIT))


# ---------------------------------------------------------------------------
# JSON extraction from LLM output (these were missing!)
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        raise QueryPlanError("Query plan was empty.")

    parsed: list[dict[str, Any]] = []
    for candidate in _json_candidates(text):
        cleaned = _cleanup_json_candidate(candidate)
        if not cleaned:
            continue
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                parsed.append(data)
        except json.JSONDecodeError:
            continue
    if parsed:
        return parsed
    raise QueryPlanError("Query plan response did not contain a JSON object.")


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(item.strip() for item in fenced if item.strip())
    if balanced := _extract_balanced_json_object(text):
        candidates.append(balanced)
    candidates.extend(_extract_all_balanced_json_objects(text))
    return candidates


def _extract_balanced_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_all_balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    start: Optional[int] = None
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : i + 1])
                start = None
    return objects


def _cleanup_json_candidate(candidate: str) -> str:
    text = candidate.strip()
    if not text:
        return text
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    text = _strip_json_comments(text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)  # trailing commas
    return text.strip()


def _strip_json_comments(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < n and text[i] not in ("\n", "\r"):
                i += 1
            continue
        if ch == "#":
            i += 1
            while i < n and text[i] not in ("\n", "\r"):
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------

_ON_COND_RE = re.compile(
    r"(?P<lt>[A-Za-z_][A-Za-z0-9_]*)\.(?P<lc>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*=\s*"
    r"(?P<rt>[A-Za-z_][A-Za-z0-9_]*)\.(?P<rc>[A-Za-z_][A-Za-z0-9_]*)"
)


def _normalize_join_on_condition(cond: Any) -> Optional[dict[str, str]]:
    # Handle proper format: {"left_table": "t", "left_column": "id", ...}
    if isinstance(cond, dict):
        if all(k in cond for k in ("left_table", "left_column", "right_table", "right_column")):
            return {
                "left_table": str(cond["left_table"]),
                "left_column": str(cond["left_column"]),
                "right_table": str(cond["right_table"]),
                "right_column": str(cond["right_column"]),
            }

        # Try to extract from nested keys
        raw_expr = cond.get("condition") or cond.get("on") or cond.get("expr") or ""
        if raw_expr:
            m = _ON_COND_RE.search(str(raw_expr))
            if m:
                return {
                    "left_table": m.group("lt"),
                    "left_column": m.group("lc"),
                    "right_table": m.group("rt"),
                    "right_column": m.group("rc"),
                }
    
    # Handle string format: "t.id = ti.ticket_id"
    elif isinstance(cond, str):
        m = _ON_COND_RE.search(cond)
        if m:
            return {
                "left_table": m.group("lt"),
                "left_column": m.group("lc"),
                "right_table": m.group("rt"),
                "right_column": m.group("rc"),
            }
    
    return None


def _normalize_joins(joins: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for join in joins:
        if not isinstance(join, dict):
            continue
        normalised_join = dict(join)
        raw_on = normalised_join.get("on") or []
        if not isinstance(raw_on, list):
            raw_on = [raw_on]

        good_conditions: list[dict[str, str]] = []
        for cond in raw_on:
            fixed = _normalize_join_on_condition(cond)
            if fixed is not None:
                good_conditions.append(fixed)
            else:
                logger.warning("Dropping unrecognised JOIN ON condition: %r", cond)

        normalised_join["on"] = good_conditions
        result.append(normalised_join)
    return result


def _normalize_query_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)

    # Normalize lists
    for key in ("select", "aggregates", "joins", "filters", "group_by", "having", "order_by"):
        value = data.get(key)
        if value is None:
            data[key] = []
        elif not isinstance(value, list):
            data[key] = [value]

    # Normalize JOINs
    data["joins"] = _normalize_joins(data["joins"])

    # Normalize SELECT fields (handle "t.column" strings → {"table": "t", "column": "column"})
    normalized_select: list[Any] = []
    for s in data.get("select", []):
        if isinstance(s, str):
            # Parse "t.column" or "column" strings
            parts = s.split(".")
            if len(parts) == 2:
                normalized_select.append({"table": parts[0], "column": parts[1]})
            elif len(parts) == 1 and parts[0] != "*":
                # Assume base table alias if not specified
                normalized_select.append({"table": data.get("base_alias", "t"), "column": parts[0]})
            else:
                normalized_select.append(s)
        else:
            normalized_select.append(s)
    data["select"] = normalized_select

    # Normalize filters (coerce values, ensure required fields)
    coerced_filters: list[Any] = []
    for f in data.get("filters", []):
        if isinstance(f, dict):
            f = dict(f)
            # Ensure 'table' field exists
            if "table" not in f and "base_alias" in data:
                f["table"] = data["base_alias"]
            
            if "value" in f:
                raw_val = f["value"]
                if isinstance(raw_val, list):
                    f["value"] = [_coerce_filter_value(v) for v in raw_val]
                else:
                    f["value"] = _coerce_filter_value(raw_val)
        coerced_filters.append(f)
    data["filters"] = coerced_filters

    # Normalize ORDER BY (lowercase direction, ensure 'table' field)
    normalized_order_by: list[Any] = []
    for o in data.get("order_by", []):
        if isinstance(o, dict):
            o = dict(o)
            # Ensure 'table' field exists
            if "table" not in o and "base_alias" in data:
                o["table"] = data["base_alias"]
            # Normalize direction to lowercase
            if "direction" in o and isinstance(o["direction"], str):
                o["direction"] = o["direction"].lower()
            normalized_order_by.append(o)
        else:
            normalized_order_by.append(o)
    data["order_by"] = normalized_order_by

    # Remove invalid GROUP BY entries
    data["group_by"] = [
        item for item in data["group_by"]
        if not (isinstance(item, dict) and str(item.get("column", "")).strip() == "*")
    ]

    # Normalize limit/offset
    limit = data.get("limit", MAX_LIMIT)
    try:
        data["limit"] = int(limit) if limit is not None else MAX_LIMIT
    except (TypeError, ValueError):
        data["limit"] = MAX_LIMIT

    offset = data.get("offset")
    try:
        data["offset"] = int(offset) if offset is not None else None
    except (TypeError, ValueError):
        data["offset"] = None

    return data


def parse_query_plan(raw: str) -> QueryPlan:
    """Parse and validate an LLM-produced query plan JSON blob."""
    payloads = _extract_json(raw)
    last_error: Optional[ValidationError] = None
    for payload in payloads:
        normalised = _normalize_query_plan_payload(payload)
        try:
            plan = QueryPlan.model_validate(normalised)
            logger.debug("Parsed plan → base_table=%s, filters=%d", plan.base_table, len(plan.filters))
            return plan
        except ValidationError as exc:
            last_error = exc
    raise QueryPlanError(f"Invalid query plan: {last_error}") from last_error


# ---------------------------------------------------------------------------
# Alias map helpers
# ---------------------------------------------------------------------------

def _build_alias_map(plan: QueryPlan) -> dict[str, str]:
    alias_map: dict[str, str] = {
        plan.base_table.lower(): plan.base_alias or plan.base_table
    }
    for join in plan.joins:
        alias_map[join.table.lower()] = join.alias or join.table
    return alias_map


def _resolve(alias_map: dict[str, str], table_ref: str) -> str:
    lower = table_ref.lower()
    if lower in alias_map:
        return alias_map[lower]
    if table_ref in alias_map.values():
        return table_ref
    return table_ref


def _qcol(alias_map: dict[str, str], table_ref: str, column: str) -> str:
    return f"{_ident(_resolve(alias_map, table_ref))}.{_ident(column)}"


# ---------------------------------------------------------------------------
# SCOPE INJECTION - STRONGLY ENHANCED FOR CUSTOMER CHATBOT
# ---------------------------------------------------------------------------

def tables_in_plan(plan: QueryPlan) -> set[str]:
    tables = {plan.base_table.lower()}
    for join in plan.joins:
        tables.add(join.table.lower())
    return tables


def _has_filter(plan: QueryPlan, *, table_ref: str, column: str, operator: str, value: Any) -> bool:
    alias_map = _build_alias_map(plan)
    resolved = _resolve(alias_map, table_ref)
    for item in plan.filters:
        if (_resolve(alias_map, item.table).lower() == resolved.lower() and
            item.column.lower() == column.lower() and
            item.operator == operator and
            item.value == value):
            return True
    return False


def inject_mandatory_scope(
    plan: QueryPlan,
    *,
    customer_id: Optional[int],
    user_id: Optional[int],
) -> QueryPlan:
    scoped = plan.model_copy(deep=True)
    
    # Force base_alias for ticket queries to avoid alias mismatch
    if scoped.base_table.lower() == "ticket" and not scoped.base_alias:
        scoped.base_alias = "t"
        logger.info("AUTO-FIX | Added missing base_alias 't' for ticket table")
    
    # Force base_alias for ticket_item to avoid issues
    if scoped.base_table.lower() == "ticket_item" and not scoped.base_alias:
        scoped.base_alias = "ti"
        logger.info("AUTO-FIX | Added missing base_alias 'ti' for ticket_item table")
    
    tables = tables_in_plan(scoped)
    alias_map = _build_alias_map(scoped)

    # Force ticket base + alias for list/detail queries
    if scoped.base_table.lower() in {"ticket_item", "product"}:
        logger.critical(f"FORCE TICKET BASE | Overriding '{scoped.base_table}' → 'ticket' (alias 't')")
        scoped.base_table = "ticket"
        scoped.base_alias = "t"

        # Auto-add correct joins ONLY when needed
        if "product" in tables or "brand" in tables or "color" in tables or "size" in tables:
            if not any(j.table.lower() == "ticket_item" for j in scoped.joins):
                scoped.joins.insert(0, JoinSpec(
                    table="ticket_item",
                    alias="ti",
                    join_type="inner",
                    on=[JoinCondition(left_table="t", left_column="id",
                                      right_table="ti", right_column="ticket_id")]
                ))
            if not any(j.table.lower() == "product" for j in scoped.joins):
                scoped.joins.append(JoinSpec(
                    table="product",
                    alias="p",
                    join_type="inner",
                    on=[JoinCondition(left_table="ti", left_column="product_id",
                                      right_table="p", right_column="id")]
                ))

    # Clean bad filters (remove anything except customer_id)
    clean_filters = []
    for f in scoped.filters:
        if f.column.lower() == "customer_id":
            clean_filters.append(f)
        else:
            logger.warning(f"DROPPED invalid filter: {f.column} {f.operator} {f.value}")
    scoped.filters = clean_filters

    # Ensure customer_id filter is always present on ticket
    if {"ticket", "ticket_item"} & tables:
        if customer_id is None:
            raise QueryPlanError("Missing customer scope")
        ticket_ref = alias_map.get("ticket", "t")
        if not _has_filter(scoped, table_ref=ticket_ref, column="customer_id",
                           operator="=", value=int(customer_id)):
            scoped.filters.append(
                FilterSpec(table=ticket_ref, column="customer_id",
                           operator="=", value=int(customer_id))
            )
            logger.info("SCOPE INJECTED | ticket.customer_id = %d", customer_id)

    # Customer & User scoping
    if "customer" in tables and customer_id is not None:
        cust_ref = alias_map.get("customer", "customer")
        if not _has_filter(scoped, table_ref=cust_ref, column="id", operator="=", value=int(customer_id)):
            scoped.filters.append(FilterSpec(table=cust_ref, column="id", operator="=", value=int(customer_id)))

    if "user" in tables and user_id is not None:
        user_ref = alias_map.get("user", "user")
        if not _has_filter(scoped, table_ref=user_ref, column="id", operator="=", value=int(user_id)):
            scoped.filters.append(FilterSpec(table=user_ref, column="id", operator="=", value=int(user_id)))

    return scoped
# ---------------------------------------------------------------------------
# Validation & SQL builder
# ---------------------------------------------------------------------------

def validate_and_fix_group_by(plan: QueryPlan) -> QueryPlan:
    if not plan.aggregates:
        return plan

    # Nuclear fix: if there are aggregates AND select is non-empty → this is almost always wrong for count/sum
    if any(agg.func in ("count", "sum") for agg in plan.aggregates) and plan.select:
        logger.warning(
            "AUTO-FIX AGGRESSIVE | Detected count/sum with non-empty select → CLEARING SELECT"
        )
        fixed = plan.model_copy(deep=True)
        fixed.select = []  # remove all select columns
        fixed.group_by = []  # no need for group by anymore
        return fixed

    # Normal case: aggregates + grouping
    non_agg_cols = [
        GroupByField(table=s.table, column=s.column)
        for s in plan.select if s.column != "*"
    ]

    if not non_agg_cols:
        return plan

    existing_gb = {(gb.table.lower(), gb.column.lower()) for gb in plan.group_by}
    missing = [
        col for col in non_agg_cols
        if (col.table.lower(), col.column.lower()) not in existing_gb
    ]

    if missing:
        logger.info("AUTO-FIX | Adding %d missing GROUP BY columns", len(missing))
        fixed = plan.model_copy(deep=True)
        fixed.group_by.extend(missing)
        return fixed

    return plan

def build_sql_from_plan(plan: QueryPlan) -> str:
    plan = validate_and_fix_group_by(plan)
    alias_map = _build_alias_map(plan)

    select_parts: list[str] = []
    for item in plan.select:
        if item.column == "*":
            expr = f"{_ident(_resolve(alias_map, item.table))}.*"
        else:
            expr = _qcol(alias_map, item.table, item.column)
        if item.alias:
            expr += f" AS {_ident(item.alias)}"
        select_parts.append(expr)

    for item in plan.aggregates:
        if item.column == "*":
            target = "*"
        else:
            table_ref = item.table or plan.base_alias or plan.base_table
            target = _qcol(alias_map, table_ref, item.column)
        distinct = "DISTINCT " if item.distinct else ""
        expr = f"{item.func.upper()}({distinct}{target})"
        if item.alias:
            expr += f" AS {_ident(item.alias)}"
        select_parts.append(expr)

    if not select_parts:
        select_parts = ["*"]

    base_alias_sql = f" {_ident(plan.base_alias)}" if plan.base_alias else ""
    sql_parts: list[str] = [
        f"SELECT {', '.join(select_parts)}",
        f"FROM {_ident(plan.base_table)}{base_alias_sql}",
    ]

    for join in plan.joins:
        alias_sql = f" {_ident(join.alias)}" if join.alias else ""
        if not join.on:
            raise QueryPlanError(f"JOIN on '{join.table}' has no ON conditions.")
        clauses = [
            f"{_qcol(alias_map, cond.left_table, cond.left_column)} = "
            f"{_qcol(alias_map, cond.right_table, cond.right_column)}"
            for cond in join.on
        ]
        sql_parts.append(
            f"{join.join_type.upper()} JOIN {_ident(join.table)}{alias_sql}"
            f" ON {' AND '.join(clauses)}"
        )

    if plan.filters:
        where_clauses: list[str] = []
        for item in plan.filters:
            lhs = _qcol(alias_map, item.table, item.column)
            op = item.operator

            if op == "in":
                if not isinstance(item.value, list) or not item.value:
                    raise QueryPlanError(f"IN filter must have non-empty list.")
                rhs = ", ".join(_literal(v) for v in item.value)
                where_clauses.append(f"{lhs} IN ({rhs})")
            elif op == "not in":
                if not isinstance(item.value, list) or not item.value:
                    raise QueryPlanError(f"NOT IN filter must have non-empty list.")
                rhs = ", ".join(_literal(v) for v in item.value)
                where_clauses.append(f"{lhs} NOT IN ({rhs})")
            elif op == "is null":
                where_clauses.append(f"{lhs} IS NULL")
            elif op == "is not null":
                where_clauses.append(f"{lhs} IS NOT NULL")
            else:
                where_clauses.append(f"{lhs} {op.upper()} {_literal(item.value)}")

        sql_parts.append("WHERE " + " AND ".join(where_clauses))

    if plan.group_by:
        group_items = [
            _qcol(alias_map, item.table, item.column)
            for item in plan.group_by
        ]
        sql_parts.append("GROUP BY " + ", ".join(group_items))

    if plan.having:
        if not plan.group_by and not plan.aggregates:
            raise QueryPlanError("HAVING requires GROUP BY or aggregates.")
        having_clauses: list[str] = []
        for item in plan.having:
            if item.column == "*":
                target = "*"
            else:
                if not item.table:
                    raise QueryPlanError(f"HAVING aggregate requires table.")
                target = _qcol(alias_map, item.table, item.column)
            agg_expr = f"{item.func.upper()}({target})"
            having_clauses.append(f"{agg_expr} {item.operator.upper()} {_literal(item.value)}")
        sql_parts.append("HAVING " + " AND ".join(having_clauses))

    if plan.order_by:
        order_items = [
            f"{_qcol(alias_map, item.table, item.column)} {item.direction.upper()}"
            for item in plan.order_by
        ]
        sql_parts.append("ORDER BY " + ", ".join(order_items))

    sql_parts.append(f"LIMIT {max(1, min(plan.limit, MAX_LIMIT))}")
    if plan.offset is not None and plan.offset > 0:
        sql_parts.append(f"OFFSET {plan.offset}")

    sql = " ".join(sql_parts)

    try:
        stmt = sqlglot.parse_one(sql, dialect="postgres")
        sql = stmt.sql(dialect="postgres")
    except Exception as exc:
        raise QueryPlanError(f"Generated SQL is invalid: {exc}") from exc

    logger.debug("Final SQL built:\n%s", sql)
    return sql