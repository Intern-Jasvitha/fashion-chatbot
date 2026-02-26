"""
Production-grade schema chunker for SQL agent RAG.
Decomposes database schema into rich semantic chunks (table definitions,
relationship patterns, security rules, query patterns) derived from
Prisma schema and validated for customer-scoped use cases.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

# Tables visible to customer bot (from schema_loader.ALLOWED_MODELS)
# Map: Prisma model name -> table name (from @@map in schema.prisma)
ALLOWED_TABLES = {
    "category",
    "type",
    "size",
    "color",
    "gender",
    "brand",
    "ccpayment_type",
    "ccpayment_state",
    "ccentry_method",
    "customer",
    "employee",
    "ccpayment",
    "ccpayment_card",
    "product",
    "ticket",
    "ticket_item",
    "user",
}

# Verified from prisma/schema.prisma: (from_table, from_column, to_table, to_column)
# Used for JOIN patterns - do not blindly copy; matches actual FK relationships
VERIFIED_JOIN_RELATIONS = [
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


def _chunk(
    content: str,
    chunk_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "content": content,
        "metadata": {
            "type": chunk_type,
            "indexed_at": now,
            **metadata,
        },
    }


# ---------------------------------------------------------------------------
# Type 1: Table definitions (rich semantic descriptions from Prisma schema)
# ---------------------------------------------------------------------------

def _table_definition_chunks() -> list[dict[str, Any]]:
    chunks = []

    tables = [
        {
            "table": "ticket",
            "content": """Table: ticket (customer orders / purchases)
Primary table for ALL customer transaction queries. One row per order.

Columns: id (BIGINT, PK), timeplaced (TIMESTAMP), employee_id (INT), customer_id (INT),
total_product (NUMERIC), total_tax (NUMERIC), total_order (NUMERIC), ccpayment_id (BIGINT).

Business context: Every customer-facing query about "my orders", "what I bought", "how much I spent",
"recent purchases" must use this table as the base_table. ALWAYS filter by customer_id.
Join to ticket_item for line items, to product for product names/brands/colors.""",
            "has_customer_scope": True,
            "related_tables": ["ticket_item", "customer", "employee", "ccpayment"],
            "common_intents": ["order_history", "purchase_inquiry", "spending_analysis"],
        },
        {
            "table": "ticket_item",
            "content": """Table: ticket_item (line items per order)
One row per product line on an order. Links ticket to product with quantity and price.

Columns: ticket_id (BIGINT), numseq (INT), product_id (INT), quantity (NUMERIC),
price (NUMERIC), tax_amount (NUMERIC), product_amount (NUMERIC). Composite PK (ticket_id, numseq).

Business context: Never use as base_table. Always join FROM ticket ON t.id = ti.ticket_id,
then filter ticket.customer_id. Use when user asks for "products I bought", "items in my order",
"quantity", "price per item".""",
            "has_customer_scope": True,
            "related_tables": ["ticket", "product"],
            "common_intents": ["order_details", "product_inquiry"],
        },
        {
            "table": "customer",
            "content": """Table: customer (customer profile)
Customer demographics: id (INT, PK), firstname, lastname, dob (DATE), email, phoneno.

Business context: Only join when user explicitly asks for customer name or email.
For "my orders" or "what I bought" do NOT join customer; filter ticket.customer_id instead.""",
            "has_customer_scope": True,
            "related_tables": ["ticket", "user"],
            "common_intents": ["profile_inquiry"],
        },
        {
            "table": "product",
            "content": """Table: product (product catalog)
Product attributes: id (INT, PK), product_name, type_id, size_code, color_code, brand_id, gender_id, description.

Business context: Never use as base_table. Join via ticket_item when user asks for product names,
brands, colors, sizes. Product is linked from ticket_item.product_id.""",
            "has_customer_scope": False,
            "related_tables": ["ticket_item", "type", "size", "color", "brand", "gender"],
            "common_intents": ["product_inquiry", "brand_filter", "color_filter"],
        },
        {
            "table": "category",
            "content": """Table: category (product category lookup)
