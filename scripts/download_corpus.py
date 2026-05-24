#!/usr/bin/env python3
"""
Download all RBI corpus documents.

Usage:
    python scripts/download_corpus.py
    python scripts/download_corpus.py --priority critical
    python scripts/download_corpus.py --dry-run

Downloads PDFs to /data/corpus/rbi/ucb/ and /data/corpus/rbi/crosscutting/
Only downloads files that don't already exist (safe to re-run).
"""
import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.domain_config import RBI_DOCUMENT_CORPUS


UCB_DIR   = Path("/data/corpus/rbi/ucb")
CROSS_DIR = Path("/data/corpus/rbi/crosscutting")

CATEGORY_DIR_MAP = {
    "credit":     UCB_DIR,
    "governance": UCB_DIR,
    "operations": UCB_DIR,
    "loans":      UCB_DIR,
    "kyc":        CROSS_DIR,
    "general":    CROSS_DIR,
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--priority", choices=["critical","high","medium","low","all"],
                   default="all", help="Only download docs with this priority")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()

    # Create directories
    UCB_DIR.mkdir(parents=True, exist_ok=True)
    CROSS_DIR.mkdir(parents=True, exist_ok=True)

    docs = RBI_DOCUMENT_CORPUS
    if args.priority != "all":
        docs = [d for d in docs if d.get("priority") == args.priority]

    print(f"\nAxonri — RBI Corpus Downloader")
    print(f"Documents to process: {len(docs)}")
    print(f"Priority filter: {args.priority}")
    print("-" * 60)

    downloaded = skipped = failed = 0

    for doc in docs:
        dest_dir  = CATEGORY_DIR_MAP.get(doc.get("category","general"), UCB_DIR)
        dest_path = dest_dir / doc["filename"]

        if dest_path.exists():
            size_kb = dest_path.stat().st_size // 1024
            print(f"  [skip]   {doc['filename']} ({size_kb}KB already exists)")
            skipped += 1
            continue

        note = doc.get("note", "")
        if note:
            print(f"\n  [manual] {doc['doc_name']}")
            print(f"           NOTE: {note}")
            print(f"           URL:  {doc['url']}")
            print(f"           Save to: {dest_path}")
            continue

        if args.dry_run:
            print(f"  [would download] {doc['filename']}")
            downloaded += 1
            continue

        print(f"  [download] {doc['doc_name']}...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(doc["url"], str(dest_path))
            size_kb = dest_path.stat().st_size // 1024
            print(f"OK ({size_kb}KB)")
            downloaded += 1
            time.sleep(0.5)   # be polite to rbi.org.in
        except Exception as e:
            print(f"FAILED: {e}")
            print(f"         Manual download: {doc['url']}")
            print(f"         Save to: {dest_path}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Done: {downloaded} downloaded, {skipped} skipped, {failed} failed")
    if failed > 0:
        print("Download failed docs manually from the URLs shown above.")


if __name__ == "__main__":
    main()
