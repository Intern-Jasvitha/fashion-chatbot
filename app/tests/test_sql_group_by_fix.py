"""Test automatic GROUP BY validation and fixing."""

import pytest

from app.services.sql_agent import SQL_PLAN_PROMPT
from app.services.sql_query_plan import (
    AggregateSpec,
    FilterSpec,
    GroupByField,
    QueryPlan,
    SelectField,
    build_sql_from_plan,
    validate_and_fix_group_by,
)


def test_auto_fix_missing_group_by():
    """Test that missing GROUP BY columns are added automatically."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[
            SelectField(table="t", column="id", alias="id"),
            SelectField(table="t", column="customer_id"),
        ],
        aggregates=[
            AggregateSpec(func="count", column="*"),
        ],
        group_by=[],  # Missing!
        limit=50,
    )

    fixed = validate_and_fix_group_by(plan)

    assert len(fixed.group_by) == 2
    assert any(gb.column == "id" for gb in fixed.group_by)
    assert any(gb.column == "customer_id" for gb in fixed.group_by)


def test_no_fix_needed_pure_aggregate():
    """Test that pure aggregate queries don't get GROUP BY."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[],
        aggregates=[AggregateSpec(func="count", column="*")],
        group_by=[],
        limit=50,
    )

    fixed = validate_and_fix_group_by(plan)

    assert len(fixed.group_by) == 0


def test_no_fix_needed_already_complete():
    """Test that correct GROUP BY is left untouched."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[SelectField(table="t", column="id")],
        aggregates=[AggregateSpec(func="count", column="*")],
        group_by=[GroupByField(table="t", column="id")],
        limit=50,
    )

    fixed = validate_and_fix_group_by(plan)

    assert len(fixed.group_by) == 1
    assert fixed.group_by[0].column == "id"


def test_no_fix_needed_no_aggregates():
    """Test that plans without aggregates are unchanged."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[
            SelectField(table="t", column="id"),
            SelectField(table="t", column="customer_id"),
        ],
        aggregates=[],
        group_by=[],
        limit=50,
    )

    fixed = validate_and_fix_group_by(plan)

    assert fixed.group_by == []


def test_auto_fix_adds_only_missing_columns():
    """Test that only missing columns are added, existing ones preserved."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[
            SelectField(table="t", column="id"),
            SelectField(table="t", column="customer_id"),
        ],
        aggregates=[AggregateSpec(func="count", column="*")],
        group_by=[GroupByField(table="t", column="id")],  # customer_id missing
        limit=50,
    )

    fixed = validate_and_fix_group_by(plan)

    assert len(fixed.group_by) == 2
    assert any(gb.column == "id" for gb in fixed.group_by)
    assert any(gb.column == "customer_id" for gb in fixed.group_by)


def test_auto_fixed_plan_produces_valid_sql():
    """Test that auto-fixed plan produces valid SQL (no GROUP BY error)."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[SelectField(table="t", column="id", alias="id")],
        aggregates=[AggregateSpec(func="count", column="*")],
        filters=[FilterSpec(table="t", column="customer_id", operator="=", value=1)],
        group_by=[],
        limit=50,
    )
    fixed = validate_and_fix_group_by(plan)
    sql = build_sql_from_plan(fixed)
    assert "GROUP BY" in sql
    assert "t.id" in sql or ".id" in sql


def test_sql_prompt_includes_fewshot_examples():
    """Regression: SQL prompt must include few-shot examples for count/join patterns."""
    assert 'how many tickets i have' in SQL_PLAN_PROMPT.lower()
    assert 'select' in SQL_PLAN_PROMPT.lower() and 'empty' in SQL_PLAN_PROMPT.lower()
    assert 'count' in SQL_PLAN_PROMPT.lower()
    assert 'what products did i buy' in SQL_PLAN_PROMPT.lower()
    assert 'how many items in each order' in SQL_PLAN_PROMPT.lower()
    assert 'CRITICAL RULES' in SQL_PLAN_PROMPT or 'Patterns' in SQL_PLAN_PROMPT


def test_auto_fix_removes_select_star_with_aggregates():
    """Test that SELECT * is removed when aggregates present (how many tickets case)."""
    plan = QueryPlan(
        base_table="ticket",
        base_alias="t",
        select=[SelectField(table="t", column="*")],
        aggregates=[AggregateSpec(func="count", column="*")],
        filters=[FilterSpec(table="t", column="customer_id", operator="=", value=1)],
        group_by=[],
        limit=1,
    )
    fixed = validate_and_fix_group_by(plan)
    assert len(fixed.select) == 0
    sql = build_sql_from_plan(fixed)
    assert "COUNT(*)" in sql
    assert "t.*" not in sql
