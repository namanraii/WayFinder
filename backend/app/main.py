"""Wayfinder backend API entrypoint (spec §16, §20)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time

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

# GZip response compression for maximum transfer efficiency
app.add_middleware(GZipMiddleware, minimum_size=500)

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


@app.middleware("http")
async def add_security_and_performance_headers(request: Request, call_next):
    start_time = time.perf_counter()
    response: Response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time * 1000:.2f}ms"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Register API routers
for prefix in ("", "/api"):
    app.include_router(documents_router, prefix=prefix)
    app.include_router(decisions_router, prefix=prefix)
    app.include_router(artifacts_router, prefix=prefix)
    app.include_router(compare_router, prefix=prefix)
    app.include_router(qa_router, prefix=prefix)
    app.include_router(tracker_router, prefix=prefix)
    app.include_router(whatsapp_router, prefix=prefix)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Wayfinder", "version": "0.1.0"}


# Serve static frontend SPA build in single-container deployment
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_dist_candidates = [
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
    Path(__file__).resolve().parent / "static",
    Path("/app/frontend/dist"),
    Path("/app/static"),
]

for _dist in _dist_candidates:
    if _dist.exists() and (_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend-static")
        break

