"""Retrieval benchmark harness (see bench/PREREGISTRATION.md for the design).

Writes bench/results/<timestamp>_<env>.json (+ a per-query .json.gz) and then
calls bench/report.py to render the markdown summary and plots.

Expects a migrated database with the CUAD reference split loaded
(app.scripts.load_reference_corpus). Run via `make bench ENV=local|azure`.

Part B drops and rebuilds vector indexes on reference_clauses and always
restores the migration's default HNSW index (m=16, ef_construction=64) at the
end, then checks the index set matches what it was at the start.
"""
import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "bench"))

import metrics as M  # noqa: E402

SEED = 42
TOP_K = 10
HYBRID_CANDIDATES = 50
HYBRID_EF_SEARCH = 50
DEFAULT_EF_SEARCH = 40
EF_SEARCH_VALUES = [10, 20, 40, 80, 160]
WARMUP_QUERIES = 100
FILTER_SAMPLE = 200
HNSW_INDEX = "ix_reference_clauses_embedding_hnsw"
HNSW_DEFAULT_DDL = (
    f"CREATE INDEX {HNSW_INDEX} ON reference_clauses "
    "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
)
KNN_SQL = "SELECT id FROM reference_clauses ORDER BY embedding <=> %s::vector LIMIT %s"
FILTERED_KNN_SQL = (
    "SELECT id FROM reference_clauses WHERE categories @> ARRAY[%s]::varchar[] "
    "ORDER BY embedding <=> %s::vector LIMIT %s"
)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vec(v) -> str:
    return "[" + ",".join(f"{float(x):.8g}" for x in v) + "]"


# ---------------------------------------------------------------------------
# Database helpers (raw psycopg2 connection, autocommit, session-level SETs)
# ---------------------------------------------------------------------------

class DB:
    def __init__(self, url: str):
        import psycopg2
        from app.db.session import ensure_sslmode
        self.conn = psycopg2.connect(ensure_sslmode(url))
        self.conn.autocommit = True
        self.cur = self.conn.cursor()

    def q(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur.fetchall() if self.cur.description else None

    def scalar(self, sql, params=None):
        rows = self.q(sql, params)
        return rows[0][0] if rows else None

    def set(self, **settings):
        for name, value in settings.items():
            self.cur.execute(f"SET {name.replace('__', '.')} = %s", (str(value),))

    def reset(self):
        self.cur.execute("RESET ALL")

    def explain(self, sql, params, analyze=False):
        opts = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
        self.cur.execute(f"EXPLAIN ({opts}) " + sql, params)
        return self.cur.fetchone()[0][0]


def plan_nodes(plan) -> list:
    """Flatten an EXPLAIN JSON plan into [(node type, index name)]."""
    out = []

    def walk(node):
        out.append((node.get("Node Type"), node.get("Index Name")))
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return out


def plan_summary(plan) -> dict:
    nodes = plan_nodes(plan)
    return {
        "nodes": [n for n, _ in nodes],
        "indexes": sorted({i for _, i in nodes if i}),
        "uses_hnsw": any(i and "hnsw" in i for _, i in nodes),
        "uses_ivfflat": any(i and "ivfflat" in i for _, i in nodes),
        "seq_scan": any(n == "Seq Scan" for n, _ in nodes),
    }


def vector_index_names(db) -> list:
    return [r[0] for r in db.q(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'reference_clauses' "
        "AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')"
    )]


def index_definitions(db) -> list:
    return sorted(r[0] for r in db.q(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'reference_clauses'"
    ))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def environment(db, args, corpus_meta_path, split_path, n_reference, n_eval_rows):
    from app.core.config import settings
    url = urlparse(os.environ["DATABASE_URL"])
    show = {}
    for name in ["shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
                 "max_parallel_workers_per_gather", "max_parallel_maintenance_workers",
                 "hnsw.ef_search", "hnsw.iterative_scan", "hnsw.max_scan_tuples", "ivfflat.probes"]:
        try:
            show[name] = db.scalar(f"SHOW {name}")
        except Exception as e:  # GUC missing on this server/pgvector version
            show[name] = f"unavailable: {type(e).__name__}"
    cpu_model = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith(("model name", "cpu model")):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "env": args.env,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "postgres_version": db.scalar("SELECT version()"),
        "postgres_server_version_num": db.scalar("SHOW server_version_num"),
        "pgvector_version": db.scalar("SELECT extversion FROM pg_extension WHERE extname = 'vector'"),
        "db_host": url.hostname,
        "db_ssl": db.conn.info.ssl_in_use,
        "host_description": os.getenv("BENCH_HOST_DESC") or ("local Docker" if args.env == "local" else None),
        "azure_sku": os.getenv("BENCH_AZURE_SKU"),
        "server_settings": show,
        "client": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count_visible": os.cpu_count(),
            "cpu_model_container": cpu_model,
            "host_cpu": os.getenv("BENCH_CLIENT_CPU"),
            "docker_resources": os.getenv("BENCH_DOCKER_RESOURCES"),
        },
        "corpus": {
            "reference_rows": n_reference,
            "eval_rows": n_eval_rows,
            "corpus_meta_sha256": sha256_file(corpus_meta_path),
            "split_sha256": sha256_file(split_path),
        },
        "embedding_model": settings.embedding_model,
        "embedding_model_revision": settings.embedding_model_revision,
        "seed": SEED,
        "git": {
            "commit": os.getenv("GIT_COMMIT"),
            "dirty_files": int(os.getenv("GIT_DIRTY_FILES", "-1")),
            "diff_sha256": os.getenv("GIT_DIFF_SHA"),
        },
    }


