# AI Fashion Agent

This document explains the app folder, each service, and the architecture in plain English. Order: overview, structure, entry point, core, API, graph, services, schemas, request flow.

---

## What the project does

The app is an AI fashion assistant API. A user sends a chat message. The system decides whether the request is allowed (policy), which agent should answer (SQL, RAG, or both), then runs that agent and returns one answer. It uses PostgreSQL (Prisma) for data and sessions, Qdrant for vector search, and an external LLM for chat.

---

## Stack: Docker, database, vector DB, LLM, and related services

What the project uses and what runs where.

**Docker (docker-compose.yml)**  
- **PostgreSQL**: Image `postgres:16`. Container name `ai-fashion-postgres_db`. Port 5438 on host maps to 5432. Used for app data, sessions, and LangGraph checkpointer.  
- **Qdrant**: Image `qdrant/qdrant:latest`. Container name `ai-fashion-qdrant_db`. Ports 6333 and 6334. Used for vector search.  
- The FastAPI app itself is not in this compose file; you run it on the host (e.g. `uvicorn app.main:app`).

**Database**  
- **PostgreSQL 16**. Connection via `DATABASE_URL` (e.g. `postgresql://ai-fashion:ai-fashion@localhost:5438/ai-fashiondb`).  
- **ORM**: Prisma. Schema in `prisma/schema.prisma`. Tables include User, Customer, ChatSession, ChatMessage, chat_event_log, policy audit, learning, release, and others.  
- **LangGraph checkpointer**: AsyncPostgresSaver uses the same `DATABASE_URL` to persist conversation state per thread (session).

**Vector database**  
- **Qdrant**. Configured with `QDRANT_HOST`, `QDRANT_PORT` (e.g. 6333), `QDRANT_COLLECTION_NAME`.  
- Used for: (1) RAG document retrieval (main collection named in config), (2) schema RAG for the SQL agent (collection `sql-agent`).  
- Populated by scripts (e.g. load PDFs for RAG, load schema chunks for sql-agent); the app only reads at runtime.

**LLM (chat)**  
- **Any HTTP chat API** pointed at `LLAMA_URL`. No built-in model.  
- Supports **OpenAI-compatible** (e.g. OpenAI, vLLM, LiteLLM) and **Llama-style** (e.g. llama.cpp server, Ollama) request/response shapes.  
- Used for: intent routing, policy classification (optional), SQL generation, RAG answer generation, hybrid synthesis, and any other LLM call in the graph.

**Embeddings**  
- **External embedding API** at `EMBEDDING_URL`. App sends `POST {"text": ["..."]}` and expects a vector (or list of vectors). `EMBEDDING_DIMENSION` must match the model.  
- Used for: RAG query embedding, schema RAG query embedding. Not provided by the app; you run a separate embedding service.

**TTS (voice)**  
- **Option A**: VibeVoice. When `ISVIBEVOICE=true`, `POST /voice/tts` calls `VIBEVOICE_URL` (default `http://localhost:3000`) to synthesize speech.  
- **Option B**: OpenAI TTS. When `ISVIBEVOICE=false`, uses `OPENAI_API_KEY` and the OpenAI speech API.

**Summary table**

| Component        | What we use                          | Where it runs / config              |
|-----------------|--------------------------------------|-------------------------------------|
| App server       | FastAPI, Uvicorn                     | Host (not in docker-compose)        |
| Database         | PostgreSQL 16, Prisma                | Docker: postgres:16, port 5438      |
| Vector DB        | Qdrant                               | Docker: qdrant/qdrant, port 6333    |
| LLM              | Any HTTP chat API (LLAMA_URL)        | Your choice (local or cloud)         |
| Embeddings       | Any HTTP embedding API (EMBEDDING_URL) | Your choice (local or cloud)      |
| TTS              | VibeVoice or OpenAI                  | VIBEVOICE_URL or OPENAI_API_KEY     |
| LangGraph state  | PostgreSQL (same DB)                 | Same DATABASE_URL, AsyncPostgresSaver |

