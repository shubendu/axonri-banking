"""Admin router — logs, users, corpus management."""
from fastapi import APIRouter, Request, Query
router = APIRouter()

@router.get("/api/admin/logs/queries")
async def query_logs(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Paginated query log."""
    from app.database import get_db, QueryLog
    db = next(get_db())
    try:
        total = db.query(QueryLog).count()
        logs = (
            db.query(QueryLog)
            .order_by(QueryLog.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "logs": [
                {
                    "id":           l.id,
                    "username":     l.username,
                    "query_text":   l.query_text,
                    "answer_text":  l.answer_text[:150] if l.answer_text else "",
                    "sources":      l.sources_json,
                    "input_method": l.input_method,
                    "duration_ms":  l.duration_ms,
                    "status":       l.status,
                    "created_at":   l.created_at,
                }
                for l in logs
            ],
        }
    finally:
        db.close()

@router.get("/api/admin/logs/queries/{query_id}")
async def query_log_detail(query_id: str):
    """Full detail for a single query (for debugging)."""
    from app.database import get_db, QueryLog
    import json
    db = next(get_db())
    try:
        log = db.query(QueryLog).filter(QueryLog.id == query_id).first()
        if not log:
            from fastapi import HTTPException
            raise HTTPException(404, f"Query {query_id} not found")
        return {
            "id":              log.id,
            "query_text":      log.query_text,
            "answer_text":     log.answer_text,
            "sources":         json.loads(log.sources_json or "[]"),
            "input_method":    log.input_method,
            "model_used":      log.model_used,
            "tokens_generated":log.tokens_generated,
            "duration_ms":     log.duration_ms,
            "status":          log.status,
            "created_at":      log.created_at,
        }
    finally:
        db.close()