# ---------------------------------------------------------------------------
# Part A: retrieval quality
# ---------------------------------------------------------------------------

def knn(db, qvec, k=TOP_K):
    return [r[0] for r in db.q(KNN_SQL, (vec(qvec), k))]


def part_a(db, ref, eval_rows, eval_vecs, questions, question_vecs, categories, args):
    from app.services.retrieval import TfidfRetriever, rrf_fuse

    ref_cats = {r["id"]: set(r["categories"]) for r in ref}
    n_relevant = {c: sum(1 for r in ref if c in r["categories"]) for c in categories}
    tfidf = TfidfRetriever(ids=[r["id"] for r in ref], texts=[r["text"] for r in ref])

    # Distinct query texts; relevance is applied per (text, category) afterwards
    texts = {
        "clause": [r["text"] for r in eval_rows],
        "question": [q["text"] for q in questions],
    }
    vecs = {"clause": eval_vecs, "question": question_vecs}
    query_sets = {
        "clause": [(i, c) for i, r in enumerate(eval_rows) for c in r["categories"]],
        "question": [(i, q["category"]) for i, q in enumerate(questions)],
    }

    # EXPLAIN checks for the vector methods
    probe = vec(eval_vecs[0])
    db.reset()
    db.set(enable_indexscan="off")
    exact_plan = plan_summary(db.explain(KNN_SQL, (probe, TOP_K)))
    db.reset()
    db.set(hnsw__ef_search=DEFAULT_EF_SEARCH)
    hnsw_plan = plan_summary(db.explain(KNN_SQL, (probe, TOP_K)))
    db.reset()
    if exact_plan["uses_hnsw"] or not hnsw_plan["uses_hnsw"]:
        raise RuntimeError(f"Unexpected plans: exact={exact_plan} hnsw={hnsw_plan}")

    rankings = {}
    for name in ("clause", "question"):
        log(f"Part A: retrieving for {len(texts[name])} {name} texts")
        tf_top = [[r.clause_id for r in tfidf.retrieve(t, top_k=HYBRID_CANDIDATES)] for t in texts[name]]
        db.set(enable_indexscan="off")
        exact = [knn(db, v) for v in vecs[name]]
        db.reset()
        db.set(hnsw__ef_search=DEFAULT_EF_SEARCH)
        hnsw = [knn(db, v) for v in vecs[name]]
        db.set(hnsw__ef_search=HYBRID_EF_SEARCH)
        hnsw50 = [knn(db, v, HYBRID_CANDIDATES) for v in vecs[name]]
        db.reset()
        hybrid = [[d for d, _ in rrf_fuse([a, b], k=60)][:TOP_K] for a, b in zip(tf_top, hnsw50)]
        rankings[name] = {
            "tfidf": [t[:TOP_K] for t in tf_top],
            "vector_exact": exact,
            "vector_hnsw": hnsw,
            "hybrid": hybrid,
            "_hybrid_hnsw_candidates": [len(x) for x in hnsw50],
        }

    results = {"plans": {"vector_exact": exact_plan, "vector_hnsw": hnsw_plan}, "query_sets": {}}
    per_query = {}
    methods = ["tfidf", "vector_exact", "vector_hnsw", "hybrid"]
    for name, pairs in query_sets.items():
        set_out = {"n_queries": len(pairs), "n_distinct_texts": len(texts[name]), "methods": {}}
        set_out["hybrid_hnsw_candidates_min"] = int(min(rankings[name]["_hybrid_hnsw_candidates"]))
        per_query[name] = {"pairs": pairs, "rankings": {m: rankings[name][m] for m in methods}}
        for m in methods:
            rows, by_cat = [], defaultdict(list)
            for text_idx, cat in pairs:
                ranked = [cat in ref_cats[d] for d in rankings[name][m][text_idx]]
                qm = M.query_metrics(ranked, n_relevant[cat])
                rows.append(qm)
                by_cat[cat].append(qm)
            per_cat = {c: {"n_queries": len(v), **M.mean_metrics(v)} for c, v in sorted(by_cat.items())}
            weakest = sorted(per_cat.items(), key=lambda kv: (kv[1]["precision@10"], kv[0]))[:5]
            set_out["methods"][m] = {
                "mean": M.mean_metrics(rows),
                "ci95": {
                    "precision@3": M.bootstrap_ci([r["precision@3"] for r in rows], seed=SEED),
                    "precision@10": M.bootstrap_ci([r["precision@10"] for r in rows], seed=SEED),
                },
                "per_category": per_cat,
                "weakest_5_by_precision@10": [
                    {"category": c, "precision@10": v["precision@10"], "n_queries": v["n_queries"]}
                    for c, v in weakest
                ],
            }
        set_out["categories_without_queries"] = [c for c in categories if c not in {c2 for _, c2 in pairs}]
        results["query_sets"][name] = set_out
    results["n_relevant_per_category"] = n_relevant
    # Exact top-10 for the clause texts is Part B's ground truth
    return results, per_query, rankings["clause"]["vector_exact"]