---

## How to run the project

Stepwise: run the backend first (database, API server), then the frontend. The frontend talks to the backend at `http://localhost:8000` by default (Vite proxy).

### 1. Backend

**1.1 Clone and go to project root**

```bash
cd /path/to/ai-fashion-agent
```

**1.2 Start PostgreSQL and Qdrant (Docker)**

```bash
docker-compose up -d
```

This starts Postgres on host port 5438 and Qdrant on 6333/6334. Check with `docker-compose ps`.

**1.3 Python environment**

Use a virtualenv (or conda) and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**1.4 Environment variables**

Copy the example env file and set at least the required values:

```bash
cp .env.example .env
```

Edit `.env`. Minimum you must set:

- `DATABASE_URL` – PostgreSQL URL. If using the Docker Postgres from step 1.2:  
  `postgresql://ai-fashion:ai-fashion@localhost:5438/ai-fashiondb`
- `SECRET_KEY` – any long random string (for JWT).
- `QDRANT_HOST` – e.g. `localhost`.
- `QDRANT_PORT` – e.g. `6333`.
- `QDRANT_COLLECTION_NAME` – name of your RAG collection (e.g. `documents`); create/populate it with your scripts if needed.
- `LLAMA_URL` – URL of your LLM chat API (e.g. `http://localhost:11434/v1/chat/completions` for Ollama).
- `EMBEDDING_URL` – URL of your embedding API.
- `EMBEDDING_DIMENSION` – dimension of vectors (e.g. `384` or `1536`).

Optional: `OPENAI_API_KEY`, `ISVIBEVOICE`, `VIBEVOICE_URL`, and other flags from `app/core/config.py`.

**1.5 Prisma: generate client and database**

Generate the Prisma client:

```bash
prisma generate
```

Create/update the database schema (tables). Either:

```bash
prisma db push
```

or, if you use migrations:

```bash
prisma migrate deploy
```

**1.6 Run the API server**

From the project root (with the same virtualenv active):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend is up at `http://localhost:8000`. Check: `curl http://localhost:8000/` and `curl http://localhost:8000/health`.

---

### 2. Frontend

**2.1 Install dependencies**

From the project root:

```bash
cd frontend
npm install
```

**2.2 Point at the backend (optional)**

The frontend uses `VITE_API_URL` for API base URL. Vite dev server proxies `/api` to `http://localhost:8000` (see `frontend/vite.config.ts`). So with the backend on port 8000 you do not need to set `VITE_API_URL` for local dev. If the backend is on another host/port, create `frontend/.env` (or `frontend/.env.local`) with:

```
VITE_API_URL=http://localhost:8000
```

(or the URL where the backend runs).

**2.3 Run the dev server**

From the `frontend` directory:

```bash
npm run dev
```

Vite usually serves the app at `http://localhost:5173`. Open that in the browser; the app will call the backend via the proxy (or `VITE_API_URL`).

---

### Quick checklist

| Step | Where | Command / action |
|------|--------|-------------------|
| 1 | Root | `docker-compose up -d` |
| 2 | Root | `python -m venv .venv && source .venv/bin/activate` |
| 3 | Root | `pip install -r requirements.txt` |
| 4 | Root | `cp .env.example .env` and fill required vars |
| 5 | Root | `prisma generate` then `prisma db push` (or `migrate deploy`) |
| 6 | Root | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| 7 | frontend | `npm install` then `npm run dev` |

Backend first (steps 1–6), then frontend (step 7). Ensure the LLM and embedding services you configured in `.env` are running when you use chat or RAG.

---

## Architecture diagrams

### High-level system