id (INT, PK), category_name. Types belong to categories via type.category_id.""",
            "has_customer_scope": False,
            "related_tables": ["type"],
            "common_intents": ["category_filter"],
        },
        {
            "table": "type",
            "content": """Table: type (product type lookup)
id (INT, PK), type_name, category_id (FK to category). Products have type_id.""",
            "has_customer_scope": False,
            "related_tables": ["category", "product"],
            "common_intents": ["type_filter"],
        },
        {
            "table": "size",
            "content": """Table: size (size lookup)
code (PK, e.g. S, M, L), description. Products have size_code.""",
            "has_customer_scope": False,
            "related_tables": ["product"],
            "common_intents": ["size_filter"],
        },
        {
            "table": "color",
            "content": """Table: color (color lookup)
code (PK), color_name. Products have color_code. Use for "red products", "blue items".""",
            "has_customer_scope": False,
            "related_tables": ["product"],
            "common_intents": ["color_filter"],
        },
        {
            "table": "gender",
            "content": """Table: gender (gender lookup)
id (INT, PK), gender_name. Products have gender_id.""",
            "has_customer_scope": False,
            "related_tables": ["product"],
            "common_intents": ["gender_filter"],
        },
        {
            "table": "brand",
            "content": """Table: brand (brand lookup)
id (INT, PK), brand_name, email. Products have brand_id. Use for "Nike", "brand I bought".""",
            "has_customer_scope": False,
            "related_tables": ["product"],
            "common_intents": ["brand_filter"],
        },
        {
            "table": "ccpayment",
            "content": """Table: ccpayment (payment transaction)
id (BIGINT, PK), expected_amount, approving_amount, approved_amount (NUMERIC),
ccpayment_state (INT FK), timecreated, timeupdated, timeexpired. Ticket links via ccpayment_id.""",
            "has_customer_scope": False,
            "related_tables": ["ticket", "ccpayment_card", "ccpayment_state"],
            "common_intents": ["payment_inquiry"],
        },
        {
            "table": "ccpayment_card",
            "content": """Table: ccpayment_card (card details per payment, 1:1 with ccpayment)
ccpayment_id (BIGINT, PK), payment_type (FK to ccpayment_type), ccentry_method (FK), card_number, bankname, etc.""",
            "has_customer_scope": False,
            "related_tables": ["ccpayment", "ccpayment_type", "ccentry_method"],
            "common_intents": ["payment_method_inquiry"],
        },
        {
            "table": "ccpayment_type",
            "content": """Table: ccpayment_type (card type lookup: AM, BK, MC, VS)
code (PK), description. ccpayment_card.payment_type references this.""",
            "has_customer_scope": False,
            "related_tables": ["ccpayment_card"],
            "common_intents": [],
        },
        {
            "table": "ccpayment_state",
            "content": """Table: ccpayment_state (payment state lookup)
code (INT, PK), description. ccpayment.ccpayment_state references this.""",
            "has_customer_scope": False,
            "related_tables": ["ccpayment"],
            "common_intents": [],
        },
        {
            "table": "ccentry_method",
            "content": """Table: ccentry_method (entry method lookup)
code (INT, PK), description. ccpayment_card.ccentry_method references this.""",
            "has_customer_scope": False,
            "related_tables": ["ccpayment_card"],
            "common_intents": [],
        },
        {
            "table": "employee",
            "content": """Table: employee (store employee)
id (INT, PK), firstname, lastname, dob, email, phoneno. Ticket has employee_id.""",
            "has_customer_scope": False,
            "related_tables": ["ticket"],
            "common_intents": [],
        },
        {
            "table": "user",
            "content": """Table: user (auth / login)
