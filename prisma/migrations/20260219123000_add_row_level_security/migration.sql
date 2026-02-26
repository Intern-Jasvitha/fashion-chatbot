-- Enable and force RLS for user-scoped data access
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user" FORCE ROW LEVEL SECURITY;

ALTER TABLE "customer" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "customer" FORCE ROW LEVEL SECURITY;

ALTER TABLE "ticket" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "ticket" FORCE ROW LEVEL SECURITY;

ALTER TABLE "ticket_item" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "ticket_item" FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_scope_select ON "user";
CREATE POLICY user_scope_select ON "user"
FOR SELECT
USING (
  "id" = NULLIF(current_setting('app.user_id', true), '')::INTEGER
);

DROP POLICY IF EXISTS customer_scope_select ON "customer";
CREATE POLICY customer_scope_select ON "customer"
FOR SELECT
USING (
  "id" = NULLIF(current_setting('app.customer_id', true), '')::INTEGER
);

DROP POLICY IF EXISTS ticket_scope_select ON "ticket";
CREATE POLICY ticket_scope_select ON "ticket"
FOR SELECT
USING (
  "customer_id" = NULLIF(current_setting('app.customer_id', true), '')::INTEGER
);

DROP POLICY IF EXISTS ticket_item_scope_select ON "ticket_item";
CREATE POLICY ticket_item_scope_select ON "ticket_item"
FOR SELECT
USING (
  EXISTS (
    SELECT 1
    FROM "ticket" t
    WHERE t."id" = "ticket_item"."ticket_id"
      AND t."customer_id" = NULLIF(current_setting('app.customer_id', true), '')::INTEGER
  )
);
