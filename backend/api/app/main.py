"""
Zapper PM — FastAPI application entry point.
Schema managed exclusively by Alembic migrations.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.routers import (
    auth,
    meetings,
    transcripts,
    summaries,
    action_items,
    chat,
    analytics,
    integrations,
    automations,
    knowledge,
    bot,
    settings,
    websockets,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Zapper PM API",
    version="1.0.0",
    description="AI Meeting Intelligence Platform — Project Management Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All routers under /api/v1
PREFIX = "/api/v1"

app.include_router(auth.router, prefix=PREFIX)
app.include_router(meetings.router, prefix=PREFIX)
app.include_router(transcripts.router, prefix=PREFIX)
app.include_router(summaries.router, prefix=PREFIX)
app.include_router(action_items.router, prefix=PREFIX)
app.include_router(chat.router, prefix=PREFIX)
app.include_router(analytics.router, prefix=PREFIX)
app.include_router(integrations.router, prefix=PREFIX)
# OAuth callback routes must be at root (no /api/v1) to match registered redirect URIs
app.include_router(integrations.router)
app.include_router(automations.router, prefix=PREFIX)
app.include_router(knowledge.router, prefix=PREFIX)
app.include_router(bot.router, prefix=PREFIX)
app.include_router(settings.router, prefix=PREFIX)
# WebSocket router has no prefix (WS paths start with /ws/)
app.include_router(websockets.router)


@app.get("/api/healthz")
async def healthz():
    return {"status": "ok", "service": "zapper-pm-backend", "version": "1.0.0"}
