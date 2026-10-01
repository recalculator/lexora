"""Post-hoc analyses (see the 2026-10-01 post-hoc amendment in bench/PREREGISTRATION.md).

Reads an original results file and its per-query companion (read-only) and
writes a NEW file bench/results/<timestamp>_<env>_posthoc.json (+ .md):

  1. exact filtered search latency alongside the other filtered modes
  2. paired bootstrap of clause-set P@3/P@10 differences vs tfidf
  3. diagnostics: queries whose HNSW leg returns fewer than 50 candidates
     at ef_search=50, plus vacuum state of reference_clauses

Usage: python bench/posthoc.py --env local --original bench/results/<stamp>_<env>.json
"""
import argparse
import gzip
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "bench"))

import metrics as M  # noqa: E402
import run_bench as RB  # noqa: E402

PAIRED_RESAMPLES = 10_000
COMPARISONS = [("hybrid", "tfidf"), ("vector_exact", "tfidf")]
PAIRED_METRICS = ["precision@3", "precision@10"]


def paired_bootstrap(original, per_query, ref_cats):
    qs = per_query["clause"]
    pairs = [tuple(p) for p in qs["pairs"]]
    scores = {}
    for method, rankings in qs["rankings"].items():
        rows = []
        for text_idx, cat in pairs:
            ranked = [cat in ref_cats[d] for d in rankings[text_idx]]
            rows.append([M.precision_at_k(ranked, 3), M.precision_at_k(ranked, 10)])
        scores[method] = np.asarray(rows)
        recorded = original["part_a"]["query_sets"]["clause"]["methods"][method]["mean"]
        for j, metric in enumerate(PAIRED_METRICS):
            if not np.isclose(scores[method][:, j].mean(), recorded[metric], rtol=0, atol=1e-12):
                raise RuntimeError(f"{method} {metric}: recomputed mean does not match the original results file")

    rng = np.random.default_rng(RB.SEED)
    n = len(pairs)
    out = {"n_queries": n, "resamples": PAIRED_RESAMPLES, "seed": RB.SEED, "recomputed_means_match_original": True,
           "comparisons": {}}
    diffs = {f"{a} - {b}": scores[a] - scores[b] for a, b in COMPARISONS}
    boot = {key: [] for key in diffs}
    for start in range(0, PAIRED_RESAMPLES, 500):
        idx = rng.integers(0, n, size=(min(500, PAIRED_RESAMPLES - start), n))
        for key, d in diffs.items():
            boot[key].append(d[idx].mean(axis=1))
    for key, d in diffs.items():
        b = np.concatenate(boot[key])
        out["comparisons"][key] = {
            metric: {
                "mean_difference": float(d[:, j].mean()),
                "ci95": [float(np.percentile(b[:, j], 2.5)), float(np.percentile(b[:, j], 97.5))],
                "share_of_queries_better": float((d[:, j] > 0).mean()),
                "share_of_queries_worse": float((d[:, j] < 0).mean()),
            }
            for j, metric in enumerate(PAIRED_METRICS)
        }
    return out