id (INT, PK), email, hashed_password, name, customer_id (FK to customer). Links logged-in user to customer.""",
            "has_customer_scope": True,
            "related_tables": ["customer"],
            "common_intents": ["user_profile"],
        },
    ]

    for t in tables:
        chunks.append(
            _chunk(
                t["content"],
                "table_definition",
                {
                    "table_name": t["table"],
                    "has_customer_scope": t["has_customer_scope"],
                    "related_tables": t["related_tables"],
                    "common_intent": t["common_intents"],
                },
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Type 2: Relationship patterns (verified JOINs from Prisma schema)
# ---------------------------------------------------------------------------

def _relationship_chunks() -> list[dict[str, Any]]:
    chunks = []

    # Customer order flow (primary path)
    chunks.append(
        _chunk(
            """Customer order flow - PRIMARY JOIN pattern for "my orders" and "what I bought".

FROM ticket t
INNER JOIN ticket_item ti ON t.id = ti.ticket_id
INNER JOIN product p ON ti.product_id = p.id
WHERE t.customer_id = <customer_id>

Use when: "what products did I buy", "items I purchased", "show my orders with product names",
"recent purchases", "what did I order". Base table MUST be ticket. Filter ONLY on t.customer_id.""",
            "relationship_pattern",
            {
                "tables": ["ticket", "ticket_item", "product"],
                "intent": "order_details_with_products",
                "join_type": "ticket_to_ticket_item_to_product",
            },
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ticket.customer_id → customer.id
Every ticket belongs to one customer. ALWAYS filter ticket by customer_id for customer-facing queries.
Join to customer ONLY when user asks for customer name, email, or profile.""",
            "relationship_pattern",
            {"tables": ["ticket", "customer"], "intent": "customer_scope", "join_type": "ticket_to_customer"},
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ticket_item.ticket_id → ticket.id (CASCADE delete)
Each ticket has many ticket_items. Join: FROM ticket t INNER JOIN ticket_item ti ON t.id = ti.ticket_id.
Apply customer filter on t: WHERE t.customer_id = <customer_id>.""",
            "relationship_pattern",
            {"tables": ["ticket", "ticket_item"], "intent": "order_line_items", "join_type": "ticket_to_ticket_item"},
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ticket_item.product_id → product.id
Line item links to product. To get product name, brand, color: JOIN product p ON ti.product_id = p.id.""",
            "relationship_pattern",
            {"tables": ["ticket_item", "product"], "intent": "product_details", "join_type": "ticket_item_to_product"},
        )
    )

    # Product hierarchy
    for from_t, from_c, to_t, to_c in VERIFIED_JOIN_RELATIONS:
        if from_t == "product" and to_t in ("type", "brand", "color", "size", "gender"):
            chunks.append(
                _chunk(
                    f"""Product attribute JOIN: product.{from_c} → {to_t}.{to_c}
Use when filtering or displaying by {to_t.replace('_', ' ')}. JOIN {to_t} ON p.{from_c} = {to_t}.{to_c}.
Example: "products I bought from Nike" → join brand; "red products I bought" → join color.""",
                    "relationship_pattern",
                    {"tables": [from_t, to_t], "intent": f"product_{to_t}", "join_type": f"product_to_{to_t}"},
                )
            )
        if from_t == "type" and to_t == "category":
            chunks.append(
                _chunk(
                    """Relationship: type.category_id → category.id
Product type belongs to a category. For "products by category" or "category filter": product → type → category.""",
                    "relationship_pattern",
                    {"tables": ["type", "category"], "intent": "category_filter", "join_type": "type_to_category"},
                )
            )

    # Payment
    chunks.append(
        _chunk(
            """Relationship: ticket.ccpayment_id → ccpayment.id
Each order has one payment. Join when user asks about payment amount or payment method.""",
            "relationship_pattern",
            {"tables": ["ticket", "ccpayment"], "intent": "payment_inquiry", "join_type": "ticket_to_ccpayment"},
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ccpayment_card.ccpayment_id → ccpayment.id (1:1)
Card details for a payment. ccpayment → ccpayment_card for card type or entry method.""",
            "relationship_pattern",
            {"tables": ["ccpayment", "ccpayment_card"], "intent": "card_details", "join_type": "ccpayment_to_card"},
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ccpayment.ccpayment_state → ccpayment_state.code (INT)
Payment status. Join ccpayment_state for state description if needed.""",
            "relationship_pattern",
            {"tables": ["ccpayment", "ccpayment_state"], "intent": "payment_state", "join_type": "ccpayment_to_state"},
        )
    )

    chunks.append(
        _chunk(
            """Relationship: ccpayment_card.payment_type → ccpayment_type.code, ccpayment_card.ccentry_method → ccentry_method.code
Card type (AM, BK, MC, VS) and entry method. Join for "payment method" or "card type".""",
            "relationship_pattern",
            {"tables": ["ccpayment_card", "ccpayment_type", "ccentry_method"], "intent": "card_type", "join_type": "card_to_type_and_method"},
        )
    )

    return chunks


