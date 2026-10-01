"""Retrieval services: TF-IDF, pgvector, and hybrid (Reciprocal Rank Fusion).

All retrievers implement the same interface:

    retrieve(query, top_k, filters) -> List[RetrievalResult(clause_id, text, score)]

`filters` is an optional dict mapping a field name to a value (equality) or a
list/tuple of values (membership). The special key ``exclude_ids`` removes the
given clause ids from the results (e.g. to drop the query clause itself).
For list-valued (array) fields such as reference_clauses.categories, a filter
matches when the stored set and the requested values overlap.

Fallback philosophy (matches the classifier): if sentence-transformers or the
pgvector extension is unavailable, `get_retriever` falls back to TF-IDF and
logs why.
"""
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Hashable, List, NamedTuple, Optional, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import bindparam, text as sql_text

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

# Lazy import to avoid crashing if sentence-transformers not installed
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

EMBEDDING_DIM = 384
EXCLUDE_IDS = "exclude_ids"


class RetrievalResult(NamedTuple):
    clause_id: Hashable
    text: str
    score: float


class Retriever(ABC):
    """Common retrieval interface."""

    name: str = "base"

    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """Return up to top_k results, best first."""


def _matches(metadata: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
    """Check a document's metadata against a filter dict (exclude_ids handled by caller)."""
    if not filters:
        return True
    for key, value in filters.items():
        if key == EXCLUDE_IDS:
            continue
        actual = metadata.get(key)
        if isinstance(actual, (list, tuple, set)):
            wanted = set(value) if isinstance(value, (list, tuple, set)) else {value}
            if not wanted & set(actual):
                return False
        elif isinstance(value, (list, tuple, set)):
            if actual not in value:
                return False
        elif actual != value:
            return False
    return True


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------

class Embedder:
    """Sentence-transformers encoder producing L2-normalized float32 embeddings."""

    def __init__(self, model_name: str, revision: Optional[str] = None):
        self.model_name = model_name
        self.revision = revision
        self.model = SentenceTransformer(model_name, revision=revision, device="cpu")
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Sequence[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        embeddings = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)


_embedder: Optional[Embedder] = None
_embedder_failed = False
_embedder_lock = threading.Lock()


def get_embedder() -> Optional[Embedder]:
    """Lazily load the global embedder. Returns None if it cannot be loaded."""
    global _embedder, _embedder_failed
    if _embedder is not None or _embedder_failed:
        return _embedder
    with _embedder_lock:
        if _embedder is not None or _embedder_failed:
            return _embedder
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, embeddings disabled")
            _embedder_failed = True
            return None
        try:
            logger.info(
                "Loading embedding model",
                model=settings.embedding_model,
                revision=settings.embedding_model_revision,
            )
            embedder = Embedder(settings.embedding_model, settings.embedding_model_revision or None)
            if embedder.dim != EMBEDDING_DIM:
                raise ValueError(f"Expected {EMBEDDING_DIM}-dim embeddings, got {embedder.dim}")
            _embedder = embedder
        except Exception as e:
            logger.error("Failed to load embedding model", error=str(e))
            _embedder_failed = True
    return _embedder


def vector_literal(embedding: Sequence[float]) -> str:
    """Format an embedding as a pgvector text literal, e.g. '[0.1,0.2]'."""
    return "[" + ",".join(f"{float(x):.8g}" for x in embedding) + "]"


# ---------------------------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------------------------

class TfidfRetriever(Retriever):
    """In-memory TF-IDF retrieval over a fixed set of documents."""

    name = "tfidf"

    def __init__(
        self,
        ids: Sequence[Hashable],
        texts: Sequence[str],
        metadata: Optional[Sequence[Dict[str, Any]]] = None,
    ):
        if len(ids) != len(texts):
            raise ValueError("ids and texts must have the same length")
        self.ids = list(ids)
        self.texts = list(texts)
        self.metadata = list(metadata) if metadata is not None else [{} for _ in self.ids]
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
        )
        self.document_vectors = None
        if not self.texts:
            logger.warning("No documents to index")
            return
        try:
            self.document_vectors = self.vectorizer.fit_transform(self.texts)
            logger.info("Indexed documents for retrieval", num_docs=len(self.texts))
        except Exception as e:
            logger.error("Failed to index documents", error=str(e))
            self.document_vectors = None

    def retrieve(
        self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        if self.document_vectors is None or top_k <= 0:
            return []
        try:
            similarities = cosine_similarity(
                self.vectorizer.transform([query]), self.document_vectors
            )[0]
        except Exception as e:
            logger.error("Retrieval failed", error=str(e))
            return []

        excluded = set((filters or {}).get(EXCLUDE_IDS, ()))
        # Stable sort so ties keep corpus order (deterministic results)
        order = np.argsort(-similarities, kind="stable")
        results = []
        for idx in order:
            score = float(similarities[idx])
            if score <= 0:
                break
            if self.ids[idx] in excluded or not _matches(self.metadata[idx], filters):
                continue
            results.append(RetrievalResult(self.ids[idx], self.texts[idx], score))
            if len(results) >= top_k:
                break
        return results


# ---------------------------------------------------------------------------
# pgvector
# ---------------------------------------------------------------------------

# Whitelisted tables and filterable columns (identifiers are never taken from user input)
PGVECTOR_TABLES = {
    "clauses": {"id_column": "idx", "filter_columns": {"document_id", "clause_type"}, "array_columns": set()},
    "reference_clauses": {
        "id_column": "id",
        "filter_columns": {"categories", "source_contract"},
        "array_columns": {"categories"},
    },
}


class PgVectorRetriever(Retriever):
    """Cosine-distance kNN over a pgvector column.

    Score is cosine similarity (1 - cosine distance). Whether an index is used
    depends on the planner and on session settings; see bench/ for measurements.
    """

    name = "vector"

    def __init__(
        self,
        session,
        table: str,
        embedder: Optional[Embedder] = None,
        scope: Optional[Dict[str, Any]] = None,
    ):
        """`scope` is a fixed filter applied to every query (e.g. {"document_id": 7})."""
        if table not in PGVECTOR_TABLES:
            raise ValueError(f"Unsupported table: {table}")
        self.session = session
        self.table = table
        self.id_column = PGVECTOR_TABLES[table]["id_column"]
        self.filter_columns = PGVECTOR_TABLES[table]["filter_columns"]
        self.array_columns = PGVECTOR_TABLES[table]["array_columns"]
        self.scope = dict(scope or {})
        self.embedder = embedder or get_embedder()
        if self.embedder is None:
            raise RuntimeError("Embedder unavailable")

    def _build_sql(self, filters: Optional[Dict[str, Any]], params: Dict[str, Any]) -> str:
        where = ["embedding IS NOT NULL"]
        for key, value in {**self.scope, **(filters or {})}.items():
            if key == EXCLUDE_IDS:
                if value:
                    where.append(f"{self.id_column} NOT IN :exclude_ids")
                    params["exclude_ids"] = tuple(value)
                continue
            if key not in self.filter_columns:
                raise ValueError(f"Unsupported filter column for {self.table}: {key}")
            if key in self.array_columns:
                # Overlap: row matches if any requested value is in the stored array
                values = list(value) if isinstance(value, (list, tuple, set)) else [value]
                where.append(f"{key} && CAST(:f_{key} AS varchar[])")
                params[f"f_{key}"] = values
            elif isinstance(value, (list, tuple, set)):
                where.append(f"{key} IN :f_{key}")
                params[f"f_{key}"] = tuple(value)
            else:
                where.append(f"{key} = :f_{key}")
                params[f"f_{key}"] = value
        return (
            f"SELECT {self.id_column} AS clause_id, text, "
            f"1 - (embedding <=> CAST(:q AS vector)) AS score "
            f"FROM {self.table} WHERE {' AND '.join(where)} "
            f"ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        )

    def retrieve(
        self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        if top_k <= 0:
            return []
        query_vec = self.embedder.encode([query])[0]
        return self.retrieve_by_vector(query_vec, top_k, filters)

    def retrieve_by_vector(
        self, query_vec: Sequence[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        params: Dict[str, Any] = {"q": vector_literal(query_vec), "k": top_k}
        stmt = sql_text(self._build_sql(filters, params))
        for name, value in params.items():
            if isinstance(value, tuple):
                stmt = stmt.bindparams(bindparam(name, expanding=True))
        rows = self.session.execute(stmt, params).fetchall()
        return [RetrievalResult(r.clause_id, r.text, float(r.score)) for r in rows]


# ---------------------------------------------------------------------------
# Hybrid (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def rrf_fuse(rankings: Sequence[Sequence[Hashable]], k: int = 60) -> List[tuple]:
    """Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank(d)), rank from 1.

    Returns (id, score) sorted by score descending; ties broken by first appearance.
    """
    scores: Dict[Hashable, float] = {}
    first_seen: Dict[Hashable, int] = {}
    position = 0
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in first_seen:
                first_seen[doc_id] = position
                position += 1
    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))


class HybridRetriever(Retriever):
    """Fuses several retrievers' rankings with RRF."""

    name = "hybrid"

    def __init__(self, retrievers: Sequence[Retriever], k: Optional[int] = None, candidate_k: int = 50):
        if not retrievers:
            raise ValueError("HybridRetriever needs at least one retriever")
        self.retrievers = list(retrievers)
        self.k = k if k is not None else settings.rrf_k
        self.candidate_k = candidate_k

    def retrieve(
        self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        if top_k <= 0:
            return []
        depth = max(self.candidate_k, top_k)
        rankings = []
        texts: Dict[Hashable, str] = {}
        for retriever in self.retrievers:
            results = retriever.retrieve(query, top_k=depth, filters=filters)
            rankings.append([r.clause_id for r in results])
            for r in results:
                texts.setdefault(r.clause_id, r.text)
        fused = rrf_fuse(rankings, k=self.k)[:top_k]
        return [RetrievalResult(doc_id, texts[doc_id], score) for doc_id, score in fused]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

RETRIEVER_MODES = ("tfidf", "vector", "hybrid")


def vector_extension_available(session) -> bool:
    """True if the pgvector extension is installed in the connected database."""
    try:
        row = session.execute(
            sql_text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).first()
        return row is not None
    except Exception as e:
        logger.warning("Could not check for pgvector extension", error=str(e))
        try:
            session.rollback()
        except Exception:
            pass
        return False


def _tfidf_from_clauses(clauses: Sequence[Dict[str, Any]], id_key: str = "idx") -> TfidfRetriever:
    return TfidfRetriever(
        ids=[c.get(id_key) for c in clauses],
        texts=[c.get("text", "") for c in clauses],
        metadata=[{k: v for k, v in c.items() if k != "text"} for c in clauses],
    )


def get_retriever(
    clauses: Sequence[Dict[str, Any]],
    session=None,
    table: str = "clauses",
    scope: Optional[Dict[str, Any]] = None,
    id_key: str = "idx",
    mode: Optional[str] = None,
) -> Retriever:
    """Build a retriever according to RETRIEVER (tfidf|vector|hybrid).

    `clauses` (dicts with text and metadata, keyed by `id_key`) back the TF-IDF
    side; `session`, `table` and `scope` back the vector side, so both sides
    must cover the same set of rows. Falls back to TF-IDF, with a log line, if
    embeddings or the vector extension are unavailable.
    """
    mode = (mode or settings.retriever).lower()
    if mode not in RETRIEVER_MODES:
        logger.warning("Unknown RETRIEVER value, using hybrid", retriever=mode)
        mode = "hybrid"

    tfidf = _tfidf_from_clauses(clauses, id_key)
    if mode == "tfidf":
        return tfidf

    reason = None
    if session is None:
        reason = "no database session"
    elif get_embedder() is None:
        reason = "embedding model unavailable"
    elif not vector_extension_available(session):
        reason = "pgvector extension not installed"
    if reason:
        logger.warning("Falling back to TF-IDF retrieval", requested=mode, reason=reason)
        return tfidf

    vector = PgVectorRetriever(session, table, scope=scope)
    if mode == "vector":
        return vector
    return HybridRetriever([tfidf, vector])
