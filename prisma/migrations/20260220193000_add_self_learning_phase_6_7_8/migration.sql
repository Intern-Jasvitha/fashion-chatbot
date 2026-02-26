-- AlterTable
ALTER TABLE "chat_event_log"
  ADD COLUMN "learning_allowed" BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN "learning_exclusion_reason" TEXT;

-- AlterTable
ALTER TABLE "chat_feedback"
  ADD COLUMN "learning_allowed" BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN "learning_exclusion_reason" TEXT;

-- CreateTable
CREATE TABLE "learning_consent_preference" (
    "id" TEXT NOT NULL,
    "user_id" INTEGER NOT NULL,
    "customer_id" INTEGER,
    "long_term_personalization_opt_in" BOOLEAN NOT NULL DEFAULT false,
    "telemetry_learning_opt_in" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "learning_consent_preference_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "learning_exclusion_audit" (
    "id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "message_id" TEXT,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "exclusion_reason_code" TEXT NOT NULL,
    "policy_reason_code" TEXT,
    "content_hash" TEXT NOT NULL,
    "content_redacted" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "learning_exclusion_audit_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "release_component_version" (
    "id" TEXT NOT NULL,
    "component_key" TEXT NOT NULL,
    "version_hash" TEXT NOT NULL,
    "version_label" TEXT,
    "status" TEXT NOT NULL DEFAULT 'STABLE',
    "canary_percent" INTEGER NOT NULL DEFAULT 0,
    "source_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "release_component_version_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "golden_conversation_case" (
    "id" TEXT NOT NULL,
    "case_key" TEXT NOT NULL,
    "prompt_text" TEXT NOT NULL,
    "expected_allow" BOOLEAN NOT NULL,
    "expected_reason_code" TEXT,
    "expected_intent" TEXT,
    "forbidden_terms_json" TEXT,
    "required_terms_json" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "golden_conversation_case_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "golden_conversation_run" (
    "id" TEXT NOT NULL,
    "triggered_by_user_id" INTEGER,
    "run_window_days" INTEGER NOT NULL DEFAULT 7,
    "pass_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL,
    "fail_summary_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "golden_conversation_run_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "canary_rollout_run" (
    "id" TEXT NOT NULL,
    "triggered_by_user_id" INTEGER,
    "canary_percent" INTEGER NOT NULL,
    "baseline_metrics_json" TEXT,
    "current_metrics_json" TEXT,
    "rollback_triggered" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL,
    "notes" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "canary_rollout_run_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "learning_consent_preference_user_id_key" ON "learning_consent_preference"("user_id");

-- CreateIndex
CREATE INDEX "learning_consent_preference_customer_id_updated_at_idx" ON "learning_consent_preference"("customer_id", "updated_at");

-- CreateIndex
CREATE INDEX "learning_exclusion_audit_request_id_idx" ON "learning_exclusion_audit"("request_id");

-- CreateIndex
CREATE INDEX "learning_exclusion_audit_session_id_created_at_idx" ON "learning_exclusion_audit"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "learning_exclusion_audit_exclusion_reason_code_created_at_idx" ON "learning_exclusion_audit"("exclusion_reason_code", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "release_component_version_component_key_version_hash_key" ON "release_component_version"("component_key", "version_hash");

-- CreateIndex
CREATE INDEX "release_component_version_component_key_created_at_idx" ON "release_component_version"("component_key", "created_at");

-- CreateIndex
CREATE INDEX "release_component_version_status_updated_at_idx" ON "release_component_version"("status", "updated_at");

-- CreateIndex
CREATE UNIQUE INDEX "golden_conversation_case_case_key_key" ON "golden_conversation_case"("case_key");

-- CreateIndex
CREATE INDEX "golden_conversation_case_enabled_updated_at_idx" ON "golden_conversation_case"("enabled", "updated_at");

-- CreateIndex
CREATE INDEX "golden_conversation_run_status_created_at_idx" ON "golden_conversation_run"("status", "created_at");

-- CreateIndex
CREATE INDEX "canary_rollout_run_status_created_at_idx" ON "canary_rollout_run"("status", "created_at");

-- AddForeignKey
ALTER TABLE "learning_consent_preference" ADD CONSTRAINT "learning_consent_preference_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "learning_consent_preference" ADD CONSTRAINT "learning_consent_preference_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "learning_exclusion_audit" ADD CONSTRAINT "learning_exclusion_audit_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "learning_exclusion_audit" ADD CONSTRAINT "learning_exclusion_audit_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "chat_message"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "learning_exclusion_audit" ADD CONSTRAINT "learning_exclusion_audit_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "learning_exclusion_audit" ADD CONSTRAINT "learning_exclusion_audit_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "golden_conversation_run" ADD CONSTRAINT "golden_conversation_run_triggered_by_user_id_fkey" FOREIGN KEY ("triggered_by_user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "canary_rollout_run" ADD CONSTRAINT "canary_rollout_run_triggered_by_user_id_fkey" FOREIGN KEY ("triggered_by_user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Learning-safe projections
CREATE VIEW "learning_safe_event_view" AS
SELECT *
FROM "chat_event_log"
WHERE "learning_allowed" = true;

CREATE VIEW "learning_safe_feedback_view" AS
SELECT *
FROM "chat_feedback"
WHERE "learning_allowed" = true;
