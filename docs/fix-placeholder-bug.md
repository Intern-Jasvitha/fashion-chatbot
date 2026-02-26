# Fix: SQL Placeholder Bug

## Problem Summary

When users queried the SQL agent with requests like "show me order details of my past 3 months", the system returned an error:

```
Error: invalid input syntax for type integer: "{customer_id}"
```

### Root Cause

The LLM was copying literal placeholder strings (e.g., `{customer_id}`) from the schema examples into the query plan, instead of using the actual customer_id values. This resulted in SQL like:

```sql
WHERE t.customer_id = '{customer_id}' AND t.customer_id = 1
```

PostgreSQL tried to cast the string `"{customer_id}"` to an integer, which failed.

## The Fix

We implemented a three-layer defense strategy:

### 1. Updated Schema Examples (`schema_loader.py`)

**Before:**
```python
"""Example queries (always include customer_id filter):
1. Recent orders:
   Filters: customer_id = {customer_id}
```

**After:**
```python
"""Example query patterns (use actual values from scope_rules, NOT placeholders):
1. Recent orders:
   Filters: customer_id = <use the actual customer_id number from scope_rules>

CRITICAL: Always use the LITERAL integer values provided in scope_rules.
NEVER use placeholder strings like {customer_id} in filter values.
```

### 2. Added Placeholder Detection (`sql_query_plan.py`)

Added validation in `_coerce_filter_value()` to reject placeholder patterns:

```python
# SAFETY: Reject placeholder patterns that LLM shouldn't emit
if re.match(r'^[{]+[^}]+[}]+$', stripped):
    raise QueryPlanError(
        f"Filter value contains unresolved placeholder: {value!r}. "
        f"Use actual scope values from scope_rules instead."
    )
```

This catches patterns like:
- `{customer_id}`
- `{{customer_id}}`
- `{user_id}`

### 3. Enhanced Scope Rules Prompt (`sql_agent.py`)

**Before:**
```python
scope_rules = (
    f"- customer_id = {customer_id_int} (customer name: {display_name})\n"
    f"- user_id = {user_id_int if user_id_int is not None else 'not available'}\n"
)
```

**After:**
```python
scope_rules = (
    f"MANDATORY SCOPE - Use these EXACT literal values in your filters:\n"
    f"- customer_id = {customer_id_int}  (customer name: {display_name})\n"
    f"  → IMPORTANT: Use the literal integer {customer_id_int}, NOT a placeholder like {{customer_id}}\n"
)
```

## Testing

Added comprehensive tests in `test_sql_query_plan.py`:

```python
def test_parse_query_plan_rejects_placeholder_values()
def test_parse_query_plan_rejects_double_brace_placeholders()
def test_parse_query_plan_accepts_actual_integer_values()
```

All tests pass ✅

## Impact

- **Prevents** the LLM from learning the wrong pattern (Fix 1)
- **Detects** if placeholders slip through (Fix 2)  
- **Guides** the LLM more explicitly (Fix 3)

The combination ensures robust handling of scope filters and prevents similar issues in the future.

## Files Changed

- `app/services/schema_loader.py` - Updated example queries
- `app/services/sql_query_plan.py` - Added placeholder detection
- `app/services/sql_agent.py` - Enhanced scope rules prompt
- `app/tests/test_sql_query_plan.py` - Added validation tests
