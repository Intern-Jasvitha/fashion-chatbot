/*
  Warnings:

  - You are about to drop the `Post` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `User` table. If the table is not empty, all the data it contains will be lost.

*/
-- DropForeignKey
ALTER TABLE "Post" DROP CONSTRAINT "Post_author_id_fkey";

-- DropTable
DROP TABLE "Post";

-- DropTable
DROP TABLE "User";

-- CreateTable
CREATE TABLE "category" (
    "id" INTEGER NOT NULL,
    "category_name" TEXT NOT NULL,

    CONSTRAINT "category_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "type" (
    "id" INTEGER NOT NULL,
    "type_name" TEXT NOT NULL,
    "category_id" INTEGER NOT NULL,

    CONSTRAINT "type_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "size" (
    "code" TEXT NOT NULL,
    "description" TEXT,

    CONSTRAINT "size_pkey" PRIMARY KEY ("code")
);

-- CreateTable
CREATE TABLE "color" (
    "code" TEXT NOT NULL,
    "color_name" TEXT NOT NULL,

    CONSTRAINT "color_pkey" PRIMARY KEY ("code")
);

-- CreateTable
CREATE TABLE "gender" (
    "id" INTEGER NOT NULL,
    "gender_name" TEXT NOT NULL,

    CONSTRAINT "gender_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "brand" (
    "id" INTEGER NOT NULL,
    "brand_name" TEXT NOT NULL,
    "email" TEXT,

    CONSTRAINT "brand_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ccpayment_type" (
    "code" TEXT NOT NULL,
    "description" TEXT,

    CONSTRAINT "ccpayment_type_pkey" PRIMARY KEY ("code")
);

-- CreateTable
CREATE TABLE "ccpayment_state" (
    "code" INTEGER NOT NULL,
    "description" TEXT,

    CONSTRAINT "ccpayment_state_pkey" PRIMARY KEY ("code")
);

-- CreateTable
CREATE TABLE "ccentry_method" (
    "code" INTEGER NOT NULL,
    "description" TEXT,

    CONSTRAINT "ccentry_method_pkey" PRIMARY KEY ("code")
);

-- CreateTable
CREATE TABLE "customer" (
    "id" INTEGER NOT NULL,
    "firstname" TEXT NOT NULL,
    "lastname" TEXT NOT NULL,
    "dob" DATE NOT NULL,
    "email" TEXT,
    "phoneno" TEXT,

    CONSTRAINT "customer_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "employee" (
    "id" INTEGER NOT NULL,
    "firstname" TEXT NOT NULL,
    "lastname" TEXT NOT NULL,
    "dob" DATE NOT NULL,
    "email" TEXT,
    "phoneno" TEXT,

    CONSTRAINT "employee_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ccpayment" (
    "id" BIGINT NOT NULL,
    "ccpaytran_id" BIGINT,
    "expected_amount" DECIMAL(18,5) NOT NULL,
    "approving_amount" DECIMAL(18,5) NOT NULL,
    "approved_amount" DECIMAL(18,5) NOT NULL,
    "ccpayment_state" INTEGER NOT NULL,
    "timecreated" TIMESTAMP(3) NOT NULL,
    "timeupdated" TIMESTAMP(3) NOT NULL,
    "timeexpired" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ccpayment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ccpayment_card" (
    "ccpayment_id" BIGINT NOT NULL,
    "payment_type" TEXT NOT NULL,
    "is_encrypt" TEXT,
    "card_number" TEXT,
    "bankname" TEXT,
    "ccexpdate" INTEGER,
    "ccentry_method" INTEGER NOT NULL,

    CONSTRAINT "ccpayment_card_pkey" PRIMARY KEY ("ccpayment_id")
);

-- CreateTable
CREATE TABLE "product" (
    "id" INTEGER NOT NULL,
    "type_id" INTEGER NOT NULL,
    "size_code" TEXT NOT NULL,
    "color_code" TEXT NOT NULL,
    "product_name" TEXT NOT NULL,
    "brand_id" INTEGER NOT NULL,
    "gender_id" INTEGER NOT NULL,
    "description" TEXT,

    CONSTRAINT "product_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ticket" (
    "id" BIGINT NOT NULL,
    "timeplaced" TIMESTAMP(3) NOT NULL,
    "employee_id" INTEGER NOT NULL,
    "customer_id" INTEGER NOT NULL,
    "total_product" DECIMAL(18,5) NOT NULL,
    "total_tax" DECIMAL(18,5) NOT NULL,
    "total_order" DECIMAL(18,5) NOT NULL,
    "ccpayment_id" BIGINT NOT NULL,

    CONSTRAINT "ticket_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ticket_item" (
    "ticket_id" BIGINT NOT NULL,
    "numseq" INTEGER NOT NULL,
    "product_id" INTEGER NOT NULL,
    "quantity" DECIMAL(18,5) NOT NULL,
    "price" DECIMAL(18,5) NOT NULL,
    "tax_amount" DECIMAL(18,5) NOT NULL,
    "product_amount" DECIMAL(18,5) NOT NULL,

    CONSTRAINT "ticket_item_pkey" PRIMARY KEY ("ticket_id","numseq")
);

-- CreateIndex
CREATE INDEX "type_category_id_idx" ON "type"("category_id");

-- CreateIndex
CREATE INDEX "ccpayment_ccpayment_state_idx" ON "ccpayment"("ccpayment_state");

-- CreateIndex
CREATE INDEX "ccpayment_card_payment_type_idx" ON "ccpayment_card"("payment_type");

-- CreateIndex
CREATE INDEX "ccpayment_card_ccentry_method_idx" ON "ccpayment_card"("ccentry_method");

-- CreateIndex
CREATE INDEX "product_type_id_idx" ON "product"("type_id");

-- CreateIndex
CREATE INDEX "product_size_code_idx" ON "product"("size_code");

-- CreateIndex
CREATE INDEX "product_color_code_idx" ON "product"("color_code");

-- CreateIndex
CREATE INDEX "product_brand_id_idx" ON "product"("brand_id");

-- CreateIndex
CREATE INDEX "product_gender_id_idx" ON "product"("gender_id");

-- CreateIndex
CREATE INDEX "ticket_employee_id_idx" ON "ticket"("employee_id");

-- CreateIndex
CREATE INDEX "ticket_customer_id_idx" ON "ticket"("customer_id");

-- CreateIndex
CREATE INDEX "ticket_ccpayment_id_idx" ON "ticket"("ccpayment_id");

-- CreateIndex
CREATE INDEX "ticket_timeplaced_idx" ON "ticket"("timeplaced");

-- CreateIndex
CREATE INDEX "ticket_item_product_id_idx" ON "ticket_item"("product_id");

-- AddForeignKey
ALTER TABLE "type" ADD CONSTRAINT "type_category_id_fkey" FOREIGN KEY ("category_id") REFERENCES "category"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ccpayment" ADD CONSTRAINT "ccpayment_ccpayment_state_fkey" FOREIGN KEY ("ccpayment_state") REFERENCES "ccpayment_state"("code") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ccpayment_card" ADD CONSTRAINT "ccpayment_card_ccpayment_id_fkey" FOREIGN KEY ("ccpayment_id") REFERENCES "ccpayment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ccpayment_card" ADD CONSTRAINT "ccpayment_card_payment_type_fkey" FOREIGN KEY ("payment_type") REFERENCES "ccpayment_type"("code") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ccpayment_card" ADD CONSTRAINT "ccpayment_card_ccentry_method_fkey" FOREIGN KEY ("ccentry_method") REFERENCES "ccentry_method"("code") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product" ADD CONSTRAINT "product_type_id_fkey" FOREIGN KEY ("type_id") REFERENCES "type"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product" ADD CONSTRAINT "product_size_code_fkey" FOREIGN KEY ("size_code") REFERENCES "size"("code") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product" ADD CONSTRAINT "product_color_code_fkey" FOREIGN KEY ("color_code") REFERENCES "color"("code") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product" ADD CONSTRAINT "product_brand_id_fkey" FOREIGN KEY ("brand_id") REFERENCES "brand"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product" ADD CONSTRAINT "product_gender_id_fkey" FOREIGN KEY ("gender_id") REFERENCES "gender"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ticket" ADD CONSTRAINT "ticket_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "employee"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ticket" ADD CONSTRAINT "ticket_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ticket" ADD CONSTRAINT "ticket_ccpayment_id_fkey" FOREIGN KEY ("ccpayment_id") REFERENCES "ccpayment"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ticket_item" ADD CONSTRAINT "ticket_item_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "ticket"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ticket_item" ADD CONSTRAINT "ticket_item_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "product"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
