"""Health check endpoint."""

import os
import psutil
from fastapi import APIRouter, Request
from axonri_core.utils.network import run_network_check

router = APIRouter()


@router.get("/api/health")
async def health(request: Request):
    """
    System health check. Returns overall status + per-component checks.
    Public endpoint — no auth required (used by monitoring and admin dashboard).
    """
    checks = {}
    overall = "ok"

    # 1. LLM
    llm = request.app.state.llm
    llm_ok = await llm.health_check()
    llm_host = os.environ.get("LLM_HOST", "unknown")
    llm_port = os.environ.get("LLM_PORT", "8080")
    checks["llm"] = {
        "status": "ok" if llm_ok else "error",
        "host":   llm_host,
        "port":   llm_port,
        "model":  os.environ.get("LLM_MODEL", "unknown"),
    }
    if not llm_ok:
        overall = "degraded"

    # 2. Qdrant
    try:
        qdrant = request.app.state.qdrant
        cols = qdrant.get_collections()
        domain_config = request.app.state.domain_config
        collection_exists = any(
            c.name == domain_config.collection_name
            for c in cols.collections
        )
        if collection_exists:
            col_info = qdrant.get_collection(domain_config.collection_name)
            vector_count = getattr(col_info, 'points_count', None) or getattr(col_info, 'vectors_count', None) or 0
        else:
            vector_count = 0

        checks["qdrant"] = {
            "status":           "ok",
            "collection":       domain_config.collection_name,
            "collection_exists":collection_exists,
            "vector_count":     vector_count,
        }
        if not collection_exists:
            checks["qdrant"]["status"] = "warning"
            checks["qdrant"]["note"] = "Collection not found — run ingestion script"
            overall = "degraded"
    except Exception as e:
        checks["qdrant"] = {"status": "error", "error": str(e)}
        overall = "degraded"

    # 3. BM25
    bm25 = request.app.state.bm25
    checks["bm25"] = {"status": "ok", "chunk_count": bm25.size}

    # 4. STT (Whisper)
    from app.routers.stt import _model as whisper_model
    checks["stt"] = {
        "status": "ok" if whisper_model else "loading",
        "model":  "whisper-small",
    }

    # 5. Disk
    try:
        disk = psutil.disk_usage("/data")
        disk_pct = round(disk.used / disk.total * 100, 1)
        checks["disk"] = {
            "status":   "warning" if disk_pct > 85 else "ok",
            "used_pct": disk_pct,
            "free_gb":  round(disk.free / 1e9, 1),
            "total_gb": round(disk.total / 1e9, 1),
        }
        if disk_pct > 85:
            overall = "degraded"
    except Exception as e:
        checks["disk"] = {"status": "error", "error": str(e)}

    # 6. RAM
    try:
        ram = psutil.virtual_memory()
        checks["ram"] = {
            "used_pct":     round(ram.percent, 1),
            "used_gb":      round((ram.total - ram.available) / 1e9, 1),
            "available_gb": round(ram.available / 1e9, 1),
            "total_gb":     round(ram.total / 1e9, 1),
        }
    except Exception as e:
        checks["ram"] = {"status": "error", "error": str(e)}

    return {
        "status":  overall,
        "version": "1.0.0",
        "domain":  request.app.state.domain_config.domain_id,
        "checks":  checks,
    }


@router.get("/api/health/network")
async def network_check(request: Request):
    """
    Diagnostic: check which hosts can reach the LLM from inside Docker.
    Useful during deployment troubleshooting.
    Only accessible to admin users in production.
    """
    port = int(os.environ.get("LLM_PORT", "8080"))
    return {
        "llm_port": port,
        "current_host": os.environ.get("LLM_HOST", "not set"),
        "candidates": run_network_check(port),
    }
