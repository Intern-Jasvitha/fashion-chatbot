-- AlterTable
ALTER TABLE "knowledge_gap_items"
  ADD COLUMN "owner" TEXT,
  ADD COLUMN "resolution_notes" TEXT,
  ADD COLUMN "resolved_at" TIMESTAMP(3),
  ADD COLUMN "verified_at" TIMESTAMP(3),
  ADD COLUMN "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- CreateTable
CREATE TABLE "correction_memory" (
    "id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "message_id" TEXT,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "source_feedback_id" TEXT,
    "memory_scope" TEXT NOT NULL,
    "instruction_redacted" TEXT NOT NULL,
    "instruction_hash" TEXT NOT NULL,
    "consent_long_term" BOOLEAN NOT NULL DEFAULT false,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "correction_memory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "handoff_queue" (
    "id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "message_id" TEXT,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "reason_code" TEXT NOT NULL,
    "priority" TEXT NOT NULL DEFAULT 'MEDIUM',
    "status" TEXT NOT NULL DEFAULT 'OPEN',
    "payload_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "handoff_queue_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "learning_job_run" (
    "id" TEXT NOT NULL,
    "job_type" TEXT NOT NULL,
    "window_start" DATE NOT NULL,
    "window_end" DATE NOT NULL,
    "status" TEXT NOT NULL,
    "summary_json" TEXT,
    "config_hash" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "learning_job_run_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "learning_daily_metrics" (
    "id" TEXT NOT NULL,
    "metric_date" DATE NOT NULL,
    "avg_tqs" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "avg_kgs" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "rephrase_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "handoff_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "feedback_down_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "learning_daily_metrics_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "wrqs_config_version" (
    "id" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "positive_weights_json" TEXT NOT NULL,
    "penalty_weights_json" TEXT NOT NULL,
    "source_window_start" DATE NOT NULL,
    "source_window_end" DATE NOT NULL,
    "config_hash" TEXT NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "wrqs_config_version_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "correction_memory_session_id_created_at_idx" ON "correction_memory"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "correction_memory_user_id_created_at_idx" ON "correction_memory"("user_id", "created_at");

-- CreateIndex
CREATE INDEX "correction_memory_customer_id_created_at_idx" ON "correction_memory"("customer_id", "created_at");

-- CreateIndex
CREATE INDEX "correction_memory_memory_scope_created_at_idx" ON "correction_memory"("memory_scope", "created_at");

-- CreateIndex
CREATE INDEX "handoff_queue_status_created_at_idx" ON "handoff_queue"("status", "created_at");

-- CreateIndex
CREATE INDEX "handoff_queue_session_id_created_at_idx" ON "handoff_queue"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "handoff_queue_user_id_created_at_idx" ON "handoff_queue"("user_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "learning_job_run_job_type_window_start_window_end_key" ON "learning_job_run"("job_type", "window_start", "window_end");

-- CreateIndex
CREATE INDEX "learning_job_run_job_type_created_at_idx" ON "learning_job_run"("job_type", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "learning_daily_metrics_metric_date_key" ON "learning_daily_metrics"("metric_date");

-- CreateIndex
CREATE UNIQUE INDEX "wrqs_config_version_version_key" ON "wrqs_config_version"("version");

-- CreateIndex
CREATE INDEX "wrqs_config_version_is_active_created_at_idx" ON "wrqs_config_version"("is_active", "created_at");

-- AddForeignKey
ALTER TABLE "correction_memory" ADD CONSTRAINT "correction_memory_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "correction_memory" ADD CONSTRAINT "correction_memory_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "chat_message"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "correction_memory" ADD CONSTRAINT "correction_memory_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "correction_memory" ADD CONSTRAINT "correction_memory_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "correction_memory" ADD CONSTRAINT "correction_memory_source_feedback_id_fkey" FOREIGN KEY ("source_feedback_id") REFERENCES "chat_feedback"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "handoff_queue" ADD CONSTRAINT "handoff_queue_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "handoff_queue" ADD CONSTRAINT "handoff_queue_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "chat_message"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "handoff_queue" ADD CONSTRAINT "handoff_queue_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "handoff_queue" ADD CONSTRAINT "handoff_queue_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;
