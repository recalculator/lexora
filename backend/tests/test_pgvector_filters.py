"""Category-filtered vector search (runs only with TEST_DATABASE_URL).

Regression tests for the bug found by the benchmark: with HNSW and
hnsw.iterative_scan=off, a selective category filter returned far fewer rows
than requested. Filtered lookups now run as exact search over the GIN index.
"""
import json

import numpy as np
import pytest
from sqlalchemy import insert, text

from app.db.models import ReferenceClause
from app.services.retrieval import PgVectorRetriever

DIM = 384


class FixedEmbedder:
    dim = DIM

    def encode(self, texts, batch_size=64):
        raise AssertionError("tests pass vectors directly")


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def plan_nodes(plan):
    out = []

    def walk(node):
        out.append((node["Node Type"], node.get("Index Name")))
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return out


@pytest.fixture
def seeded(pg_session):
    """Rows near the query are 'Background'; a 'Common' category (~10% of the
    inserted rows, selective enough that the planner prefers HNSW plus a
    filter) and a 3-row 'Rare' category sit far from the query. With HNSW and
    iterative scans off, the ef_search candidates near the query are all
    Background, so a filtered lookup for Common came back short."""
    rng = np.random.default_rng(0)
    query = unit(rng.normal(size=DIM))
    near = [unit(query + 0.3 * rng.normal(size=DIM)) for _ in range(2700)]
    common = [unit(-query + 0.3 * rng.normal(size=DIM)) for _ in range(300)]
    rare = [unit(-query + 0.3 * rng.normal(size=DIM)) for _ in range(3)]
    rows = [{"source_contract": "test", "categories": ["Background"], "text": f"bg {i}", "embedding": v}
            for i, v in enumerate(near)]
    rows += [{"source_contract": "test", "categories": ["Common"], "text": f"common {i}", "embedding": v}
             for i, v in enumerate(common)]
    rows += [{"source_contract": "test", "categories": ["Rare", "Other"], "text": f"rare {i}", "embedding": v}
             for i, v in enumerate(rare)]
    pg_session.execute(insert(ReferenceClause), rows)
    pg_session.execute(text("ANALYZE reference_clauses"))
    return pg_session, query


def test_filtered_lookup_returns_k_when_enough_rows_match(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    for category, prefix in (("Common", "common "), ("Rare", "rare ")):
        results = retriever.retrieve_by_vector(query, 3, {"categories": [category]})
        assert len(results) == 3, category
        assert all(r.text.startswith(prefix) for r in results)
        # Exact ordering by score
        assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_filtered_lookup_matches_exact_top_k(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    results = retriever.retrieve_by_vector(query, 3, {"categories": ["Common"]})
    # Ground truth computed in numpy, independent of any index or planner choice
    rows = session.execute(
        text("SELECT text, embedding::text FROM reference_clauses WHERE categories @> ARRAY['Common']::varchar[]")
    ).fetchall()
    sims = [(float(np.dot(np.asarray(json.loads(e), dtype=np.float32), query)), t) for t, e in rows]
    exact = [t for _, t in sorted(sims, reverse=True)[:3]]
    assert [r.text for r in results] == exact


def test_filtered_lookup_correct_when_planner_prefers_hnsw(seeded):
    """Deterministic regression test: steer the planner to HNSW (as it chose
    for frequent CUAD categories in the benchmark) before the lookup. Without
    the fix this returns 0 of 3; with it, exact search over GIN returns 3."""
    session, query = seeded
    session.execute(text("SET LOCAL enable_bitmapscan = off"))
    session.execute(text("SET LOCAL enable_seqscan = off"))
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    results = retriever.retrieve_by_vector(query, 3, {"categories": ["Common"]})
    assert len(results) == 3
    assert all(r.text.startswith("common ") for r in results)
    # The session's own settings are restored afterwards
    assert session.execute(text("SHOW enable_bitmapscan")).scalar() == "off"
    assert session.execute(text("SHOW enable_seqscan")).scalar() == "off"


def test_filtered_lookup_returns_all_when_fewer_than_k_match(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    assert len(retriever.retrieve_by_vector(query, 10, {"categories": ["Rare"]})) == 3


def test_filtered_plan_uses_gin_not_hnsw_or_seq_scan(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    nodes = plan_nodes(retriever.explain_by_vector(query, 3, {"categories": ["Common"]}))
    node_types = [n for n, _ in nodes]
    indexes = {i for _, i in nodes if i}
    assert "ix_reference_clauses_categories" in indexes
    assert "Bitmap Index Scan" in node_types
    assert "Seq Scan" not in node_types
    assert not any("hnsw" in i for i in indexes)


def test_settings_restored_after_filtered_lookup(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    names = ("enable_indexscan", "enable_seqscan", "enable_bitmapscan")
    before = [session.execute(text(f"SHOW {s}")).scalar() for s in names]
    retriever.retrieve_by_vector(query, 3, {"categories": ["Common"]})
    # Same transaction, before commit/rollback
    after = [session.execute(text(f"SHOW {s}")).scalar() for s in names]
    assert before == after == ["on", "on", "on"]


def test_unfiltered_lookup_can_still_use_hnsw(seeded):
    session, query = seeded
    retriever = PgVectorRetriever(session, "reference_clauses", embedder=FixedEmbedder())
    indexes = {i for _, i in plan_nodes(retriever.explain_by_vector(query, 3)) if i}
    assert "ix_reference_clauses_embedding_hnsw" in indexes
