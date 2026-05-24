"""Documents router — list and manage corpus documents."""
from fastapi import APIRouter, Request
router = APIRouter()

@router.get("/api/documents")
async def list_documents(request: Request):
    """List all ingested documents with status."""
    from app.database import get_db, DocumentRecord
    db = next(get_db())
    try:
        docs = db.query(DocumentRecord).order_by(DocumentRecord.created_at.desc()).all()
        return [
            {
                "id":          d.id,
                "doc_name":    d.doc_name,
                "corpus_type": d.corpus_type,
                "status":      d.status,
                "chunk_count": d.chunk_count,
                "pages":       d.page_count,
                "ingested_at": d.ingested_at,
                "file_hash":   d.file_hash,
                "error":       d.error_message,
            }
            for d in docs
        ]
    finally:
        db.close()


@router.post("/api/admin/documents/{doc_id}/reingest")
async def reingest_document(doc_id: str, request: Request):
    """Trigger re-ingestion of a document (admin only)."""
    from app.database import get_db, DocumentRecord
    from fastapi import BackgroundTasks
    db = next(get_db())
    try:
        doc = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
        if not doc:
            from fastapi import HTTPException
            raise HTTPException(404, f"Document {doc_id} not found")

        # Update status
        doc.status = "PENDING"
        db.commit()

        # Run ingestion in background
        async def run_ingest():
            try:
                pipeline = request.app.state.ingest
                result = pipeline.ingest(
                    file_path=doc.file_path,
                    doc_name=doc.doc_name,
                    corpus_type=doc.corpus_type,
                )
                doc.status = result.status
                doc.chunk_count = result.chunk_count
                doc.ingested_at = result.duration_ms
                db.commit()
            except Exception as e:
                doc.status = "ERROR"
                doc.error_message = str(e)
                db.commit()

        import asyncio
        asyncio.create_task(run_ingest())

        return {"status": "queued", "doc_id": doc_id}
    finally:
        db.close()