```mermaid
flowchart TB
    subgraph Client
        C[Client / Frontend]
    end

    subgraph FastAPI["FastAPI (main.py)"]
        MW[AuthMiddleware]
        R["/api/v1 Router"]
    end

    subgraph API["API Endpoints"]
        A1["/auth (signup, login, logout)"]
        A2["/intent"]
        A3["/chat"]
        A4["/sql-agent"]
        A5["/voice/tts"]
    end

    subgraph Graph["LangGraph Orchestrator"]
        PG[policy_gate]
        IR[intent_router]
        SA[sql_agent node]
        RA[rag_agent node]
        HA[hybrid_agent node]
    end

    subgraph Services["Services (app/services)"]
        S1[policy_agent, policy_gate]
        S2[intent_router]
        S3[sql_agent, sql_validator, schema_*]
        S4[rag_agent, rag_grounding]
        S5[candidate_*, wrqs_*, learning_*]
    end

    subgraph Data["Data & External"]
        DB[(PostgreSQL\nPrisma)]
        QD[(Qdrant)]
        LLM[LLM API]
        EMB[Embedding API]
        TTS[TTS API]
    end

    C --> MW
    MW --> R
    R --> A1 & A2 & A3 & A4 & A5
    A3 --> Graph
    A4 --> S3
    A1 --> DB
    Graph --> PG --> IR --> SA & RA & HA
    SA & RA & HA --> Services
    Services --> DB & QD & LLM & EMB
    A5 --> TTS
    Graph --> DB
```

### LangGraph request flow (chat path)

```mermaid
flowchart LR
    START([START]) --> PG[policy_gate]
    PG -->|allow?| DECIDE{policy_allow}
    DECIDE -->|no| END1([END - refusal])
    DECIDE -->|yes| IR[intent_router]
    IR --> ROUTE{intent}
    ROUTE -->|sql| SA[sql_agent]
    ROUTE -->|rag| RA[rag_agent]
    ROUTE -->|hybrid| HA[hybrid_agent]
    SA --> END2([END])
    RA --> END2
    HA --> END2
```

### LangGraph nodes and services

```mermaid
flowchart TB
    subgraph Nodes["Graph nodes (graph/nodes.py)"]
        N1[policy_gate_node]
        N2[intent_router_node]
        N3[sql_node]
        N4[rag_node]
        N5[hybrid_node]
    end

    subgraph Policy["Policy"]
        P1[policy_agent.evaluate_policy_hard_gate]
        P2[policy_gate.evaluate_policy]
    end

    subgraph Intent["Intent"]
        I1[intent_router heuristic + LLM]
    end

    subgraph SQL["SQL path"]
        S1[schema_loader / schema_rag]
        S2[sql_agent.run_sql_agent]
        S3[sql_validator / sql_query_plan]
        S4[candidate_gate, wrqs_scoring]
    end

    subgraph RAG["RAG path"]
        R1[embed_query + Qdrant search]
        R2[rag_grounding]
        R3[rag_agent generation]
    end

    subgraph Hybrid["Hybrid path"]
        H1[sql_agent + rag_agent in parallel]
        H2[LLM synthesis]
    end

    N1 --> P1
    N2 --> I1
    N3 --> S1 & S2 & S3 & S4
    N4 --> R1 & R2 & R3
    N5 --> H1 --> H2
```

### Data flow and storage

```mermaid
flowchart TB
    subgraph App["App layer"]
        API[API endpoints]
        G[LangGraph]
    end

    subgraph State["AgentState (per request)"]
        ST[messages, intent, user_state,\ncustomer_id, policy_*, candidate_*,\ncorrection_hints, wrqs_weights, ...]
    end

    subgraph PostgreSQL["PostgreSQL (Prisma)"]
        U[User, Customer]
        CS[ChatSession]
        CM[ChatMessage]
        CEL[chat_event_log]
        POL[policy_audit, learning_*, release_*, ...]
    end

    subgraph Qdrant["Qdrant"]
        COL1[documents collection\nRAG retrieval]
        COL2[sql-agent collection\nschema RAG]
    end

    subgraph External["External APIs"]
        LLM[LLM]
        EMB[Embeddings]
    end

    API --> G
    G --> State
    G --> PostgreSQL
    G --> Qdrant
    G --> External
    API --> PostgreSQL
```

