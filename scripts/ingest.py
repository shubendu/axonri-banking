#!/usr/bin/env python3
"""
Axonri corpus ingestion script.

Usage:
    # First time setup
    docker compose exec app python scripts/ingest.py

    # Force re-ingest all (ignore hash check)
    docker compose exec app python scripts/ingest.py --force

    # Ingest specific directory
    docker compose exec app python scripts/ingest.py --dir /data/corpus/rbi/ucb

    # Check what would be ingested (dry run)
    docker compose exec app python scripts/ingest.py --dry-run

Environment:
    Reads QDRANT_HOST, QDRANT_PORT, VECTORS_DIR, LOG_DIR from environment.
    Set these in docker-compose.yml.
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add parent directory so we can import axonri_core and app
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from axonri_core.ingestion import IngestPipeline
from axonri_core.bm25 import BM25Manager
from axonri_core.logging import IngestionLogger
from axonri_core.utils.hash import sha256_file
from app.domain_config import banking_config
from app.database import SessionLocal, DocumentRecord, init_db


def parse_args():
    parser = argparse.ArgumentParser(description="Axonri corpus ingestion")
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Specific directory to ingest (default: all corpus dirs)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if file hash unchanged",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be ingested without actually doing it",
    )
    return parser.parse_args()


CORPUS_DIRS = [
    ("/data/corpus/rbi/ucb",           "regulatory"),
    ("/data/corpus/rbi/crosscutting",  "regulatory"),
]


def main():
    args = parse_args()

    # Init DB
    init_db()
    db = SessionLocal()

    # Init services
    qdrant = QdrantClient(
        host=os.environ.get("QDRANT_HOST", "localhost"),
        port=int(os.environ.get("QDRANT_PORT", "6333")),
        timeout=30,
    )
    vectors_dir = os.environ.get("VECTORS_DIR", "/data/vectors")
    bm25 = BM25Manager(persist_path=os.path.join(vectors_dir, "bm25.pkl"))
    pipeline = IngestPipeline(config=banking_config, qdrant=qdrant, bm25=bm25)
    ingest_logger = IngestionLogger(log_dir=os.environ.get("LOG_DIR", "/data/logs"))

    # Determine which directories to scan
    if args.dir:
        corpus_dirs = [(args.dir, "regulatory")]
    else:
        corpus_dirs = CORPUS_DIRS

    total = skipped = updated = failed = 0
    t_start = time.monotonic()

    for corpus_dir, corpus_type in corpus_dirs:
        path = Path(corpus_dir)
        if not path.exists():
            print(f"[warn] Directory not found: {corpus_dir} — skipping")
            continue

        pdfs = sorted(path.glob("*.pdf"))
        if not pdfs:
            print(f"[warn] No PDFs found in {corpus_dir}")
            continue

        print(f"\n[ingest] Scanning: {corpus_dir} ({len(pdfs)} PDFs)")

        for pdf in pdfs:
            total += 1
            file_hash = sha256_file(str(pdf))

            # Check existing record
            existing = (
                db.query(DocumentRecord)
                .filter(DocumentRecord.file_path == str(pdf))
                .first()
            )

            if existing and existing.file_hash == file_hash and not args.force:
                print(f"  [skip]   {pdf.name}")
                skipped += 1
                continue

            if args.dry_run:
                print(f"  [would ingest] {pdf.name}")
                updated += 1
                continue

            # Update or create DB record
            if existing:
                existing.status = "INGESTING"
                existing.file_hash = file_hash
            else:
                existing = DocumentRecord(
                    doc_name=pdf.stem.replace("_", " ").title(),
                    file_path=str(pdf),
                    corpus_type=corpus_type,
                    file_hash=file_hash,
                    status="INGESTING",
                )
                db.add(existing)
            db.commit()

            print(f"  [ingest] {pdf.name}...", end=" ", flush=True)
            t_doc = time.monotonic()

            try:
                result = pipeline.ingest(
                    file_path=str(pdf),
                    doc_name=existing.doc_name,
                    corpus_type=corpus_type,
                    file_hash=file_hash,
                )
                duration_ms = int((time.monotonic() - t_doc) * 1000)
                print(f"{result.chunk_count} chunks ({duration_ms}ms)")

                existing.status = "READY"
                existing.chunk_count = result.chunk_count
                existing.vector_count = result.vector_count
                existing.page_count = result.pages_parsed
                existing.ingested_at = __import__('datetime').datetime.utcnow().isoformat()
                existing.error_message = None
                db.commit()

                ingest_logger.log(
                    doc_id=result.doc_id, doc_name=result.doc_name,
                    file_path=str(pdf), file_hash=file_hash,
                    trigger="script", status="success",
                    pages_parsed=result.pages_parsed,
                    chunks_created=result.chunk_count,
                    vectors_upserted=result.vector_count,
                    duration_ms=duration_ms,
                )
                updated += 1

            except Exception as e:
                duration_ms = int((time.monotonic() - t_doc) * 1000)
                print(f"FAILED: {e}")
                existing.status = "ERROR"
                existing.error_message = str(e)[:500]
                db.commit()
                ingest_logger.log(
                    doc_id="", doc_name=pdf.name,
                    file_path=str(pdf), file_hash=file_hash,
                    trigger="script", status="error",
                    duration_ms=duration_ms,
                    errors=[str(e)],
                )
                failed += 1

    db.close()
    total_time = int((time.monotonic() - t_start))

    print(f"\n{'='*50}")
    print(f"Ingestion complete in {total_time}s")
    print(f"  {total} files scanned")
    print(f"  {updated} ingested/updated")
    print(f"  {skipped} skipped (unchanged)")
    print(f"  {failed} failed")
    if args.dry_run:
        print("  [DRY RUN — no files were actually ingested]")
    if failed > 0:
        print(f"\nCheck logs for details: /data/logs/ingestion.ndjson")
        sys.exit(1)


if __name__ == "__main__":
    main()
