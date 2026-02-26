-- CreateTable
CREATE TABLE "chat_event_log" (
    "id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "turn_index" INTEGER NOT NULL,
    "event_type" TEXT NOT NULL,
    "message_id" TEXT,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "content_hash" TEXT,
    "content_redacted" TEXT,
    "payload_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chat_event_log_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "chat_feedback" (
    "id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "message_id" TEXT,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "feedback_type" TEXT NOT NULL,
    "content_hash" TEXT,
    "content_redacted" TEXT,
    "payload_json" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chat_feedback_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "knowledge_gap_items" (
    "id" TEXT NOT NULL,
    "topic_key" TEXT NOT NULL,
    "intent" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'NEW',
    "trigger_source" TEXT NOT NULL,
    "score" INTEGER NOT NULL,
    "occurrence_count" INTEGER NOT NULL DEFAULT 1,
    "first_seen_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_seen_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_request_id" TEXT,
    "last_session_id" TEXT,

    CONSTRAINT "knowledge_gap_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "session_features" (
    "session_id" TEXT NOT NULL,
    "user_id" INTEGER,
    "customer_id" INTEGER,
    "turn_index" INTEGER NOT NULL DEFAULT 0,
    "rephrase_count" INTEGER NOT NULL DEFAULT 0,
    "explain_clicks" INTEGER NOT NULL DEFAULT 0,
    "handoff_clicks" INTEGER NOT NULL DEFAULT 0,
    "lang_pref" TEXT,
    "short_answer_pref" BOOLEAN,
    "last_tqs" INTEGER,
    "last_kgs" INTEGER,
    "clarify_mode" BOOLEAN NOT NULL DEFAULT false,
    "rag_top_k_override" INTEGER,
    "query_expansion_enabled" BOOLEAN NOT NULL DEFAULT false,
    "wrqs_weight_overrides_json" TEXT,
    "adaptation_expires_turn" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "session_features_pkey" PRIMARY KEY ("session_id")
);

-- CreateIndex
CREATE INDEX "chat_event_log_request_id_idx" ON "chat_event_log"("request_id");

-- CreateIndex
CREATE INDEX "chat_event_log_session_id_turn_index_idx" ON "chat_event_log"("session_id", "turn_index");

-- CreateIndex
CREATE INDEX "chat_event_log_event_type_created_at_idx" ON "chat_event_log"("event_type", "created_at");

-- CreateIndex
CREATE INDEX "chat_event_log_user_id_created_at_idx" ON "chat_event_log"("user_id", "created_at");

-- CreateIndex
CREATE INDEX "chat_feedback_session_id_created_at_idx" ON "chat_feedback"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "chat_feedback_message_id_created_at_idx" ON "chat_feedback"("message_id", "created_at");

-- CreateIndex
CREATE INDEX "chat_feedback_feedback_type_created_at_idx" ON "chat_feedback"("feedback_type", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "knowledge_gap_items_topic_key_intent_key" ON "knowledge_gap_items"("topic_key", "intent");

-- CreateIndex
CREATE INDEX "knowledge_gap_items_status_last_seen_at_idx" ON "knowledge_gap_items"("status", "last_seen_at");

-- CreateIndex
CREATE INDEX "knowledge_gap_items_score_last_seen_at_idx" ON "knowledge_gap_items"("score", "last_seen_at");

-- CreateIndex
CREATE INDEX "session_features_user_id_updated_at_idx" ON "session_features"("user_id", "updated_at");

-- CreateIndex
CREATE INDEX "session_features_customer_id_updated_at_idx" ON "session_features"("customer_id", "updated_at");

-- AddForeignKey
ALTER TABLE "chat_event_log" ADD CONSTRAINT "chat_event_log_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_event_log" ADD CONSTRAINT "chat_event_log_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "chat_message"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_event_log" ADD CONSTRAINT "chat_event_log_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_event_log" ADD CONSTRAINT "chat_event_log_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "chat_message"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session_features" ADD CONSTRAINT "session_features_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "chat_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session_features" ADD CONSTRAINT "session_features_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session_features" ADD CONSTRAINT "session_features_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;