### Layer overview

```mermaid
flowchart LR
    subgraph Entry["Entry"]
        M[main.py]
    end

    subgraph Core["core/"]
        CF[config]
        SEC[security]
        LLM[llm]
        QD[qdrant]
        EMB[embeddings]
    end

    subgraph API["api/"]
        DEP[dependencies]
        V1[v1/router]
        AUTH[auth]
        CHAT[chat]
        INT[intent]
        SQL[sql_agent]
        VOICE[voice]
    end

    subgraph Graph["graph/"]
        STATE[state]
        GR[graph.py]
        ND[nodes.py]
    end

    subgraph Svc["services/"]
        list[30+ service modules]
    end

    subgraph Schemas["schemas/"]
        SCH[auth, intent, chat, sql_agent]
    end

    M --> Core & API
    API --> Graph & Svc & Schemas
    Graph --> Svc
    CHAT --> Graph
```

---

## App folder structure

- **app/main.py** – FastAPI app, lifespan, auth middleware, CORS, health.
- **app/core/** – Config, security (JWT, passwords), LLM client, Qdrant client, embeddings client.
- **app/api/** – REST routes and dependencies (Prisma, Qdrant, graph, auth).
- **app/graph/** – LangGraph state, graph build, and nodes (policy, intent, sql, rag, hybrid).
- **app/services/** – Business logic used by the graph and API (auth, policy, SQL, RAG, learning, etc.).
- **app/schemas/** – Pydantic request/response models for API and intent.

---

## Entry point: main.py

- Loads environment with dotenv.
- Sets up logging for the app.
- Creates FastAPI app with a lifespan that: connects Prisma to PostgreSQL, creates Qdrant client, builds the LangGraph with an async Postgres checkpointer, stores them on app.state; on shutdown disconnects Prisma and closes Qdrant.
- **AuthMiddleware**: For paths under /api/v1, requires a valid Bearer JWT except for auth paths (login, signup, logout) and a few guest-allowed paths (POST /chat, POST /voice/tts). Returns 401 if no token or invalid.
- Adds CORS and mounts the v1 API router at /api/v1.
- Root GET / returns status and database type. GET /health checks PostgreSQL and Qdrant connectivity.

---

## Core

**core/config.py**  
Settings from environment (pydantic-settings): DATABASE_URL, SECRET_KEY, token expiry, Qdrant host/port/collection, embedding URL and dimension, LLM URL (LLAMA_URL), OpenAI key and TTS options, and many feature flags (phase flags, learning, release controls, ops dashboard, content moderation, thresholds).

**core/security.py**  
JWT creation (create_access_token) and verification, password hashing and verification (passlib bcrypt_sha256). Algorithm HS256.

**core/llm.py**  
Async chat function that POSTs to a configurable URL (LLAMA_URL). Supports OpenAI-style (messages array) and Llama-style (message + system_prompt) APIs. Also exposes a LangChain BaseChatModel wrapper (ChatModelViaHTTP) for use in the graph.

**core/qdrant.py**  
Creates a QdrantClient from config (host, port).

**core/embeddings.py**  
Async client: embed_query (single text) and embed_batch (multiple texts). POSTs to EMBEDDING_URL with {"text": [...]}, returns list of float vectors.

---

## API

**api/dependencies.py**  
- get_prisma: returns request.app.state.prisma.  
- get_qdrant: returns request.app.state.qdrant.  
- get_graph: returns request.app.state.graph.  
- get_current_user: OAuth2PasswordBearer token, decode JWT, load user with customer from Prisma; 401 if invalid.  
- get_current_user_optional: same but returns None when no token; still rejects malformed tokens.

**api/v1/router.py**  
Single API router that includes: auth, intent, chat, voice, sql_agent.

**api/v1/endpoints/auth.py**  
- POST /auth/signup: register user (auth_service.register), return token and user.  
- POST /auth/login: authenticate (auth_service.authenticate), return token and user.  
- POST /auth/logout: placeholder response (client-side logout).

**api/v1/endpoints/intent.py**  
- POST /intent: body has message; runs intent_router.detect_intent and returns which agent (sql, rag, hybrid). No auth required in router; middleware may still apply.

**api/v1/endpoints/chat.py**  
- POST /chat: main entry. Resolves session (guest or body.session_id), optional customer by name, learning preferences, correction hints, release WRQS weights. Translates non-English input to English for the graph, then invokes the LangGraph with messages and state. After response: policy audit, learning guardrails, quality scoring (TQS/KGS), persistence of turn, telemetry events, feedback/handoff handling. Returns content, intent, session_id, message ids, turn_index, debug_trace.  
- POST /chat/feedback: store user feedback on an assistant message; correction memory and long-term consent.  
- POST /chat/handoff: enqueue human handoff for a message.  
- GET /chat/sessions/{session_id}/history: full history and latest trace.  
- GET/PUT /chat/learning/preferences: get or update learning preferences.  
- GET /chat/ops/dashboard: ops KPIs (when enabled).  
- GET /chat/ops/release/status, POST golden-run, POST canary/start, POST canary/rollback: release control endpoints.

**api/v1/endpoints/sql_agent.py**  
- POST /sql-agent: authenticated. Resolves customer from current user or selected_customer_name. Calls sql_agent.run_sql_agent and returns content, sql, plan, metadata.

**api/v1/endpoints/voice.py**  
- POST /voice/tts: body has text. Uses VibeVoice at VIBEVOICE_URL when ISVIBEVOICE is true, else OpenAI TTS. Returns audio. Optional auth.

---

## Graph (LangGraph)

**graph/state.py**  
AgentState extends MessagesState. Holds: intent (sql/rag/hybrid), context, sql_result, rag_result, user_state, roles, consent_flags, active_order_id, active_design_id, user_id, customer_id, customer_name, trace fields, policy_allow and policy metadata, candidate_set and candidate_scores, selected_candidate_id, learning_turn_index, clarify_mode, rag_top_k_override, query_expansion_enabled, wrqs_weight_overrides, release_wrqs_weights, short_answer_pref, lang_pref, correction_hints, sql_memory.

**graph/graph.py**  
- build_graph(settings, qdrant_client, checkpointer): builds a StateGraph(AgentState).  
- Nodes: policy_gate, intent_router, sql_agent, rag_agent, hybrid_agent.  
- Edges: START to policy_gate; policy_gate conditionally to intent_router or END; intent_router by intent to sql_agent, rag_agent, or hybrid_agent; each agent to END.  
- Graph is compiled with the async Postgres checkpointer for conversation persistence.

**graph/nodes.py**  
- **policy_gate_node**: Takes last user message and user_state. Calls policy_agent.evaluate_policy_hard_gate (rules plus optional LLM classifier). Sets policy_allow, policy_intent, policy_domain, reason_code, refusal_text, decision_source. If not allowed, appends refusal AIMessage and returns; otherwise passes through.  
- **intent_router_node**: For guests, forces intent rag. Otherwise builds history from messages, calls LLM with strict router prompt, parses SQL_AGENT/RAG_AGENT/HYBRID_AGENT, then applies intent_router.heuristic_override. Returns intent and trace.  
- **rag_node**: Detects memory-style questions (e.g. "what did I say"). If memory: answers from conversation history only. Else: embeds query, searches Qdrant, optionally RAG grounding (assess_claim_support, fallback), builds context, generates answer with LLM. Uses correction_hints and lang_pref. Returns messages, rag_result, context, metadata, trace.  
- **sql_node**: Loads schema (schema_loader or schema_rag), runs sql_agent (query preprocess, plan or direct SQL, validator/firewall, execute, format). Can use sql_memory and candidate framework (candidates, gate, WRQS scoring, best candidate). Returns messages, sql_result, metadata, candidate_set, candidate_scores, selected_candidate_id, trace.  
- **hybrid_node**: Runs SQL and RAG in parallel (same sql_agent and rag_agent services), then one LLM call to synthesize one answer. Uses language preference and correction hints. Returns combined message and trace.

---

## Services (what each does)

**auth_service.py**  
Register: check email unique, hash password, find or create Customer by email, create User with customerId; return UserOut. Authenticate: find user by email, verify password, return UserOut or None.

**policy_gate.py**  
Deterministic policy. UserState (GUEST/REGISTERED), PolicyIntent, DomainClass. Regex patterns for safety (abuse, hate, sexual, self-harm, illegal, prompt injection), domain (order, design, product, account, OASIS public, internal metrics, financials, politics, weather). classify_intent, classify_domain, refusal text per case. evaluate_policy: blocks safety-critical, blocks off-domain/confidential for guest or registered as per matrix; returns PolicyDecision (allow, intent, domain, reason_code, refusal_text).

**policy_agent.py**  
Phase 2 hard gate: runs policy_gate rules first; if not blocked, optional LLM classifier (JSON intent/domain/confidence). Merges rules and LLM into a single allow/deny with reason_code and refusal_text. evaluate_policy_hard_gate returns PolicyAgentDecision (allow, intent, domain, confidence, reason_code, refusal_text, decision_source, rules/llm details).

**intent_router.py**  
Deterministic scoring (score_intent) from patterns (aggregation, financial, data nouns, list, explanation, memory, etc.) to prefer SQL_AGENT, RAG_AGENT, or HYBRID_AGENT. heuristic_override: if heuristics give a non-default intent, use it; else use LLM proposal. detect_intent: try deterministic first, then LLM with conversation history.

**session_service.py**  
get_or_create_session: find or create ChatSession by id. get_full_history: all messages for a session. load_history: last N messages for LLM context. save_turn: append one user and one assistant message, optional trace on assistant. get_latest_assistant_trace, get_latest_user_message.

**sql_agent.py**  
run_sql_agent: optional schema from schema_rag or schema_loader; preprocess query; generate SQL (prompt with schema and customer_id); validate (SELECT only, WHERE required); enforce customer scope; execute via asyncpg; format results; LLM to natural language. Returns content and metadata (sql, plan if used, row count, errors). Used by graph sql_node and by hybrid_agent and by the /sql-agent API.

**sql_validator.py**  
validate_and_prepare: basic safety (SELECT only, no dangerous keywords). enforce_customer_scope: ensure WHERE with customer_id (or equivalent) for the right table. run_sql_firewall: limit enforcement, allowed tables, reject cross-user aggregates; uses sqlglot. SqlValidationError on failure.

**sql_query_plan.py**  
Structured query plan: tables, filters, joins, order, limit. parse_query_plan: extract JSON plan from LLM. inject_mandatory_scope: add customer scoping. validate_and_fix_group_by. build_sql_from_plan: generate SQL from plan. QueryPlanError on invalid plan.

**schema_loader.py**  
Reads Prisma schema file, whitelist of allowed models, builds DDL-style context string (tables, relations, customer scoping rules, examples, time guidance). load_schema_context returns that string for LLM SQL generation.

**schema_rag.py**  
RAG over schema: embed user query, search Qdrant collection "sql-agent", return retrieved schema context string. No fallback to schema_loader. SchemaRAGError if collection missing or search fails.

**schema_chunker.py**  
Chunks schema into pieces (table definitions, relationships, security, query patterns) for embedding and loading into Qdrant (used by scripts that populate sql-agent collection).

**rag_agent.py**  
run: if memory question, answer from conversation history only; else embed query, search Qdrant, build_context from results, optional grounding checks, generate answer with LLM. Used by graph rag_node and hybrid_agent.

**rag_grounding.py**  
build_retrieval_metadata from Qdrant points (scores, etc.). assess_claim_support: compare answer to retrieved context for hallucination risk. should_fallback_for_grounding: decide if we should fall back. is_recommendation_prompt. build_explainability_metadata for debug/quality.

**hybrid_agent.py**  
run: asyncio.gather sql_agent and rag_agent, then one LLM synthesis step to combine database answer and document answer into one reply. Used by graph hybrid_node.

**candidate_framework.py**  
Candidate: candidate_id, text, signals (positive/penalty factors). CandidateContext: user message, policy_allow, user_state, etc. build_candidate: build candidate from id, text, sql/rag metadata. normalize_signals. infer_tie_break_preference.

**candidate_signals.py**  
candidate_signals(candidate_id, text, sql_metadata, rag_metadata): returns dict of signal scores (e.g. for WRQS scoring).

**candidate_gate.py**  
gate_candidate: if policy blocked or guest and SQL candidate, or policy re-eval on candidate text fails, or over-disclosure (Po >= 0.95), deny; else allow. gate_candidates: run gate for each candidate, return dict of candidate_id to GateResult.

**wrqs_config.py**  
WRQSConfig: positive and penalty weight dicts. get_default_wrqs_config.

**wrqs_scoring.py**  
score_candidate with weights (release or default). select_best_candidate: rank by score, apply gate, return best allowed candidate.

**query_preprocessor.py**  
preprocess_query_for_sql: normalizes query and returns dict (e.g. for plan or SQL generation).

**language_helper.py**  
get_language_instruction: returns system-prompt snippet for response language when lang_pref is set.

**translation_service.py**  
translate_to_english, translate_to_language: call external translation (e.g. LLM) for chat input/output when user chooses non-English.

**correction_memory_service.py**  
create_correction_memory: store user correction from feedback (session or long-term by consent). load_correction_hints: load hints for a session/user/customer for injection into prompts.

**feedback_service.py**  
ensure_message_in_session: check message belongs to session. create_feedback: insert feedback row (feedback_type, reason_code, correction_text, learning_allowed). get_latest_feedback_map: per message_id feedback_type for history.

**handoff_service.py**  
enqueue_handoff: create handoff queue item. increment_session_handoff_clicks: bump counter on session feature for quality/adaptation.

**learning_preferences_service.py**  
ensure_learning_preferences, get_learning_preferences, upsert_learning_preferences (long_term_personalization_opt_in, telemetry_learning_opt_in). long_term_memory_allowed: from request consent and stored preference.

**learning_guardrails_service.py**  
classify_learning_eligibility: whether this turn is allowed for learning (policy, reason code, telemetry opt-in). create_learning_exclusion_audit: record when a turn is excluded from learning.

**quality_scoring_service.py**  
TurnQualityInput: intent, positive/penalty factors, retrieval confidence, hallucination risk, sql_error, sql_row_count, rephrase_count, handoff_click. compute_tqs (turn quality score), compute_kgs (knowledge gap score). classify_turn_quality: low_tqs, high_kgs, critical_kgs thresholds.

**online_adaptation_service.py**  
Session feature: turn_index, rephrase_count, handoff_clicks, wrqs overrides, rag_top_k, etc. get_or_create_session_feature, expire_adaptation (TTL), persist_turn_scores. evaluate_adaptation: decide whether to apply adaptation (e.g. increase RAG top_k, change WRQS weights) from TQS/KGS and rephrase/handoff. apply_adaptation: write overrides to DB. adaptation_state: read overrides for graph. apply_wrqs_overrides: merge session overrides into weights. build_gap_topic_key, upsert_knowledge_gap_item for critical KGS.

**telemetry_service.py**  
emit_event: write event to chat_event_log (request_id, session_id, turn_index, event_type, message_id, user_id, customer_id, content, payload, learning_allowed, etc.). emit_trace_tool_events: emit events for debug trace steps. Redaction and hashing helpers.

**release_control_service.py**  
get_active_wrqs_weights: current production WRQS weights. snapshot_component_versions: record version hashes. run_golden_gate: run golden set, compute pass rate, store result. start_canary_rollout: start canary with percent. evaluate_canary_and_maybe_rollback: compare canary vs baseline (KGS, handoff rate), rollback if thresholds exceeded. get_release_status. is_experiment_dimension_allowed.

**ops_dashboard_service.py**  
get_ops_dashboard: KPIs over a day window (sessions, messages, policy blocks, intent distribution, quality metrics, etc.). get_ops_snapshot: compact snapshot for trace.

**policy_audit_service.py**  
save_policy_audit: persist policy decision (request_id, session_id, user, message, policy_intent, domain, confidence, allow, reason_code, decision_source, trace).

**offline_learning_jobs.py**  
run_daily_job: aggregate telemetry, update weights or gap items for a date. run_weekly_job: weekly WRQS weight tuning within max_delta.

---

## Schemas

**schemas/auth.py**  
UserCreate, UserLogin, UserOut, CustomerOut, TokenResponse.

**schemas/intent.py**  
AgentIntent (SQL_AGENT, RAG_AGENT, HYBRID_AGENT). IntentRequest (message), IntentResponse (intent).

**schemas/chat.py**  
ChatRequest, ChatResponse, ChatFeedbackRequest/Response, ChatHandoffRequest/Response, ChatHistoryResponse, ChatMessageOut, learning preferences, ops dashboard, release status, golden run, canary start/rollback.

**schemas/sql_agent.py**  
SQLAgentRequest, SQLAgentResponse.

---

## Request flow (high level)

1. Client sends POST /api/v1/chat with message, optional session_id, language, selected_customer_name. Auth: optional for chat (guest allowed).
2. main.py AuthMiddleware: if path is guest-allowed, continue; else require valid JWT.
3. chat endpoint: resolve session, customer, learning preferences, correction hints, release weights. Optionally translate input to English. Build initial state (messages, user_state, customer_id, trace, etc.).
4. LangGraph invoke: thread_id = session_id (checkpointer loads/saves history).  
   - policy_gate: allow or block; if block, return refusal and end.  
   - intent_router: sql / rag / hybrid.  
   - One of sql_agent, rag_agent, hybrid_agent runs and produces the final message.
5. Chat endpoint again: translate response back if needed; save policy audit; run learning guardrails; compute TQS/KGS and persist; save turn (user + assistant messages); optionally apply adaptation; emit telemetry events; return content, intent, session_id, trace.
6. Other endpoints: auth (signup/login) issue JWT; intent returns only routing; sql-agent runs SQL path only with auth; voice/tts returns audio; feedback and handoff write to DB; learning preferences and ops/release are read/update endpoints.

---

## Summary

- **main.py**: App lifecycle, Prisma + Qdrant + LangGraph, JWT middleware, /api/v1.  
- **core**: Config, JWT/passwords, LLM HTTP client, Qdrant, embeddings.  
- **api**: Router and dependencies; auth, intent, chat (main flow), sql-agent, voice.  
- **graph**: State, graph (policy then intent then one of sql/rag/hybrid), nodes in nodes.py.  
- **services**: Auth, policy (gate + agent), intent, session, SQL (agent, validator, query_plan), schema (loader, rag, chunker), RAG (agent, grounding), hybrid, candidates (framework, signals, gate), WRQS (config, scoring), query preprocess, language/translation, correction memory, feedback, handoff, learning (preferences, guardrails, quality, online adaptation, telemetry, offline jobs), release control, ops dashboard, policy audit.  
- **schemas**: Pydantic models for API and intent.

All in order: request hits API, middleware checks auth, chat builds state and invokes graph; graph runs policy then intent then one agent; response is saved, scored, and returned with optional telemetry and learning updates.
