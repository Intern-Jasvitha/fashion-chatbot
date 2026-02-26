"""Extract curated DDL-style schema + strong customer scoping for LLM SQL generation."""

import re
from pathlib import Path

# ================== WHITELIST - ONLY THESE TABLES ARE VISIBLE TO CUSTOMER BOT ==================
ALLOWED_MODELS = {
    "Category", "Type", "Size", "Color", "Gender", "Brand",
    "CcpaymentType", "CcpaymentState", "CcentryMethod",
    "Customer", "Employee",
    "Ccpayment", "CcpaymentCard",
    "Product", "Ticket", "TicketItem",
    "User",
}

# Relations (used dynamically)
JOIN_RELATIONS: list[tuple[str, str, str, str]] = [
    ("type", "category_id", "category", "id"),
    ("product", "type_id", "type", "id"),
    ("product", "size_code", "size", "code"),
    ("product", "color_code", "color", "code"),
    ("product", "brand_id", "brand", "id"),
    ("product", "gender_id", "gender", "id"),
    ("ticket", "employee_id", "employee", "id"),
    ("ticket", "customer_id", "customer", "id"),
    ("ticket", "ccpayment_id", "ccpayment", "id"),
    ("ticket_item", "ticket_id", "ticket", "id"),
    ("ticket_item", "product_id", "product", "id"),
    ("ccpayment", "ccpayment_state", "ccpayment_state", "code"),
    ("ccpayment_card", "ccpayment_id", "ccpayment", "id"),
    ("ccpayment_card", "payment_type", "ccpayment_type", "code"),
    ("ccpayment_card", "ccentry_method", "ccentry_method", "code"),
]

def get_schema_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "prisma" / "schema.prisma"

def _prisma_to_sql_type(pt: str) -> str:
    m = {
        "Int": "INT",
        "BigInt": "BIGINT",
        "String": "VARCHAR/TEXT",
        "Boolean": "BOOLEAN",
        "DateTime": "TIMESTAMP",
        "Decimal": "NUMERIC(18,5)",   # Critical for SUM/aggregates
        "Float": "FLOAT",
    }
    base = pt.replace("?", "").replace("[]", "")
    return m.get(base, base.upper())

