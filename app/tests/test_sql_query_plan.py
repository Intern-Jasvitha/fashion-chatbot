import pytest

from app.services.sql_query_plan import (
    QueryPlanError,
    build_sql_from_plan,
    inject_mandatory_scope,
    parse_query_plan,
)


def test_parse_query_plan_rejects_invalid_json() -> None:
    with pytest.raises(QueryPlanError):
        parse_query_plan("not-json")


def test_scope_injection_adds_ticket_customer_filter() -> None:
    raw = """
    {
      "base_table": "ticket",
      "base_alias": "t",
      "select": [{"table": "t", "column": "id"}],
      "filters": [],
      "limit": 50
    }
    """
    plan = parse_query_plan(raw)
    scoped = inject_mandatory_scope(plan, customer_id=42, user_id=9)
    sql = build_sql_from_plan(scoped)
    normalized = sql.lower()
    assert "ticket" in normalized
    assert "customer_id = 42" in normalized


def test_scope_injection_requires_user_scope_for_user_table() -> None:
    raw = """
    {
      "base_table": "user",
      "base_alias": "u",
      "select": [{"table": "u", "column": "id"}],
      "filters": [],
      "limit": 20
    }
    """
    plan = parse_query_plan(raw)
    with pytest.raises(QueryPlanError):
        inject_mandatory_scope(plan, customer_id=1, user_id=None)


def test_parse_query_plan_handles_fenced_json_with_commentary() -> None:
    raw = """
    Here is the safe plan:
    ```json
    {
      "base_table": "ticket",
      "base_alias": "t",
      "select": [{"table": "t", "column": "id", "alias": "order_id"}],
      "filters": [
        {"table": "t", "column": "customer_id", "operator": "=", "value": 1} # comment
      ],
      "limit": 5
    }
    ```
    """
    plan = parse_query_plan(raw)
    assert plan.base_table == "ticket"
    assert plan.limit == 5


def test_parse_query_plan_rejects_placeholder_values() -> None:
    """Test that placeholder strings like {customer_id} are rejected."""
    raw = """
    {
      "base_table": "ticket",
      "base_alias": "t",
      "select": [{"table": "t", "column": "id"}],
      "filters": [
        {"table": "t", "column": "customer_id", "operator": "=", "value": "{customer_id}"}
      ],
      "limit": 50
    }
    """
    with pytest.raises(QueryPlanError, match="unresolved placeholder"):
        parse_query_plan(raw)


def test_parse_query_plan_rejects_double_brace_placeholders() -> None:
    """Test that double-brace placeholders like {{customer_id}} are rejected."""
    raw = """
    {
      "base_table": "ticket",
      "base_alias": "t",
      "select": [{"table": "t", "column": "id"}],
      "filters": [
        {"table": "t", "column": "customer_id", "operator": "=", "value": "{{customer_id}}"}
      ],
      "limit": 50
    }
    """
    with pytest.raises(QueryPlanError, match="unresolved placeholder"):
        parse_query_plan(raw)


def test_parse_query_plan_accepts_actual_integer_values() -> None:
    """Test that actual integer values (as strings or numbers) work correctly."""
    raw = """
    {
      "base_table": "ticket",
      "base_alias": "t",
      "select": [{"table": "t", "column": "id"}],
      "filters": [
        {"table": "t", "column": "customer_id", "operator": "=", "value": "123"}
      ],
      "limit": 50
    }
    """
    plan = parse_query_plan(raw)
    # The value should be coerced to integer
    assert plan.filters[0].value == 123
