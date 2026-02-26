"""Unit tests for query preprocessor (semantic ID detection for SQL agent)."""

import pytest

from app.services.query_preprocessor import preprocess_query_for_sql


def test_preprocess_detects_order_id_in_phrase() -> None:
    result = preprocess_query_for_sql("give me order details for 264933961", 123)
    assert "264933961" in result["detected_ids"]
    assert result["enhanced_scope_instruction"]
    assert "customer_id = 123" in result["enhanced_scope_instruction"]
    assert "ticket_id" in result["enhanced_scope_instruction"] or "product_id" in result["enhanced_scope_instruction"]


def test_preprocess_detects_order_keyword_with_id() -> None:
    result = preprocess_query_for_sql("order 264933961", 456)
    assert "264933961" in result["detected_ids"]
    assert "456" in result["enhanced_scope_instruction"]


def test_preprocess_no_id_returns_empty_enhancement() -> None:
    result = preprocess_query_for_sql("what are my recent orders?", 789)
    assert result["enhanced_scope_instruction"] == ""
    assert result["detected_ids"] == []


def test_preprocess_preserves_original_query() -> None:
    query = "order details for this 264933961"
    result = preprocess_query_for_sql(query, 1)
    assert result["original_query"] == query