def load_schema_context() -> str:
    path = get_schema_path()
    if not path.exists():
        return _fallback_schema()

    text = path.read_text()
    models = []

    model_pattern = re.compile(r"model\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
    for m in model_pattern.finditer(text):
        model_name = m.group(1)
        if model_name not in ALLOWED_MODELS:
            continue

        body = m.group(2)
        map_match = re.search(r'@@map\s*\(\s*["\']([^"\']+)["\']\s*\)', body)
        table_name = map_match.group(1) if map_match else model_name.lower()

        field_pattern = re.compile(
            r"^\s*(\w+)\s+([\w\[\]]+?)\s*(\?)?\s*(.*)$", re.MULTILINE
        )
        columns = []
        for f in field_pattern.finditer(body):
            field_name = f.group(1)
            field_type = f.group(2)
            extra = f.group(4).strip()

            if "relation" in extra.lower() or field_type.endswith("[]"):
                continue

            map_match = re.search(r'@map\s*\(\s*["\']([^"\']+)["\']\s*\)', extra)
            col_name = (
                map_match.group(1)
                if map_match
                else re.sub(r'(?<!^)(?=[A-Z])', '_', field_name).lower()
            )

            sql_type = _prisma_to_sql_type(field_type)
            col_str = f"{col_name} ({sql_type})"
            if "@id" in extra or (field_name.lower() == "id" and "Int" in field_type):
                col_str += " [PK]"
            columns.append(col_str)

        if columns:
            models.append({"table": table_name, "columns": columns})

    return (
        _format_ddl(models)
        + "\n\n"
        + _format_dynamic_relations()
        + "\n\n"
        + _format_customer_scoping()
        + "\n\n"
        + _format_examples()
        + "\n\n"
        + _format_time_guidance()
    )

def _format_ddl(models):
    lines = ["PostgreSQL schema (customer chatbot only):", ""]
    for m in models:
        lines.append(f"CREATE TABLE {m['table']} (")
        lines.extend(f"  {col}," for col in m["columns"])
        lines[-1] = lines[-1].rstrip(",")
        lines.append(");")
        lines.append("")
    return "\n".join(lines).strip()

def _format_dynamic_relations():
    lines = ["Relationships (use these JOINs):"]
    for ft, fc, tt, tc in JOIN_RELATIONS:
        lines.append(f"- {ft}.{fc} → {tt}.{tc}")
    lines.append("")
    lines.append("IMPORTANT: For questions like 'products I bought', 'my orders', 'what I purchased' →")
    lines.append("ALWAYS start from ticket table and JOIN through ticket_item → product.")
    return "\n".join(lines)

def _format_customer_scoping():
    return """CRITICAL CUSTOMER SCOPING RULES (NEVER VIOLATE):
This is a customer-facing chatbot. EVERY query MUST be scoped to the current customer using the EXACT literal integer from scope_rules.

Required filters:
- ticket.customer_id = <literal integer>
- ticket_item → must JOIN ticket → apply customer_id filter
- customer.id = <literal integer>

"my orders", "what did I buy?", "how much have I spent?", "recent purchases" → 
base_table MUST be "ticket" + customer_id filter on ticket.customer_id."""

def _format_examples():
    return """Example query patterns (use literal values from scope_rules + JSON plan format):

1. Pure count: "How many orders do I have?"
   {
     "base_table": "ticket",
     "base_alias": "t",
     "select": [],
     "aggregates": [{"func": "count", "table": "t", "column": "*"}],
     "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}]
   }

2. Pure sum: "How much have I spent in total?"
   {
     "base_table": "ticket",
     "base_alias": "t",
     "select": [],
     "aggregates": [{"func": "sum", "table": "t", "column": "total_order"}],
     "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}]
   }

3. Recent orders:
   {
     "base_table": "ticket",
     "base_alias": "t",
     "select": [{"table": "t", "column": "id"}, {"table": "t", "column": "timeplaced"}, {"table": "t", "column": "total_order"}],
     "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}],
     "order_by": [{"table": "t", "column": "timeplaced", "direction": "desc"}],
     "limit": 10
   }

4. Products purchased (with joins):
   {
     "base_table": "ticket",
     "base_alias": "t",
     "select": [{"table": "p", "column": "product_name"}, {"table": "ti", "column": "quantity"}, {"table": "ti", "column": "price"}],
     "joins": [
       {"table": "ticket_item", "alias": "ti", "join_type": "inner", "on": [{"left_table": "t", "left_column": "id", "right_table": "ti", "right_column": "ticket_id"}]},
       {"table": "product", "alias": "p", "join_type": "inner", "on": [{"left_table": "ti", "left_column": "product_id", "right_table": "p", "right_column": "id"}]}
     ],
     "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}],
     "limit": 10
   }

CRITICAL - Aggregate queries (how many, total, sum, count):
- ALWAYS include "base_alias" (e.g. "t" for ticket, "ti" for ticket_item)
- For ANY "how many", "total", "sum", "count" → select MUST be empty array []
- Never mix select columns with simple aggregates (count/sum/avg) in the same plan
- Always include "table" in each aggregate and filter (e.g. "t" for ticket)

BAD:  {"base_table": "ticket", "select": [{"table": "t", "column": "total_order"}], "aggregates": [{"func": "sum", "table": "t", "column": "total_order"}]}
GOOD: {"base_table": "ticket", "base_alias": "t", "select": [], "aggregates": [{"func": "sum", "table": "t", "column": "total_order", "alias": "total_spent"}], "filters": [{"table": "t", "column": "customer_id", "operator": "=", "value": 123}]}"""

def _format_time_guidance():
    return """TIME & GROUPING GUIDANCE (current UTC date: 2026-02-25)
Use these exact patterns:

- Last month: timeplaced >= '2026-01-26'
- This year: timeplaced >= '2026-01-01'
- Per month: group_by: ["date_trunc('month', t.timeplaced)"]
- Last 30 days: timeplaced >= '2026-01-26'

Always use literal dates based on 2026-02-25. Never use placeholders."""

def _fallback_schema() -> str:
    """Static fallback if prisma/schema.prisma cannot be read."""
    return """PostgreSQL schema (customer chatbot only):

CREATE TABLE category (
  id (INT) [PK],
  category_name (VARCHAR/TEXT)
);

CREATE TABLE type (
  id (INT) [PK],
  type_name (VARCHAR/TEXT),
  category_id (INT)
);

CREATE TABLE size (
  code (VARCHAR/TEXT) [PK],
  description (VARCHAR/TEXT)
);

CREATE TABLE color (
  code (VARCHAR/TEXT) [PK],
  color_name (VARCHAR/TEXT)
);

CREATE TABLE gender (
  id (INT) [PK],
  gender_name (VARCHAR/TEXT)
);

CREATE TABLE brand (
  id (INT) [PK],
  brand_name (VARCHAR/TEXT)
);

CREATE TABLE customer (
  id (INT) [PK],
  firstname (VARCHAR/TEXT),
  lastname (VARCHAR/TEXT),
  dob (TIMESTAMP),
  email (VARCHAR/TEXT),
  phoneno (VARCHAR/TEXT)
);

CREATE TABLE employee (
  id (INT) [PK],
  firstname (VARCHAR/TEXT),
  lastname (VARCHAR/TEXT)
);

CREATE TABLE ccpayment_type (
  code (VARCHAR/TEXT) [PK],
  name (VARCHAR/TEXT)
);

CREATE TABLE ccpayment_state (
  code (VARCHAR/TEXT) [PK],
  name (VARCHAR/TEXT)
);

CREATE TABLE ccentry_method (
  code (VARCHAR/TEXT) [PK],
  name (VARCHAR/TEXT)
);

CREATE TABLE ccpayment (
  id (BIGINT) [PK],
  customer_id (INT),
  amount (NUMERIC(18,5)),
  time (TIMESTAMP),
  ccpayment_state (VARCHAR/TEXT)
);

CREATE TABLE ccpayment_card (
  id (BIGINT) [PK],
  ccpayment_id (BIGINT),
  payment_type (VARCHAR/TEXT),
  ccentry_method (VARCHAR/TEXT),
  card_last4 (VARCHAR/TEXT)
);

CREATE TABLE ticket (
  id (BIGINT) [PK],
  timeplaced (TIMESTAMP),
  employee_id (INT),
  customer_id (INT),
  total_product (NUMERIC(18,5)),
  total_tax (NUMERIC(18,5)),
  total_order (NUMERIC(18,5)),
  ccpayment_id (BIGINT)
);

CREATE TABLE ticket_item (
  ticket_id (BIGINT),
  numseq (INT),
  product_id (INT),
  quantity (NUMERIC(18,5)),
  price (NUMERIC(18,5)),
  tax_amount (NUMERIC(18,5)),
  product_amount (NUMERIC(18,5))
);

CREATE TABLE product (
  id (INT) [PK],
  type_id (INT),
  size_code (VARCHAR/TEXT),
  color_code (VARCHAR/TEXT),
  product_name (VARCHAR/TEXT),
  brand_id (INT),
  gender_id (INT),
  description (VARCHAR/TEXT)
);

CREATE TABLE "user" (
  id (INT) [PK],
  customer_id (INT)
);

Relationships (use these JOINs):
- ticket.customer_id → customer.id
- ticket_item.ticket_id → ticket.id
- ticket_item.product_id → product.id
- product.type_id → type.id
- product.brand_id → brand.id
- product.color_code → color.code
- product.size_code → size.code
- ticket.ccpayment_id → ccpayment.id

CRITICAL: ALWAYS filter ticket.customer_id = <your customer_id> (literal integer)"""