# ---------------------------------------------------------------------------
# Part B: ANN tradeoffs
# ---------------------------------------------------------------------------

def timed_pass(db, qvecs, warmup_vecs, sql_fn):
    for v in warmup_vecs:
        db.q(*sql_fn(v))
    latencies, results = [], []
    t_start = time.perf_counter()
    for v in qvecs:
        t0 = time.perf_counter()
        rows = db.q(*sql_fn(v))
        latencies.append((time.perf_counter() - t0) * 1000)
        results.append([r[0] for r in rows])
    wall = time.perf_counter() - t_start
    return latencies, results, wall


def server_pass(db, qvecs, sql_fn):
    exec_ms, plan_ms, hits, reads, plans = [], [], [], [], set()
    for v in qvecs:
        plan = db.explain(*sql_fn(v), analyze=True)
        exec_ms.append(plan["Execution Time"])
        plan_ms.append(plan["Planning Time"])
        hits.append(plan["Plan"].get("Shared Hit Blocks", 0))
        reads.append(plan["Plan"].get("Shared Read Blocks", 0))
        plans.add(json.dumps(plan_summary(plan), sort_keys=True))
    return {
        "execution_ms": M.percentiles(exec_ms),
        "planning_ms": M.percentiles(plan_ms),
        "shared_hit_blocks_mean": float(np.mean(hits)),
        "shared_read_blocks_mean": float(np.mean(reads)),
        "distinct_plans": [json.loads(p) for p in sorted(plans)],
    }


