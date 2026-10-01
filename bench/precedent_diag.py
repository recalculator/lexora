"""App precedent-retrieval diagnostic: does each app clause type get its 3 precedents?

Runs the app's own PgVectorRetriever against reference_clauses for a fixed
sample of eval clauses (seed 42), once per app clause type, using the app's
category map and top_k = 3, with the exact-filter fix switched OFF (the
pre-fix behaviour: filtered queries may use HNSW with a WHERE clause) and ON.

Writes bench/results/<timestamp>_<env>_precedent_diag.json (+ .md). Read-only
apart from planner settings scoped to its own transactions.

Usage: python bench/precedent_diag.py --env local
"""
import argparse
import json
import os
import random
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "bench"))

import run_bench as RB  # noqa: E402

SAMPLE = 100
TOP_K = 3  # precedents the app shows the LLM (app.services.rag.PRECEDENT_K)


@contextmanager
def fix_disabled():
    """Pre-fix behaviour: never switch filtered queries to exact search."""
    from app.services.retrieval import PgVectorRetriever
    original = PgVectorRetriever._uses_exact_filter
    PgVectorRetriever._uses_exact_filter = lambda self, filters: False
    try:
        yield
    finally:
        PgVectorRetriever._uses_exact_filter = original


def plan_indexes(plan):
    out = []

    def walk(node):
        out.append((node.get("Node Type"), node.get("Index Name")))
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return {"nodes": [n for n, _ in out], "indexes": sorted({i for _, i in out if i})}


def run_mode(vecs, app_types, fix_on):
    from sqlalchemy import text
    from app.db.session import SessionLocal
    from app.services.rag import PRECEDENT_K, load_category_map, precedent_categories
    from app.services.retrieval import PgVectorRetriever

    assert PRECEDENT_K == TOP_K, "app precedent count changed; update this diagnostic"
    mapping = load_category_map()
    out = {}
    session = SessionLocal()
    try:
        retriever = PgVectorRetriever(session, "reference_clauses")
        retriever.retrieve_by_vector(vecs[0], 1)  # loads pgvector so its settings can be shown
        settings = {name: session.execute(text(f"SHOW {name}")).scalar()
                    for name in ("hnsw.ef_search", "hnsw.iterative_scan")}
        for app_type in app_types:
            cats = precedent_categories(app_type) if mapping.get(app_type) else None
            filters = {"categories": cats} if cats else None
            counts = [len(retriever.retrieve_by_vector(v, TOP_K, filters)) for v in vecs]
            matching = session.execute(
                text("SELECT count(*) FROM reference_clauses WHERE categories && CAST(:c AS varchar[])"),
                {"c": cats},
            ).scalar() if cats else session.execute(text("SELECT count(*) FROM reference_clauses")).scalar()
            out[app_type] = {
                "filtered": bool(cats),
                "cuad_categories": cats,
                "matching_reference_rows": int(matching),
                "mean_returned": float(np.mean(counts)),
                "queries_below_top_k": int(sum(c < TOP_K for c in counts)),
                "queries": len(counts),
                "plan_first_query": plan_indexes(retriever.explain_by_vector(vecs[0], TOP_K, filters)),
            }
            RB.log(f"  fix {'on ' if fix_on else 'off'} {app_type}: mean {out[app_type]['mean_returned']:.2f} "
                   f"of {TOP_K}, short {out[app_type]['queries_below_top_k']}/{len(counts)}")
    finally:
        session.rollback()
        session.close()
    return {"session_settings": settings, "types": out}


def render(path: Path, r: dict):
    lines = [f"# Precedent retrieval diagnostic ({r['environment']['env']})\n",
             f"{r['sample_size']} eval clauses (seed {r['seed']}), top {r['top_k']} precedents per app clause type, "
             "app retriever and category map. 'Fix off' = filtered queries may use HNSW with a WHERE clause "
             "(pre-fix behaviour); 'fix on' = exact search over the categories GIN index.\n",
             "| App clause type | Filtered | Matching rows | Fix off: mean / short | Fix on: mean / short |",
             "|---|---|---|---|---|"]
    off, on = r["fix_off"]["types"], r["fix_on"]["types"]
    for t in r["app_clause_types"]:
        lines.append(
            f"| {t} | {'yes' if on[t]['filtered'] else 'no (unmapped)'} | {on[t]['matching_reference_rows']} | "
            f"{off[t]['mean_returned']:.2f} / {off[t]['queries_below_top_k']} | "
            f"{on[t]['mean_returned']:.2f} / {on[t]['queries_below_top_k']} |"
        )
    lines.append(f"\nSession settings: fix off {r['fix_off']['session_settings']}, "
                 f"fix on {r['fix_on']['session_settings']}.")
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["local", "azure"])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "bench/results")
    args = parser.parse_args()
    args.dry_run = False
    if "DATABASE_URL" not in os.environ:
        sys.exit("ERROR: DATABASE_URL must be set")

    from app.services.onnx_infer import CLAUSE_TYPES
    from app.services.retrieval import get_embedder

    rows = [r for r in map(json.loads, (ROOT / "bench/data/cuad_corpus.jsonl").read_text().splitlines())
            if r["split"] == "eval"]
    sample = random.Random(RB.SEED).sample(rows, SAMPLE)
    vecs = get_embedder().encode([r["text"] for r in sample])

    db = RB.DB(os.environ["DATABASE_URL"])
    n_ref = db.scalar("SELECT count(*) FROM reference_clauses")
    result = {
        "environment": RB.environment(db, args, ROOT / "bench/corpus/cuad_corpus_meta.json",
                                      ROOT / "bench/corpus/cuad_split.json", n_ref, len(rows)),
        "hnsw_index_size_bytes": int(db.scalar("SELECT pg_relation_size(%s::regclass)", (RB.HNSW_INDEX,))),
        "sample_size": SAMPLE,
        "seed": RB.SEED,
        "top_k": TOP_K,
        "app_clause_types": list(CLAUSE_TYPES),
    }
    RB.log("Fix off (pre-fix behaviour)")
    with fix_disabled():
        result["fix_off"] = run_mode(vecs, CLAUSE_TYPES, fix_on=False)
    RB.log("Fix on")
    result["fix_on"] = run_mode(vecs, CLAUSE_TYPES, fix_on=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out_dir / f"{stamp}_{args.env}_precedent_diag.json"
    if out.exists():
        sys.exit(f"ERROR: {out} exists")
    out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    render(out, result)
    RB.log(f"Wrote {out} and {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