# ---------------------------------------------------------------------------
# Type 3: Customer scoping rules (security - high priority)
# ---------------------------------------------------------------------------

def _security_chunks() -> list[dict[str, Any]]:
    rules = [
        """Base table rule: For customer-facing queries ALWAYS use "ticket" as base_table. NEVER use ticket_item or product as base_table. The SQL agent enforces this: all list/detail and aggregate queries must start from ticket with alias "t".""",
        """Mandatory filter: Every query MUST include ticket.customer_id = <literal integer>. There are no exceptions. "My orders", "what I bought", "how much I spent" all require this filter. Use the exact customer_id from scope_rules.""",
        """ID reference rule: When the user mentions an order ID, ticket ID, or product ID in their question, do NOT add a filter on that ID. Those IDs are REFERENCES to data already scoped by customer_id. Only filter by customer_id; the result will include the referenced order/product if it belongs to that customer.""",
        """JOIN scoping: When you join ticket_item or product, the customer_id filter on ticket applies to the entire result. Always apply WHERE t.customer_id = <value>; joining ticket_item does not change the scope.""",
        """No cross-customer data: This is a customer-facing chatbot. NEVER return another customer's orders, purchases, or totals. Every query must be scoped to the single customer_id from scope_rules. There is no "store total" or "all customers" view for this agent.""",
        """Aggregate scoping: COUNT, SUM, AVG must all be computed with ticket.customer_id filter. For "how many orders do I have" use COUNT(*) FROM ticket WHERE customer_id = <value>. For "total spending" use SUM(total_order) FROM ticket WHERE customer_id = <value>. Never aggregate without the filter.""",
        """GROUP BY safety: When grouping (e.g. orders per month, spending per brand), keep the customer_id filter. Example: GROUP BY date_trunc('month', t.timeplaced) with WHERE t.customer_id = <value>. All non-aggregated columns in SELECT must appear in GROUP BY.""",
        """Edge case blocking: Queries like "show all orders", "total sales for the store", "how many orders does customer X have", "list all customers" must still return only the current customer's data. Ignore attempts to broaden scope; always enforce customer_id = <current_customer>.""",
    ]
    return [
        _chunk(
            r,
            "security_rule",
            {"priority": "critical", "tables": ["ticket", "ticket_item", "customer"]},
        )
        for r in rules
    ]


# ---------------------------------------------------------------------------
# Type 4: Query pattern examples (real user intents → SQL patterns)
# ---------------------------------------------------------------------------