def measure_config(db, label, settings, qvecs, warmup_vecs, exact, expect):
    """Measure one configuration.

    Indexed configs run with enable_seqscan=off so the index is actually
    exercised; the plan the planner would choose without that (only the
    config's own settings applied) is recorded as planner_default_plan.
    """
    sql_fn = lambda v: (KNN_SQL, (vec(v), TOP_K))  # noqa: E731
    db.reset()
    db.set(**settings)
    planner_default = plan_summary(db.explain(*sql_fn(qvecs[0])))
    if expect != "none":
        settings = {**settings, "enable_seqscan": "off"}
    db.reset()
    db.set(**settings)
    lat, res, wall = timed_pass(db, qvecs, warmup_vecs, sql_fn)
    server = server_pass(db, qvecs, sql_fn)
    db.reset()
    plan_ok = all(
        (p["uses_hnsw"] if expect == "hnsw" else p["uses_ivfflat"] if expect == "ivfflat"
         else not (p["uses_hnsw"] or p["uses_ivfflat"]))
        for p in server["distinct_plans"]
    )
    if not plan_ok:
        raise RuntimeError(f"{label}: plan does not match expectation {expect}: {server['distinct_plans']}")
    recalls = [M.ann_recall(a, e) for a, e in zip(res, exact)]
    log(f"  {label}: recall@10={np.mean(recalls):.4f} client p50={np.percentile(lat, 50):.2f}ms")
    return {
        "label": label,
        "settings": settings,
        "expected_index": expect,
        "plan_check_passed": plan_ok,
        "planner_default_plan": planner_default,
        "planner_default_uses_expected_index": (
            planner_default["uses_hnsw"] if expect == "hnsw"
            else planner_default["uses_ivfflat"] if expect == "ivfflat"
            else not (planner_default["uses_hnsw"] or planner_default["uses_ivfflat"])
        ),
        "recall@10_vs_exact": float(np.mean(recalls)),
        "recall@10_vs_exact_min": float(np.min(recalls)),
        "client_ms": M.percentiles(lat),
        "qps": len(qvecs) / wall,
        "n_timed": len(qvecs),
        "n_warmup": len(warmup_vecs),
        "server": server,
    }


def build_index(db, name, ddl):
    db.q(f"DROP INDEX IF EXISTS {name}")
    t0 = time.perf_counter()
    db.q(ddl)
    build_s = time.perf_counter() - t0
    db.q("ANALYZE reference_clauses")
    size = db.scalar("SELECT pg_relation_size(%s::regclass)", (name,))
    log(f"  built {name} in {build_s:.2f}s, {size} bytes")
    return {"name": name, "ddl": ddl, "build_seconds": build_s, "size_bytes": int(size)}


