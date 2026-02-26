import pytest

from app.services.sql_validator import SqlValidationError, run_sql_firewall


def test_firewall_blocks_forbidden_table_prefix() -> None:
    sql = "SELECT id FROM finance_report LIMIT 10"
    with pytest.raises(SqlValidationError):
        run_sql_firewall(sql, customer_id=1, user_id=1)


def test_firewall_blocks_ticket_query_missing_scope() -> None:
    sql = "SELECT id FROM ticket LIMIT 10"
    with pytest.raises(SqlValidationError):
        run_sql_firewall(sql, customer_id=1, user_id=1)


def test_firewall_blocks_cross_user_aggregate_without_scope() -> None:
    sql = "SELECT COUNT(*) FROM ticket"
    with pytest.raises(SqlValidationError):
        run_sql_firewall(sql, customer_id=1, user_id=1)


def test_firewall_allows_scoped_ticket_query() -> None:
    sql = "SELECT COUNT(*) FROM ticket WHERE ticket.customer_id = 1 LIMIT 10"
    out = run_sql_firewall(sql, customer_id=1, user_id=1)
    assert "ticket.customer_id = 1" in out

