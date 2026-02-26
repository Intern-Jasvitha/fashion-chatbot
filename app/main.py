"""FastAPI app with Prisma PostgreSQL connection."""

from dotenv import load_dotenv

load_dotenv()  # Load .env before any LangChain/LangGraph code so tracing env vars are available

import logging
from contextlib import asynccontextmanager

# Ensure app loggers (e.g. app.graph.nodes, app.services.sql_agent) show INFO in the console.
# Without this, only uvicorn logs appear and SQL/LLM debug logs are hidden.
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.INFO)
if not _app_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _app_log.addHandler(_h)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from prisma import Prisma
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.api.dependencies import get_prisma, get_qdrant
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.qdrant import create_qdrant_client
from app.core.security import ALGORITHM
from app.graph.graph import build_graph

logger = logging.getLogger(__name__)
prisma = Prisma(auto_register=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to PostgreSQL and Qdrant on startup, init LangGraph checkpointer, disconnect on shutdown."""
    await prisma.connect()
    app.state.prisma = prisma
    qdrant = create_qdrant_client()
    app.state.qdrant = qdrant

    settings = get_settings()
    async with AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(settings, qdrant, checkpointer)
        app.state.graph = graph
        try:
            yield
        finally:
            if prisma.is_connected():
                await prisma.disconnect()
            qdrant.close()


app = FastAPI(
    title="AI Fashion Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

# Auth: paths under /api/v1 that do not require JWT
API_V1_AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/signup", "/api/v1/auth/logout")
API_V1_GUEST_ALLOWED = {
    ("POST", "/api/v1/chat"),
    ("POST", "/api/v1/chat/"),
    ("POST", "/api/v1/voice/tts"),
}


class AuthMiddleware(BaseHTTPMiddleware):
    """Return 401 for /api/v1 requests without valid Bearer token (except auth paths)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1") or any(path.startswith(p) for p in API_V1_AUTH_PATHS):
            return await call_next(request)
        if (request.method.upper(), path) in API_V1_GUEST_ALLOWED:
            return await call_next(request)
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth[7:].strip()
        settings = get_settings()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("sub") is None:
                raise ValueError("missing sub")
        except (JWTError, ValueError):
            return JSONResponse(
                status_code=401,
                content={"detail": "Could not validate credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "database": "prisma-postgres"}


@app.get("/health")
async def health(request: Request):
    """Check PostgreSQL and Qdrant connectivity."""
    qdrant_ok = False
    try:
        request.app.state.qdrant.get_collections()
        qdrant_ok = True
    except Exception:
        pass
    return {
        "database_connected": prisma.is_connected(),
        "qdrant_connected": qdrant_ok,
    }