def filtered_with_exact(db, eval_vecs, original):
    categories = list(original["part_b_filtered"]["categories"])
    rng = random.Random(RB.SEED)
    sample = rng.sample(range(len(eval_vecs)), min(RB.FILTER_SAMPLE, len(eval_vecs)))
    qvecs = [eval_vecs[i] for i in sample]
    if len(qvecs) != original["part_b_filtered"]["n_queries_per_category"]:
        raise RuntimeError("Query sample size differs from the original run")

    modes = {
        "exact_filtered_gin": {"enable_indexscan": "off", "enable_seqscan": "off"},
        "planner_default": {"hnsw__ef_search": RB.DEFAULT_EF_SEARCH},
        "hnsw_forced": {"hnsw__ef_search": RB.DEFAULT_EF_SEARCH, "enable_seqscan": "off", "enable_bitmapscan": "off"},
        "hnsw_forced_iterative_relaxed_order": {"hnsw__ef_search": RB.DEFAULT_EF_SEARCH, "enable_seqscan": "off",
                                                "enable_bitmapscan": "off", "hnsw__iterative_scan": "relaxed_order"},
        "hnsw_forced_iterative_strict_order": {"hnsw__ef_search": RB.DEFAULT_EF_SEARCH, "enable_seqscan": "off",
                                               "enable_bitmapscan": "off", "hnsw__iterative_scan": "strict_order"},
    }
    out = {"n_queries_per_category": len(qvecs), "categories": {}}
    for cat in categories:
        group = original["part_b_filtered"]["categories"][cat]["group"]
        sql_fn = lambda v, c=cat: (RB.FILTERED_KNN_SQL, (c, RB.vec(v), RB.TOP_K))  # noqa: E731
        db.reset()
        db.set(enable_indexscan="off")
        exact = [[r[0] for r in db.q(*sql_fn(v))] for v in qvecs]
        db.reset()
        n_rows = db.scalar("SELECT count(*) FROM reference_clauses WHERE categories @> ARRAY[%s]::varchar[]", (cat,))
        expected = min(RB.TOP_K, n_rows)
        entry = {"group": group, "reference_rows": n_rows, "modes": {}}
        for mode, settings in modes.items():
            db.reset()
            db.set(**settings)
            for v in qvecs[:10]:  # warmup, discarded
                db.q(*sql_fn(v))
            lat, res = [], []
            for v in qvecs:
                t0 = time.perf_counter()
                rows = db.q(*sql_fn(v))
                lat.append((time.perf_counter() - t0) * 1000)
                res.append([r[0] for r in rows])
            server = RB.server_pass(db, qvecs, sql_fn)
            db.reset()
            counts = [len(r) for r in res]
            entry["modes"][mode] = {
                "settings": settings,
                "recall@10_vs_exact_filtered": float(np.mean([M.ann_recall(a, e) for a, e in zip(res, exact)])),
                "mean_result_count": float(np.mean(counts)),
                "share_below_expected_count": float(np.mean([c < expected for c in counts])),
                "expected_count": expected,
                "client_ms": M.percentiles(lat),
                "server_execution_ms": server["execution_ms"],
                "plans": server["distinct_plans"],
            }
        if any(p["seq_scan"] or p["uses_hnsw"] for p in entry["modes"]["exact_filtered_gin"]["plans"]):
            raise RuntimeError(f"{cat}: exact_filtered_gin did not use the GIN index alone")
        out["categories"][cat] = entry
        m = entry["modes"]["exact_filtered_gin"]
        RB.log(f"  {cat}: exact GIN recall={m['recall@10_vs_exact_filtered']:.3f} "
               f"client p50={m['client_ms']['p50']:.2f}ms server p50={m['server_execution_ms']['p50']:.3f}ms")
    return out


def hybrid_candidate_diagnostics(db, texts_vecs):
    db.reset()
    db.set(hnsw__ef_search=RB.HYBRID_EF_SEARCH)
    short = []
    for name, (texts, vecs) in texts_vecs.items():
        for i, (t, v) in enumerate(zip(texts, vecs)):
            n = len(RB.knn(db, v, RB.HYBRID_CANDIDATES))
            if n < RB.HYBRID_CANDIDATES:
                short.append({"query_set": name, "text_index": i, "returned": n, "text_prefix": t[:120]})
    db.reset()
    stats = db.q(
        "SELECT n_live_tup, n_dead_tup, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze "
        "FROM pg_stat_user_tables WHERE relname = 'reference_clauses'"
    )[0]
    return {
        "note": "Measured on the current index (rebuilt by part B of the original run), not the index Part A used.",
        "hnsw_ef_search": RB.HYBRID_EF_SEARCH,
        "queries_returning_fewer_than_50": short,
        "reference_clauses_stats": {
            "n_live_tup": stats[0], "n_dead_tup": stats[1],
            "last_vacuum": str(stats[2]), "last_autovacuum": str(stats[3]),
            "last_analyze": str(stats[4]), "last_autoanalyze": str(stats[5]),
        },
    }