def part_b(db, eval_vecs, exact, n_reference, args):
    rng = random.Random(SEED)
    warmup = [eval_vecs[i] for i in rng.sample(range(len(eval_vecs)), min(WARMUP_QUERIES, len(eval_vecs)))]
    qvecs = eval_vecs
    out = {"n_queries": len(qvecs), "configs": [], "indexes": []}
    start_defs = index_definitions(db)
    out["index_definitions_at_start"] = start_defs

    try:
        # Exact baseline (no vector index usable)
        out["configs"].append(measure_config(
            db, "exact", {"enable_indexscan": "off"}, qvecs, warmup, exact, "none"))

        # HNSW (rebuilt with the migration's parameters so build time is measured)
        out["indexes"].append({"family": "hnsw", **build_index(db, HNSW_INDEX, HNSW_DEFAULT_DDL)})
        for ef in EF_SEARCH_VALUES:
            out["configs"].append(measure_config(
                db, f"hnsw ef_search={ef}", {"hnsw__ef_search": ef}, qvecs, warmup, exact, "hnsw"))

        # IVFFlat variants (HNSW dropped so the planner can only use IVFFlat)
        db.q(f"DROP INDEX IF EXISTS {HNSW_INDEX}")
        for lists, probes_list in ((max(1, round(n_reference / 1000)), [1, 5, 10, 20]),
                                   (max(1, round(n_reference ** 0.5)), [1, 3, 5, 10])):
            name = f"bench_ivfflat_l{lists}"
            ddl = (f"CREATE INDEX {name} ON reference_clauses USING ivfflat "
                   f"(embedding vector_cosine_ops) WITH (lists = {lists})")
            out["indexes"].append({"family": "ivfflat", "lists": lists, **build_index(db, name, ddl)})
            for probes in probes_list:
                label = f"ivfflat lists={lists} probes={probes}"
                cfg = measure_config(db, label, {"ivfflat__probes": probes}, qvecs, warmup, exact, "ivfflat")
                cfg["lists"] = lists
                cfg["probes"] = probes
                cfg["scans_all_lists"] = probes >= lists
                out["configs"].append(cfg)
            db.q(f"DROP INDEX IF EXISTS {name}")
    finally:
        db.reset()
        for name in vector_index_names(db):
            if name != HNSW_INDEX:
                db.q(f"DROP INDEX IF EXISTS {name}")
        if HNSW_INDEX not in vector_index_names(db):
            db.q(HNSW_DEFAULT_DDL)
            db.q("ANALYZE reference_clauses")
        end_defs = index_definitions(db)
        out["index_definitions_at_end"] = end_defs
        out["indexes_restored"] = end_defs == start_defs
        log(f"Indexes restored to start state: {out['indexes_restored']}")
    if not out["indexes_restored"]:
        raise RuntimeError("Index set differs from the start state")
    return out


