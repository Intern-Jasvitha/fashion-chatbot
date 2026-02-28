from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    # JWT auth
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_DAYS: int = 1
    API_V1_STR: str = "/api/v1"

    # Qdrant (Docker / local)
    QDRANT_HOST: str
    QDRANT_PORT: int
    QDRANT_COLLECTION_NAME: str

    # Embedding API
    EMBEDDING_URL: str
    EMBEDDING_DIMENSION: int

    # LLM chat API (intent router, etc.)
    LLAMA_URL: str

    # OpenAI (Realtime API for voice)
    OPENAI_API_KEY: str = ""

    # TTS backend: when True use VibeVoice at VIBEVOICE_URL, when False use OpenAI
    ISVIBEVOICE: bool = False
    VIBEVOICE_URL: str = "http://localhost:3000"

    # Phase flags
    ENABLE_PHASE3_SQL_SECURITY: bool = True
    ENABLE_PHASE4_RAG_GROUNDING: bool = True
    ISREMOVED_GATE: bool = False  # When True, skip retrieval + grounding clarification gates
    ENABLE_PHASE5_CANDIDATES: bool = True
    ENABLE_PHASE6_WRQS: bool = True
    ENABLE_LEARNING_TELEMETRY: bool = True
    ENABLE_LEARNING_SCORING: bool = True
    ENABLE_LEARNING_ONLINE_ADAPTATION: bool = True
    ENABLE_LEARNING_FEEDBACK: bool = True
    ENABLE_LEARNING_HANDOFF: bool = True
    ENABLE_LEARNING_OFFLINE_JOBS: bool = True
    ENABLE_LEARNING_GOVERNANCE: bool = True
    ENABLE_RELEASE_CONTROLS: bool = True
    ENABLE_OPS_DASHBOARD: bool = True
    LEARNING_LOW_TQS_THRESHOLD: int = 60
    LEARNING_HIGH_KGS_THRESHOLD: int = 65
    LEARNING_CRITICAL_KGS_THRESHOLD: int = 80
    LEARNING_ADAPT_TTL_TURNS: int = 3
    LEARNING_RAG_TOPK_BASE: int = 12
    LEARNING_RAG_TOPK_ADAPT: int = 18
    LEARNING_WEEKLY_WRQS_MAX_DELTA: float = 0.05
    RELEASE_GOLDEN_MIN_PASS_RATE: float = 0.95
    RELEASE_CANARY_DEFAULT_PERCENT: int = 10
    RELEASE_ROLLBACK_MAX_KGS_DELTA: float = 8
    RELEASE_ROLLBACK_MAX_HANDOFF_RATE: float = 0.15
    OPS_DASHBOARD_DEFAULT_DAYS: int = 7

    # Content moderation (OASIS Halo)
    ENABLE_CONTENT_MODERATION: bool = True
    SELF_HARM_SUPPORT_EMAIL: str = "support@onliest.ai"
    SELF_HARM_SUPPORT_PHONE: str = "1-800-XXX-XXXX"
    CONTENT_MODERATION_LOG_LEVEL: str = "WARNING"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore extra env vars (e.g. LLAMA_URL) not in schema
    )


def get_settings() -> Settings:
    return Settings()
