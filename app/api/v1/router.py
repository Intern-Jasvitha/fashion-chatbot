"""API v1 router aggregating all v1 endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, intent, sql_agent

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(intent.router)
api_router.include_router(chat.router)
api_router.include_router(sql_agent.router)