def iterative_scan_supported(db):
    """Iterative index scans were added in pgvector 0.8.0 (pgvector CHANGELOG).

    Checked by version first, because SET on an unknown dotted GUC can succeed
    silently as a placeholder; then confirmed with SET/SHOW.
    """
    version = db.scalar("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    parts = tuple(int(p) for p in version.split(".")[:3])
    if parts < (0, 8, 0):
        return False, f"pgvector {version} < 0.8.0 (iterative scans added in 0.8.0)"
    try:
        db.set(hnsw__iterative_scan="relaxed_order")
        value = db.scalar("SHOW hnsw.iterative_scan")
        db.reset()
        return value == "relaxed_order", None if value == "relaxed_order" else f"SHOW returned {value!r}"
    except Exception as e:
        db.reset()
        return False, f"{type(e).__name__}: {e}".strip()


def part_b_filtered(db, eval_vecs, n_relevant, args):
    rng = random.Random(SEED)
    sample = rng.sample(range(len(eval_vecs)), min(FILTER_SAMPLE, len(eval_vecs)))
    qvecs = [eval_vecs[i] for i in sample]
    by_freq = sorted(n_relevant.items(), key=lambda kv: (-kv[1], kv[0]))
    most = [c for c, _ in by_freq[:10]]
    least = [c for c, _ in by_freq[-10:]]
    supported, why_not = iterative_scan_supported(db)

    modes = {
        "planner_default": {"hnsw__ef_search": DEFAULT_EF_SEARCH},
        "hnsw_forced": {"hnsw__ef_search": DEFAULT_EF_SEARCH, "enable_seqscan": "off", "enable_bitmapscan": "off"},
    }
    if supported:
        for order in ("relaxed_order", "strict_order"):
            modes[f"hnsw_forced_iterative_{order}"] = {
                **modes["hnsw_forced"], "hnsw__iterative_scan": order}

    out = {"n_queries_per_category": len(qvecs), "iterative_scan_supported": supported,
           "iterative_scan_unsupported_reason": why_not, "categories": {}}
    for group, cats in (("most_frequent", most), ("least_frequent", least)):
        for cat in cats:
            sql_fn = lambda v, c=cat: (FILTERED_KNN_SQL, (c, vec(v), TOP_K))  # noqa: E731
            db.reset()
            db.set(enable_indexscan="off")
            exact = [[r[0] for r in db.q(*sql_fn(v))] for v in qvecs]
            exact_plan = plan_summary(db.explain(*sql_fn(qvecs[0])))
            db.reset()
            entry = {"group": group, "reference_rows": n_relevant[cat], "exact_plan": exact_plan, "modes": {}}
            expected = min(TOP_K, n_relevant[cat])
            for mode, settings in modes.items():
                db.reset()
                db.set(**settings)
                lat, res = [], []
                for v in qvecs:
                    t0 = time.perf_counter()
                    rows = db.q(*sql_fn(v))
                    lat.append((time.perf_counter() - t0) * 1000)
                    res.append([r[0] for r in rows])
                plan = plan_summary(db.explain(*sql_fn(qvecs[0])))
                db.reset()
                counts = [len(r) for r in res]
                entry["modes"][mode] = {
                    "recall@10_vs_exact_filtered": float(np.mean([M.ann_recall(a, e) for a, e in zip(res, exact)])),
                    "mean_result_count": float(np.mean(counts)),
                    "share_below_expected_count": float(np.mean([c < expected for c in counts])),
                    "expected_count": expected,
                    "client_ms": M.percentiles(lat),
                    "plan": plan,
                }
            out["categories"][cat] = entry
            log(f"  filtered {cat}: " + ", ".join(
                f"{m}={entry['modes'][m]['recall@10_vs_exact_filtered']:.3f}" for m in entry["modes"]))
    return out


# ---------------------------------------------------------------------------
# Part C: end-to-end stage timing
# ---------------------------------------------------------------------------

def part_c(args, runs, warmup):
    from sqlalchemy import insert
    from app.db.models import Clause, Document, DocumentText
    from app.db.session import SessionLocal
    from app.services.clause_segment import segment_clauses
    from app.services.onnx_infer import get_onnx_service
    from app.services.pdf_extract import extract_text
    from app.services.rag import gather_evidence, order_priority_clauses
    from app.services.retrieval import get_embedder

    pdf = ROOT / "backend/app/static/sample_contract.pdf"
    embedder = get_embedder()
    classifier = get_onnx_service()
    stages = defaultdict(list)
    info = {}
    for run in range(warmup + runs):
        t = {}
        t0 = time.perf_counter(); text, ok = extract_text(str(pdf)); t["extract"] = time.perf_counter() - t0
        t0 = time.perf_counter(); clauses = segment_clauses(text); t["segment"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        classified = [{**c, **classifier.classify_clause(c["text"])} for c in clauses]
        t["classify"] = time.perf_counter() - t0
        t0 = time.perf_counter(); embs = embedder.encode([c["text"] for c in clauses]); t["embed"] = time.perf_counter() - t0

        session = SessionLocal()
        try:
            doc = Document(filename="bench.pdf", original_filename="bench.pdf")
            session.add(doc)
            session.flush()
            session.add(DocumentText(document_id=doc.id, text=text))
            session.flush()
            t0 = time.perf_counter()
            session.execute(insert(Clause), [
                {"document_id": doc.id, "idx": c["idx"], "text": c["text"], "start_char": c["start_char"],
                 "end_char": c["end_char"], "clause_type": c["clause_type"], "risk_score": c["risk_score"],
                 "confidence": c["confidence"], "embedding": embs[i]}
                for i, c in enumerate(classified)
            ])
            session.flush()
            t["insert"] = time.perf_counter() - t0
            priority = order_priority_clauses(classified, min_risk=60, limit=10)
            t0 = time.perf_counter()
            evidence, retriever_name, precedents_enabled = gather_evidence(
                priority, classified, session=session, document_id=doc.id)
            t["retrieve"] = time.perf_counter() - t0
        finally:
            session.rollback()
            session.close()
        if run >= warmup:
            for k, v in t.items():
                stages[k].append(v * 1000)
        info = {
            "extract_ok": ok, "num_clauses": len(clauses), "num_priority": len(priority),
            "retriever": retriever_name, "precedents_enabled": precedents_enabled,
            "num_related": sum(len(e.related) for e in evidence),
            "num_precedents": sum(len(e.precedents) for e in evidence),
            "classifier": classifier.get_model_status(),
        }
    return {
        "runs": runs, "warmup_runs": warmup, "info": info,
        "stages_ms": {k: {"median": float(np.median(v)), "p95": float(np.percentile(v, 95))}
                      for k, v in stages.items()},
        "total_median_ms": float(np.median([sum(x) for x in zip(*stages.values())])),
        "note": "insert is rolled back; classify uses the app's default classifier chain",
    }


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["local", "azure"])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "bench/results")
    parser.add_argument("--parts", default="A,B,F,C", help="Subset of A,B,F (filtered),C")
    parser.add_argument("--dry-run", action="store_true",
                        help="Small query subsets to exercise the code; results are not for reporting")
    args = parser.parse_args()
    parts = set(args.parts.upper().split(","))
    if "DATABASE_URL" not in os.environ:
        sys.exit("ERROR: DATABASE_URL must be set")

    from app.services.retrieval import get_embedder
    corpus_path = ROOT / "bench/data/cuad_corpus.jsonl"
    meta_path = ROOT / "bench/corpus/cuad_corpus_meta.json"
    split_path = ROOT / "bench/corpus/cuad_split.json"
    split = json.loads(split_path.read_text())
    eval_rows = [r for r in map(json.loads, corpus_path.read_text().splitlines()) if r["split"] == "eval"]
    questions = [{"category": c, "text": q} for c, q in split["category_questions"].items()]
    categories = split["final_categories"]

    db = DB(os.environ["DATABASE_URL"])
    ref = [{"id": i, "text": t, "categories": c} for i, t, c in
           db.q("SELECT id, text, categories FROM reference_clauses ORDER BY id")]
    if not ref:
        sys.exit("ERROR: reference_clauses is empty; load the corpus first")
    expected_ref = split["counts"]["reference"]["clauses"]
    if len(ref) != expected_ref:
        sys.exit(f"ERROR: reference_clauses has {len(ref)} rows, split says {expected_ref}")

    if args.dry_run:
        rng = random.Random(SEED)
        eval_rows = rng.sample(eval_rows, 150)
        global EF_SEARCH_VALUES, FILTER_SAMPLE, WARMUP_QUERIES
        EF_SEARCH_VALUES, FILTER_SAMPLE, WARMUP_QUERIES = [10, 40], 20, 10

    embedder = get_embedder()
    log(f"Embedding {len(eval_rows)} eval texts and {len(questions)} questions")
    eval_vecs = embedder.encode([r["text"] for r in eval_rows])
    question_vecs = embedder.encode([q["text"] for q in questions])

    result = {"environment": environment(db, args, meta_path, split_path, len(ref), len(eval_rows)),
              "preregistration": "bench/PREREGISTRATION.md",
              "corpus_meta": "bench/corpus/cuad_corpus_meta.json"}
    per_query = None
    exact = None
    n_relevant = {c: sum(1 for r in ref if c in r["categories"]) for c in categories}
    if "A" in parts or "B" in parts:
        log("Part A: retrieval quality")
        result["part_a"], per_query, exact = part_a(
            db, ref, eval_rows, eval_vecs, questions, question_vecs, categories, args)
    if "B" in parts:
        log("Part B: ANN index tradeoffs")
        result["part_b"] = part_b(db, eval_vecs, exact, len(ref), args)
    if "F" in parts:
        log("Part B (filtered): category-filtered vector search")
        result["part_b_filtered"] = part_b_filtered(db, eval_vecs, n_relevant, args)
    if "C" in parts:
        log("Part C: end-to-end stage timing")
        result["part_c"] = part_c(args, runs=3 if args.dry_run else 20, warmup=1 if args.dry_run else 3)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"{stamp}_{args.env}" + ("_dryrun" if args.dry_run else "")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{suffix}.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    if per_query is not None:
        with gzip.open(args.out_dir / f"{suffix}_perquery.json.gz", "wt") as f:
            json.dump(per_query, f)
    log(f"Wrote {out_path}")

    import report
    report.render(out_path)


if __name__ == "__main__":
    main()
