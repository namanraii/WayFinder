"""Wayfinder backend API entrypoint (spec §16, §20)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.artifacts import router as artifacts_router
from app.api.compare import router as compare_router
from app.api.decisions import router as decisions_router
from app.api.documents import router as documents_router
from app.api.qa import router as qa_router
from app.api.tracker import router as tracker_router
from app.api.webhooks_whatsapp import router as whatsapp_router
from app.db import sqlite


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database tables and storage folders on startup
    sqlite.init_db()
    yield


app = FastAPI(
    title="Wayfinder API",
    description="Turns legal documents into actionable decisions with hard guarantees on the cost of inaction.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(documents_router)
app.include_router(decisions_router)
app.include_router(artifacts_router)
app.include_router(compare_router)
app.include_router(qa_router)
app.include_router(tracker_router)
app.include_router(whatsapp_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Wayfinder", "version": "0.1.0"}
