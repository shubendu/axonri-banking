"""
Axonri Banking — FastAPI application entry point.

Startup sequence:
    1. Validate domain config
    2. Auto-detect LLM host (handles Docker on all 3 OSes)
    3. Load embedding model (BGE-M3 — ~8s, ~2GB RAM)
    4. Load reranker model (BGE-reranker-v2-m3 — ~2s)
    5. Preload Whisper STT (small model — ~5s)
    6. Init Qdrant client + ensure collection exists
    7. Load BM25 index from disk
    8. Init RAGEngine
    9. Start health logging background task (every 60s)
    10. Ready — accept requests
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from axonri_core.utils.network import detect_llm_host
from axonri_core.embeddings import get_embedder
from axonri_core.reranker import get_reranker
from axonri_core.llm import LLMClient
from axonri_core.bm25 import BM25Manager
from axonri_core.retrieval import HybridRetriever
from axonri_core.engine import RAGEngine
from axonri_core.logging import QueryLogger, IngestionLogger, HealthLogger
from axonri_core.ingestion import IngestPipeline

from qdrant_client import QdrantClient

from app.domain_config import banking_config
from app.database import init_db
from app.routers import query, documents, auth, admin, health, stt

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown."""
    # ── STARTUP ────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Axonri Banking — Starting up")
    logger.info("=" * 60)

    # 1. Validate config
    banking_config.validate()
    logger.info(f"Domain config validated: {banking_config.domain_id}")

    # 2. Auto-detect LLM host
    llm_port = int(os.environ.get("LLM_PORT", "8080"))
    detect_llm_host(llm_port)

    # 3. Load models (blocking — run in thread pool)
    loop = asyncio.get_event_loop()

    logger.info("Loading BGE-M3 embedding model...")
    await loop.run_in_executor(None, get_embedder)

    logger.info("Loading BGE reranker model...")
    await loop.run_in_executor(None, get_reranker)

    logger.info("Loading Whisper STT model...")
    from app.routers.stt import preload_whisper
    await loop.run_in_executor(None, preload_whisper)

    # 4. Init Qdrant
    qdrant = QdrantClient(
        host=os.environ.get("QDRANT_HOST", "localhost"),
        port=int(os.environ.get("QDRANT_PORT", "6333")),
        timeout=10,
    )
    logger.info(f"Qdrant connected at {os.environ.get('QDRANT_HOST', 'localhost')}:6333")

    # 5. Init BM25
    bm25_path = os.path.join(os.environ.get("VECTORS_DIR", "/data/vectors"), "bm25.pkl")
    bm25 = BM25Manager(persist_path=bm25_path)
    logger.info(f"BM25 index loaded: {bm25.size} chunks")

    # 6. Init loggers
    log_dir = os.environ.get("LOG_DIR", "/data/logs")
    query_logger = QueryLogger(log_dir=log_dir)
    ingestion_logger = IngestionLogger(log_dir=log_dir)
    health_logger = HealthLogger(log_dir=log_dir)

    # 7. Init pipeline + engine
    retriever = HybridRetriever(config=banking_config, qdrant=qdrant, bm25=bm25)
    llm = LLMClient()
    ingest_pipeline = IngestPipeline(config=banking_config, qdrant=qdrant, bm25=bm25)
    rag_engine = RAGEngine(
        config=banking_config,
        retriever=retriever,
        llm=llm,
        logger=query_logger,
    )

    # 8. Init SQLite
    init_db()

    # 9. Store on app.state for use in routes
    app.state.engine = rag_engine
    app.state.ingest = ingest_pipeline
    app.state.qdrant = qdrant
    app.state.bm25 = bm25
    app.state.query_logger = query_logger
    app.state.ingestion_logger = ingestion_logger
    app.state.health_logger = health_logger
    app.state.llm = llm
    app.state.domain_config = banking_config

    # 10. Start health logging background task
    async def health_logger_task():
        import psutil
        while True:
            try:
                llm_ok = await llm.health_check()
                qdrant_ok = True
                try:
                    cols = qdrant.get_collections()
                    qdrant_vectors = sum(
                        qdrant.get_collection(c.name).vectors_count or 0
                        for c in cols.collections
                    )
                except Exception:
                    qdrant_ok = False
                    qdrant_vectors = 0

                ram = psutil.virtual_memory()
                disk = psutil.disk_usage("/data")
                health_logger.log(
                    cpu_percent=psutil.cpu_percent(interval=None),
                    ram_used_gb=round((ram.total - ram.available) / 1e9, 2),
                    ram_total_gb=round(ram.total / 1e9, 2),
                    disk_used_gb=round(disk.used / 1e9, 2),
                    disk_total_gb=round(disk.total / 1e9, 2),
                    ollama_status="ok" if llm_ok else "error",
                    qdrant_status="ok" if qdrant_ok else "error",
                    model_loaded=os.environ.get("LLM_MODEL", "unknown"),
                    qdrant_vectors=qdrant_vectors,
                )
            except Exception as e:
                logger.warning(f"Health logger error: {e}")
            await asyncio.sleep(60)

    app.state.health_task = asyncio.create_task(health_logger_task())

    logger.info("=" * 60)
    logger.info("Axonri Banking — Ready to serve requests")
    logger.info("=" * 60)

    yield

    # ── SHUTDOWN ────────────────────────────────────────────────────────────
    logger.info("Axonri Banking — Shutting down")
    if hasattr(app.state, "health_task"):
        app.state.health_task.cancel()


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Axonri Banking",
        description="On-premise RAG for UCB compliance",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",    # Swagger UI
        redoc_url=None,
    )

    # CORS — same origin for branch + LAN for HO admin access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",   # dev frontend if separate
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth.router,      prefix="",       tags=["auth"])
    app.include_router(query.router,     prefix="",       tags=["query"])
    app.include_router(stt.router,       prefix="",       tags=["stt"])
    app.include_router(documents.router, prefix="",       tags=["documents"])
    app.include_router(admin.router,     prefix="",       tags=["admin"])
    app.include_router(health.router,    prefix="",       tags=["health"])

    # Serve frontend static files
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(os.path.join(static_dir, "index.html"))

        @app.get("/admin")
        async def serve_admin():
            return FileResponse(os.path.join(static_dir, "admin.html"))

    return app


app = create_app()