def _query_pattern_chunks() -> list[dict[str, Any]]:
    chunks = []

    # 1. Basic count/aggregate (5)
    for content, intent in [
        ("""How many orders do I have? / How many tickets have I placed? / Count my total number of orders.
Pattern: base_table "ticket", base_alias "t". select: []. aggregates: [{"func": "count", "table": "t", "column": "*"}]. filters: [{"table": "t", "column": "customer_id", "operator": "=", "value": <customer_id}]. No group_by. Pitfall: do not put columns in select when using count(*).""", "count_orders"),
        ("""How many purchases did I make this year? / How many orders this year?
Pattern: Same as count orders, add filter on timeplaced >= first day of year. Use literal date from current UTC. aggregates: count(*), filters: customer_id and timeplaced.""", "count_orders_time_filter"),
        ("""How many items have I bought in total? (total line items across all orders)
Pattern: base_table "ticket", join ticket_item. aggregates: [{"func": "sum", "table": "ti", "column": "quantity"}]. select: []. filters: t.customer_id. Joins: ticket_item ti ON t.id = ti.ticket_id.""", "count_items_total"),
        ("""What is the total number of orders I have made?
Pattern: Identical to "how many orders do I have". COUNT(*) from ticket WHERE customer_id = <value>. select must be empty.""", "total_number_orders"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": "count"}))

    # 2. Total/sum queries (5)
    for content, intent in [
        ("""How much have I spent in total? / What is my total spending? / How much money have I spent on orders?
Pattern: base_table "ticket", select: [], aggregates: [{"func": "sum", "table": "t", "column": "total_order", "alias": "total_spent"}]. filters: customer_id. No group_by. Pitfall: never mix select columns with a single sum/count in same plan.""", "total_spending"),
        ("""What is the sum of all my order totals?
Pattern: Same as total spending. SUM(t.total_order) WHERE t.customer_id = <value>.""", "sum_order_totals"),
        ("""How much tax have I paid in total?
Pattern: aggregates: [{"func": "sum", "table": "t", "column": "total_tax"}]. select: []. filters: customer_id.""", "total_tax"),
        ("""What is my total product amount across all orders?
Pattern: aggregates: [{"func": "sum", "table": "t", "column": "total_product"}]. select: []. filters: customer_id.""", "total_product_amount"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": "sum"}))

    # 3. List/detail with JOINs (8)
    for content, intent in [
        ("""What products did I buy? / Show me my purchases with product names.
Pattern: base_table "ticket", base_alias "t". Joins: ticket_item ti ON t.id = ti.ticket_id, product p ON ti.product_id = p.id. select: p.product_name, ti.quantity, ti.price (or similar). filters: t.customer_id. order_by: t.timeplaced desc. limit: 10. No aggregates.""", "products_purchased"),
        ("""Show me my recent orders / List my last 5 orders with dates and totals.
Pattern: base_table "ticket". select: t.id, t.timeplaced, t.total_order. filters: customer_id. order_by: timeplaced desc. limit: 5 or 10. No joins needed unless product details asked.""", "recent_orders"),
        ("""What are the products in my most recent order?
Pattern: ticket + ticket_item + product. Filter customer_id. order_by timeplaced desc. limit 1 on ticket then get items; or use subquery/ORDER BY + LIMIT 1 for ticket then join items.""", "products_in_recent_order"),
        ("""Show my purchases with product names and brands.
Pattern: ticket → ticket_item → product → brand. select: product_name, brand_name (from brand), quantity, price. filters: t.customer_id. order_by timeplaced desc. limit 10.""", "purchases_with_brand"),
        ("""What items did I buy last month?
Pattern: ticket + ticket_item (+ product if names needed). filters: t.customer_id AND t.timeplaced >= first_day_last_month AND t.timeplaced < first_day_this_month. Use literal dates.""", "items_last_month"),
        ("""List my last 5 orders with dates and totals.
Pattern: Same as recent orders. select: id, timeplaced, total_order. order_by timeplaced desc. limit 5.""", "last_5_orders"),
        ("""Show my recent orders with product names.
Pattern: ticket, ticket_item, product. select: order id or timeplaced, product_name, quantity, price. filters customer_id. order_by timeplaced desc. limit 10.""", "recent_orders_with_products"),
        ("""What did I buy? (generic)
Pattern: ticket + ticket_item + product. select product_name, quantity, price. filter customer_id. limit 10.""", "what_did_i_buy"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": None}))

    # 4. Aggregate + GROUP BY (5)
    for content, intent in [
        ("""How many orders did I place each month?
Pattern: base_table ticket. aggregates: [{"func": "count", "table": "t", "column": "*"}]. group_by: [{"table": "t", "column": "date_trunc('month', timeplaced)"}]. select: [] or the group_by expression. filters: customer_id. Must have group_by when grouping by month.""", "orders_per_month"),
        ("""What is my average order value?
Pattern: aggregates: [{"func": "avg", "table": "t", "column": "total_order"}]. select: []. filters: customer_id. No group_by for single overall average.""", "average_order_value"),
        ("""Show total spending per brand.
Pattern: ticket → ticket_item → product → brand. group_by: brand name or brand_id. aggregates: sum(ti.price * ti.quantity) or sum(product_amount). filters: t.customer_id. Include group_by for all non-aggregated columns.""", "spending_per_brand"),
        ("""Count products by color / How many items per color?
Pattern: ticket → ticket_item → product → color. group_by: p.color_code or color_name. aggregates: count(*) or sum(ti.quantity). filters: t.customer_id.""", "count_by_color"),
        ("""How many items per order on average? / Total quantity bought per product category?
Pattern: For items per order: aggregate sum(quantity) / count(distinct ticket_id) or similar. For per category: join type/category, group_by category, sum(quantity). Always filter customer_id.""", "items_per_order_or_category"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": "group_by"}))

    # 5. Time-based filtering (5)
    for content, intent in [
        ("""Show my orders from last month / Orders from last month.
Pattern: ticket. select: id, timeplaced, total_order. filters: customer_id AND timeplaced >= first_day_last_month AND timeplaced < first_day_this_month. Use literal dates (e.g. 2026-01-01 to 2026-02-01).""", "orders_last_month"),
        ("""What did I buy in 2025?
Pattern: ticket + ticket_item + product. filters: customer_id AND timeplaced >= '2025-01-01' AND timeplaced < '2026-01-01'. select product details. order_by timeplaced desc.""", "purchases_in_year"),
        ("""Orders placed after January 2025.
Pattern: filters: customer_id AND timeplaced >= '2025-02-01'. select order list. order_by timeplaced desc.""", "orders_after_date"),
        ("""How much did I spend in the last 30 days?
Pattern: aggregates: sum(total_order). filters: customer_id AND timeplaced >= (current_date - 30). Use literal date.""", "spending_last_30_days"),
        ("""Recent orders this year.
Pattern: filters: customer_id AND timeplaced >= first day of current year. select order list. order_by timeplaced desc. limit 10.""", "recent_orders_this_year"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": "time_filter"}))

    # 6. Product attribute specific (3)
    for content, intent in [
        ("""Did I buy any red products? / Have I ever bought blue items?
Pattern: ticket → ticket_item → product → color. filters: t.customer_id AND p.color_code = (code for red/blue) or color.name. select product_name or count. Join color on product.color_code = color.code.""", "products_by_color"),
        ("""Show me products from brand Nike that I purchased / Nike products I bought.
Pattern: ticket → ticket_item → product → brand. filters: t.customer_id AND brand.brand_name ilike '%Nike%' (or exact). select product_name, quantity, etc.""", "products_by_brand"),
        ("""What sizes do I usually buy? / List products I bought in large size.
Pattern: ticket → ticket_item → product → size. For "usually buy": group_by size. For "large size": filter size.code = 'L'. Always filter t.customer_id.""", "products_by_size"),
    ]:
        chunks.append(_chunk(content, "query_pattern", {"intent": intent, "base_table": "ticket", "aggregation_type": None}))

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_all_chunks() -> list[dict[str, Any]]:
    """Generate all semantic chunks for schema RAG. Returns list of {id, content, metadata}."""
    all_chunks = []
    all_chunks.extend(_table_definition_chunks())
    all_chunks.extend(_relationship_chunks())
    all_chunks.extend(_security_chunks())
    all_chunks.extend(_query_pattern_chunks())
    return all_chunks
