-- CreateTable
CREATE TABLE "policy_audit" (
    "id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "user_id" INTEGER,
    "user_state" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "policy_intent" TEXT NOT NULL,
    "policy_domain" TEXT NOT NULL,
    "classifier_confidence" DOUBLE PRECISION,
    "allow" BOOLEAN NOT NULL,
    "reason_code" TEXT,
    "decision_source" TEXT NOT NULL,
    "trace_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "policy_audit_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "policy_audit_request_id_idx" ON "policy_audit"("request_id");

-- CreateIndex
CREATE INDEX "policy_audit_session_id_created_at_idx" ON "policy_audit"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "policy_audit_user_id_created_at_idx" ON "policy_audit"("user_id", "created_at");

-- AddForeignKey
ALTER TABLE "policy_audit" ADD CONSTRAINT "policy_audit_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;
