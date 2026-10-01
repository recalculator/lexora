"""Tests for retrieval services."""
import math
from unittest.mock import patch

import pytest

from app.services import retrieval
from app.services.retrieval import (
    HybridRetriever,
    PgVectorRetriever,
    RetrievalResult,
    Retriever,
    TfidfRetriever,
    get_retriever,
    rrf_fuse,
)

CLAUSES = [
    {"idx": 0, "text": "This agreement may be terminated by either party with thirty days written notice.", "clause_type": "Termination"},
    {"idx": 1, "text": "Each party shall indemnify and hold harmless the other party from third-party claims.", "clause_type": "Indemnification"},
    {"idx": 2, "text": "This agreement shall be governed by the laws of the State of California.", "clause_type": "Governing Law"},
    {"idx": 3, "text": "Upon termination, the receiving party shall return all confidential information.", "clause_type": "Confidentiality"},
]


def make_tfidf():
    return TfidfRetriever(
        ids=[c["idx"] for c in CLAUSES],
        texts=[c["text"] for c in CLAUSES],
        metadata=[{"clause_type": c["clause_type"]} for c in CLAUSES],
    )


class StaticRetriever(Retriever):
    """Returns a fixed ranking; used to test fusion without a database."""

    name = "static"

    def __init__(self, ranking):
        self.ranking = ranking

    def retrieve(self, query, top_k=5, filters=None):
        excluded = set((filters or {}).get("exclude_ids", ()))
        hits = [i for i in self.ranking if i not in excluded]
        return [RetrievalResult(i, f"text {i}", 1.0 / (n + 1)) for n, i in enumerate(hits[:top_k])]


# --- Interface contract (applies to every in-process retriever) -------------

def contract_retrievers():
    return [make_tfidf(), HybridRetriever([make_tfidf(), StaticRetriever([2, 0, 1, 3])], k=60)]


@pytest.mark.parametrize("retriever", contract_retrievers(), ids=lambda r: r.name)
def test_contract_result_shape_and_order(retriever):
    results = retriever.retrieve("termination notice", top_k=3)
    assert 0 < len(results) <= 3
    for r in results:
        assert isinstance(r, RetrievalResult)
        assert isinstance(r.text, str) and r.text
        assert isinstance(r.score, float)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert len({r.clause_id for r in results}) == len(results)


@pytest.mark.parametrize("retriever", contract_retrievers(), ids=lambda r: r.name)
def test_contract_top_k_zero_and_exclude(retriever):
    assert retriever.retrieve("termination", top_k=0) == []
    results = retriever.retrieve("termination", top_k=10, filters={"exclude_ids": [0]})
    assert 0 not in [r.clause_id for r in results]


# --- TF-IDF ------------------------------------------------------------------

def test_tfidf_ranks_relevant_clause_first():
    results = make_tfidf().retrieve("governed by the laws of California", top_k=2)
    assert results[0].clause_id == 2


def test_tfidf_metadata_filter():
    results = make_tfidf().retrieve("termination", top_k=5, filters={"clause_type": "Confidentiality"})
    assert [r.clause_id for r in results] == [3]


def test_tfidf_empty_corpus():
    assert TfidfRetriever(ids=[], texts=[]).retrieve("anything") == []


# --- RRF -----------------------------------------------------------------------

def test_rrf_hand_computed_k1():
    # k=1: a=1/2, b=1/3+1/2, c=1/4+1/3, d=1/4
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "d"]], k=1)
    assert [doc for doc, _ in fused] == ["b", "c", "a", "d"]
    expected = {"a": 1 / 2, "b": 1 / 3 + 1 / 2, "c": 1 / 4 + 1 / 3, "d": 1 / 4}
    for doc, score in fused:
        assert math.isclose(score, expected[doc])


def test_rrf_hand_computed_k60():
    fused = dict(rrf_fuse([["a", "b"], ["b", "a"]], k=60))
    # Symmetric rankings: both docs get 1/61 + 1/62
    assert math.isclose(fused["a"], 1 / 61 + 1 / 62)
    assert math.isclose(fused["b"], 1 / 61 + 1 / 62)


def test_rrf_tie_break_is_first_appearance():
    fused = rrf_fuse([["x"], ["y"]], k=60)
    assert [doc for doc, _ in fused] == ["x", "y"]


def test_hybrid_uses_rrf_scores():
    hybrid = HybridRetriever([StaticRetriever([1, 2, 3]), StaticRetriever([3, 2, 1])], k=60)
    results = hybrid.retrieve("q", top_k=3)
    # 1 and 3 each get 1/61 + 1/63 (~0.032266), which beats 2's 2/62 (~0.032258)
    # because 1/(k+r) is convex; the 1-vs-3 tie is broken by first appearance.
    assert [r.clause_id for r in results] == [1, 3, 2]
    assert math.isclose(results[0].score, 1 / 61 + 1 / 63)
    assert math.isclose(results[2].score, 2 / 62)


