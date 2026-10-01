"""Load the CUAD reference split into reference_clauses with embeddings.

Embeds in batches and inserts in batches (one multi-row INSERT per batch).
Refuses to load into a non-empty table unless --replace is given, which
deletes the existing reference_clauses rows first.

Writes a load record (row counts, timings, environment) to --record.

Usage:
  python -m app.scripts.load_reference_corpus --corpus /repo/bench/data/cuad_corpus.jsonl \
      --record /repo/bench/results/load_<env>.json [--replace]
"""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import insert, text

from app.core.config import settings
from app.db.models import ReferenceClause
from app.db.session import SessionLocal
from app.services.retrieval import get_embedder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", default="reference")
    parser.add_argument("--embed-batch", type=int, default=64)
    parser.add_argument("--insert-batch", type=int, default=500)
    parser.add_argument("--replace", action="store_true", help="Delete existing reference_clauses rows first")
    parser.add_argument("--record", type=Path, help="Write a JSON load record here")
    parser.add_argument("--env", default="local")
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.corpus.read_text().splitlines()]
    rows = [r for r in rows if r["split"] == args.split]
    if not rows:
        sys.exit(f"ERROR: no rows with split={args.split!r} in {args.corpus}")

    embedder = get_embedder()
    if embedder is None:
        sys.exit("ERROR: embedding model unavailable")

    session = SessionLocal()
    try:
        existing = session.execute(text("SELECT count(*) FROM reference_clauses")).scalar()
        if existing and not args.replace:
            sys.exit(f"ERROR: reference_clauses already has {existing} rows; pass --replace to reload")
        if existing:
            session.execute(text("DELETE FROM reference_clauses"))
            print(f"Deleted {existing} existing rows")

        t0 = time.perf_counter()
        embeddings = embedder.encode([r["text"] for r in rows], batch_size=args.embed_batch)
        embed_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        for start in range(0, len(rows), args.insert_batch):
            batch = rows[start:start + args.insert_batch]
            session.execute(insert(ReferenceClause), [
                {
                    "source_contract": r["contract"],
                    "categories": r["categories"],
                    "text": r["text"],
                    "embedding": embeddings[start + i],
                }
                for i, r in enumerate(batch)
            ])
        session.commit()
        insert_s = time.perf_counter() - t0

        db_total = session.execute(text("SELECT count(*) FROM reference_clauses")).scalar()
        db_null = session.execute(text("SELECT count(*) FROM reference_clauses WHERE embedding IS NULL")).scalar()
        db_contracts = session.execute(text("SELECT count(DISTINCT source_contract) FROM reference_clauses")).scalar()
        db_per_cat = dict(session.execute(
            text("SELECT c, count(*) FROM reference_clauses, unnest(categories) AS c GROUP BY c ORDER BY c")
        ).fetchall())
        server = session.execute(text("SELECT version()")).scalar()
        pgvector = session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
    finally:
        session.close()

    expected_per_cat = dict(sorted(Counter(c for r in rows for c in r["categories"]).items()))
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env": args.env,
        "split": args.split,
        "corpus_file": str(args.corpus),
        "rows_in_corpus_split": len(rows),
        "rows_in_table": db_total,
        "rows_with_null_embedding": db_null,
        "distinct_contracts_in_table": db_contracts,
        "per_category_matches_corpus": db_per_cat == expected_per_cat,
        "multi_category_rows": sum(1 for r in rows if len(r["categories"]) > 1),
        "per_category": db_per_cat,
        "embed_seconds": round(embed_s, 3),
        "insert_seconds": round(insert_s, 3),
        "embed_batch": args.embed_batch,
        "insert_batch": args.insert_batch,
        "embedding_model": settings.embedding_model,
        "embedding_model_revision": settings.embedding_model_revision,
        "postgres_version": server,
        "pgvector_version": pgvector,
    }
    if db_total != len(rows) or db_null or not record["per_category_matches_corpus"]:
        print(json.dumps(record, indent=2))
        sys.exit("ERROR: loaded rows do not match the corpus split")
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Loaded {db_total} rows from {db_contracts} contracts across {len(db_per_cat)} categories "
          f"(embed {embed_s:.1f}s, insert {insert_s:.1f}s)")


if __name__ == "__main__":
    main()
