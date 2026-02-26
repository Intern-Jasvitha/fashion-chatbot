"""SQL query memory for conversation context tracking - CUSTOMER CHATBOT EDITION."""

from collections import deque
from datetime import datetime
from typing import Any, Optional


class SQLQueryMemory:
    """
    Tracks recent SQL queries to give the LLM conversation context.

    This helps the LLM remember previous questions and results, 
    so it can answer follow-ups like "What was the most expensive one?" 
    or "Show me more details from my last order".
    
    Persisted per session via LangGraph checkpoint state.
    """

    def __init__(self):
        self.recent_queries: deque[dict] = deque(maxlen=5)   # keep last 5 queries
        self.last_result_count: int = 0
        self.last_tables: set[str] = set()

    def add_query(
        self,
        question: str,
        sql: str,
        result_count: int,
        tables: set[str]
    ):
        """Add a completed query to history."""
        self.recent_queries.append({
            "question": question,
            "sql_summary": self._summarize_sql(sql),
            "result_count": result_count,
            "tables": list(tables),
            "timestamp": datetime.now().isoformat()
        })
        self.last_result_count = result_count
        self.last_tables = tables

    def get_context_prompt(self) -> str:
        """Return recent conversation context for the LLM (last 3 queries)."""
        if not self.recent_queries:
            return ""

        lines = ["Recent conversation (customer-scoped):"]
        for q in list(self.recent_queries)[-3:]:   # show last 3
            tables_str = ", ".join(sorted(q["tables"]))
            lines.append(
                f"Q: {q['question']}\n"
                f"   → {q['result_count']} results from tables: {tables_str}"
            )
        return "\n".join(lines) + "\n"

    def _summarize_sql(self, sql: str) -> str:
        """Create a short, safe summary of the SQL (never leak full query)."""
        sql_lower = sql.lower().strip()

        if "select" in sql_lower:
            # Extract just the main tables and limit
            from_pos = sql_lower.find("from")
            if from_pos != -1:
                # Take up to 80 chars after FROM
                summary = sql[from_pos:from_pos + 80].strip()
                return f"SELECT ... {summary}..."

        # Fallback
        return sql[:80] + ("..." if len(sql) > 80 else "")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for LangGraph checkpoint persistence."""
        return {
            "recent_queries": list(self.recent_queries),
            "last_result_count": self.last_result_count,
            "last_tables": list(self.last_tables),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SQLQueryMemory":
        """Deserialize from LangGraph checkpoint."""
        memory = cls()
        if data:
            memory.recent_queries = deque(
                data.get("recent_queries", []),
                maxlen=5
            )
            memory.last_result_count = data.get("last_result_count", 0)
            memory.last_tables = set(data.get("last_tables", []))
        return memory