# --- pgvector SQL building (no database needed) ------------------------------

class FakeEmbedder:
    dim = 384

    def encode(self, texts, batch_size=64):
        import numpy as np
        return np.ones((len(texts), 384), dtype=np.float32) / math.sqrt(384)


def test_pgvector_rejects_unknown_table_and_filter():
    with pytest.raises(ValueError):
        PgVectorRetriever(session=None, table="documents", embedder=FakeEmbedder())
    r = PgVectorRetriever(session=None, table="reference_clauses", embedder=FakeEmbedder())
    with pytest.raises(ValueError):
        r._build_sql({"text; DROP TABLE x": 1}, {})


def test_pgvector_array_column_uses_overlap():
    r = PgVectorRetriever(session=None, table="reference_clauses", embedder=FakeEmbedder())
    params = {}
    sql = r._build_sql({"categories": ["Insurance", "Governing Law"]}, params)
    assert "categories && CAST(:f_categories AS varchar[])" in sql
    assert params == {"f_categories": ["Insurance", "Governing Law"]}
    params = {}
    r._build_sql({"categories": "Insurance"}, params)
    assert params == {"f_categories": ["Insurance"]}


def test_tfidf_list_metadata_matches_on_overlap():
    r = TfidfRetriever(
        ids=[0, 1],
        texts=["licensee may not transfer the license", "licensee may not assign the license"],
        metadata=[{"categories": ["License Grant", "Non-Transferable License"]}, {"categories": ["Anti-Assignment"]}],
    )
    # Terms shared by both docs are dropped by max_df, so query the distinct ones
    assert {h.clause_id for h in r.retrieve("transfer assign", top_k=5)} == {0, 1}
    hits = r.retrieve("transfer assign", top_k=5, filters={"categories": ["Non-Transferable License"]})
    assert [h.clause_id for h in hits] == [0]
    hits = r.retrieve("transfer assign", top_k=5, filters={"categories": "Anti-Assignment"})
    assert [h.clause_id for h in hits] == [1]


def test_pgvector_sql_applies_scope_and_filters():
    r = PgVectorRetriever(session=None, table="clauses", embedder=FakeEmbedder(), scope={"document_id": 7})
    params = {}
    sql = r._build_sql({"clause_type": "Termination", "exclude_ids": [1, 2]}, params)
    assert "document_id = :f_document_id" in sql
    assert "clause_type = :f_clause_type" in sql
    assert "idx NOT IN :exclude_ids" in sql
    assert "ORDER BY embedding <=> CAST(:q AS vector)" in sql
    assert params == {"f_document_id": 7, "f_clause_type": "Termination", "exclude_ids": (1, 2)}


# --- Fallback to TF-IDF ---------------------------------------------------------

def test_tfidf_mode_returns_tfidf():
    assert isinstance(get_retriever(CLAUSES, mode="tfidf"), TfidfRetriever)


def test_fallback_without_session():
    assert isinstance(get_retriever(CLAUSES, session=None, mode="hybrid"), TfidfRetriever)


def test_fallback_when_embedder_unavailable():
    with patch.object(retrieval, "get_embedder", return_value=None):
        assert isinstance(get_retriever(CLAUSES, session=object(), mode="vector"), TfidfRetriever)


def test_fallback_when_extension_missing():
    with patch.object(retrieval, "get_embedder", return_value=FakeEmbedder()), \
            patch.object(retrieval, "vector_extension_available", return_value=False):
        assert isinstance(get_retriever(CLAUSES, session=object(), mode="hybrid"), TfidfRetriever)


def test_hybrid_selected_when_available():
    with patch.object(retrieval, "get_embedder", return_value=FakeEmbedder()), \
            patch.object(retrieval, "vector_extension_available", return_value=True):
        r = get_retriever(CLAUSES, session=object(), mode="hybrid", scope={"document_id": 1})
    assert isinstance(r, HybridRetriever)
    assert isinstance(r.retrievers[1], PgVectorRetriever)
    assert r.retrievers[1].scope == {"document_id": 1}


def test_unknown_mode_defaults_to_hybrid_then_falls_back():
    assert isinstance(get_retriever(CLAUSES, session=None, mode="bogus"), TfidfRetriever)


# --- Embedder (real model; skipped if it can't be loaded) ----------------------

def test_embedder_normalized_384():
    embedder = retrieval.get_embedder()
    if embedder is None:
        pytest.skip("Embedding model unavailable")
    import numpy as np
    vecs = embedder.encode(["termination for convenience", "governing law"])
    assert vecs.shape == (2, 384)
    assert vecs.dtype == np.float32
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-5)
    assert retrieval.get_embedder() is embedder  # singleton