def render(path: Path, r: dict):
    lines = [f"# Post-hoc analyses ({r['environment']['env']})\n",
             f"**Post-hoc**: designed after the results in `{r['original_results']}` were seen "
             "(see the 2026-10-01 post-hoc amendment in `bench/PREREGISTRATION.md`).\n",
             "## Paired bootstrap, clause-as-query (original run's per-query rankings)\n"]
    pb = r["paired_bootstrap"]
    lines.append(f"{pb['n_queries']} queries, {pb['resamples']} resamples, seed {pb['seed']}.\n")
    lines.append(RB_table(["Comparison", "Metric", "Mean paired difference", "95% CI", "Queries better / worse"], [
        [k, m, f"{v['mean_difference']:+.4f}", f"[{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]",
         f"{v['share_of_queries_better']:.3f} / {v['share_of_queries_worse']:.3f}"]
        for k, ms in pb["comparisons"].items() for m, v in ms.items()
    ]))
    lines.append("\n## Filtered search including exact GIN search\n")
    fx = r["filtered"]
    modes = list(next(iter(fx["categories"].values()))["modes"])
    lines.append("Cells: recall@10 / mean results / client p50 ms / server p50 ms.\n")
    lines.append(RB_table(["Group", "Category", "Ref rows"] + modes, [
        [e["group"], c, e["reference_rows"]] + [
            f"{e['modes'][m]['recall@10_vs_exact_filtered']:.3f} / {e['modes'][m]['mean_result_count']:.1f} / "
            f"{e['modes'][m]['client_ms']['p50']:.2f} / {e['modes'][m]['server_execution_ms']['p50']:.3f}"
            for m in modes]
        for c, e in fx["categories"].items()
    ]))
    d = r["diagnostics"]
    lines.append("\n## Diagnostics: hybrid HNSW leg candidates\n")
    lines.append(f"{d['note']} Queries returning fewer than 50 at ef_search={d['hnsw_ef_search']}: "
                 f"{len(d['queries_returning_fewer_than_50'])}. Table stats: {d['reference_clauses_stats']}.\n")
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")


def RB_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["local", "azure"])
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "bench/results")
    args = parser.parse_args()
    args.dry_run = False

    original = json.loads(args.original.read_text())
    if original["environment"]["env"] != args.env:
        sys.exit("ERROR: --env does not match the original results file")
    with gzip.open(args.original.with_name(args.original.stem + "_perquery.json.gz"), "rt") as f:
        per_query = json.load(f)

    from app.services.retrieval import get_embedder
    split = json.loads((ROOT / "bench/corpus/cuad_split.json").read_text())
    eval_rows = [r for r in map(json.loads, (ROOT / "bench/data/cuad_corpus.jsonl").read_text().splitlines())
                 if r["split"] == "eval"]
    questions = [{"category": c, "text": q} for c, q in split["category_questions"].items()]

    db = RB.DB(os.environ["DATABASE_URL"])
    ref = db.q("SELECT id, categories FROM reference_clauses")
    # Same data and server as the original run. The git commit is recorded but
    # deliberately not compared: committing the fix/script changes it.
    orig_env = original["environment"]
    checks = {
        "reference_rows": (len(ref), orig_env["corpus"]["reference_rows"]),
        "postgres_version": (db.scalar("SELECT version()"), orig_env["postgres_version"]),
        "pgvector_version": (db.scalar("SELECT extversion FROM pg_extension WHERE extname = 'vector'"),
                             orig_env["pgvector_version"]),
        "corpus_meta_sha256": (RB.sha256_file(ROOT / "bench/corpus/cuad_corpus_meta.json"),
                               orig_env["corpus"]["corpus_meta_sha256"]),
        "split_sha256": (RB.sha256_file(ROOT / "bench/corpus/cuad_split.json"), orig_env["corpus"]["split_sha256"]),
    }
    mismatches = {k: v for k, v in checks.items() if v[0] != v[1]}
    if mismatches:
        sys.exit(f"ERROR: environment differs from the original run: {mismatches}")
    ref_cats = {i: set(c) for i, c in ref}

    embedder = get_embedder()
    eval_vecs = embedder.encode([r["text"] for r in eval_rows])
    question_vecs = embedder.encode([q["text"] for q in questions])

    result = {
        "posthoc": True,
        "amendment": "bench/PREREGISTRATION.md, 2026-10-01 post-hoc amendment",
        "original_results": str(args.original.relative_to(ROOT)) if args.original.is_absolute() else str(args.original),
        "environment": RB.environment(db, args, ROOT / "bench/corpus/cuad_corpus_meta.json",
                                      ROOT / "bench/corpus/cuad_split.json", len(ref), len(eval_rows)),
    }
    RB.log("Paired bootstrap")
    result["paired_bootstrap"] = paired_bootstrap(original, per_query, ref_cats)
    RB.log("Filtered search with exact GIN mode")
    result["filtered"] = filtered_with_exact(db, eval_vecs, original)
    RB.log("Diagnostics")
    result["diagnostics"] = hybrid_candidate_diagnostics(db, {
        "clause": ([r["text"] for r in eval_rows], eval_vecs),
        "question": ([q["text"] for q in questions], question_vecs),
    })

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out_dir / f"{stamp}_{args.env}_posthoc.json"
    if out.exists():
        sys.exit(f"ERROR: {out} exists")
    out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    render(out, result)
    RB.log(f"Wrote {out} and {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
