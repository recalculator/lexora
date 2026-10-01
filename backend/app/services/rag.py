"""Retrieval-augmented context building and citation grounding for LLM prompts.

Evidence in prompts is labelled with stable IDs:
  C<idx>  a clause of the contract being analyzed (Clause.idx)
  P<id>   a precedent clause from reference_clauses (ReferenceClause.id)

After generation, `check_grounding` verifies that every cited ID is either an
analyzed clause of this contract or a precedent that was actually shown to the
model, and logs the rate of ungrounded citations.
"""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.core.logging import get_logger
from app.services.retrieval import (
    PgVectorRetriever,
    Retriever,
    get_embedder,
    get_retriever,
    vector_extension_available,
)

logger = get_logger()

CATEGORY_MAP_PATH = Path(__file__).with_name("category_map.json")
CITATION_PATTERN = re.compile(r"\b([CP])(\d+)\b")

RELATED_K = 3
PRECEDENT_K = 3
MIN_PRIORITY = 3
EVIDENCE_CHARS = 400


@lru_cache(maxsize=1)
def load_category_map() -> Dict[str, Optional[Dict[str, Any]]]:
    with open(CATEGORY_MAP_PATH, "r") as f:
        return json.load(f)["mappings"]


def precedent_categories(clause_type: Optional[str]) -> Optional[List[str]]:
    """CUAD categories for a Lexora clause type, or None for unfiltered search."""
    entry = load_category_map().get(clause_type) if clause_type else None
    if not entry:
        logger.info("No CUAD category mapping, using unfiltered precedent search", clause_type=clause_type)
        return None
    return list(entry["categories"])


def order_priority_clauses(
    clauses: Sequence[Dict[str, Any]],
    min_risk: float,
    limit: int,
    require_type: bool = False,
    min_count: int = MIN_PRIORITY,
) -> List[Dict[str, Any]]:
    """Clauses above `min_risk`, highest risk first (ties by document order).

    If fewer than `min_count` pass the threshold, fill up to `min_count` with
    the highest-risk remaining clauses (still subject to `require_type`).
    """
    candidates = [c for c in clauses if not require_type or c.get("clause_type") is not None]
    candidates.sort(key=lambda c: (-(c.get("risk_score") or 0), c.get("idx", 0)))
    passing = sum(1 for c in candidates if (c.get("risk_score") or 0) > min_risk)
    selected = candidates[:max(passing, min(min_count, len(candidates)))][:limit]
    if len(selected) > passing:
        logger.info(
            "Priority clause fallback used",
            min_risk=min_risk,
            passing=passing,
            filled=len(selected) - passing,
            filled_idx=[c.get("idx") for c in selected[passing:]],
        )
    return selected


@dataclass
class ClauseEvidence:
    clause: Dict[str, Any]
    related: list = field(default_factory=list)  # RetrievalResult from this contract
    precedents: list = field(default_factory=list)  # RetrievalResult from reference_clauses
    precedent_categories: Optional[List[str]] = None


@dataclass
class EvidenceContext:
    text: str
    shown_ids: Set[str]  # IDs that appear in the prompt context
    analyzed_ids: Set[str]  # All C<idx> for the document
    retriever_name: str
    precedents_enabled: bool

    @property
    def allowed_ids(self) -> Set[str]:
        return self.analyzed_ids | self.shown_ids


def _precedent_retriever(session) -> Optional[Retriever]:
    if session is None or get_embedder() is None or not vector_extension_available(session):
        logger.warning("Precedent retrieval unavailable, skipping precedents")
        return None
    return PgVectorRetriever(session, "reference_clauses")


def gather_evidence(
    priority: Sequence[Dict[str, Any]],
    clauses: Sequence[Dict[str, Any]],
    session=None,
    document_id: Optional[int] = None,
    related_k: int = RELATED_K,
    precedent_k: int = PRECEDENT_K,
):
    """Retrieve related same-contract clauses and precedents for each priority clause."""
    scope = {"document_id": document_id} if document_id is not None else None
    contract_retriever = get_retriever(clauses, session=session, table="clauses", scope=scope)
    precedent_retriever = _precedent_retriever(session)

    evidence = []
    for clause in priority:
        item = ClauseEvidence(clause=clause)
        query = clause.get("text", "")
        item.related = contract_retriever.retrieve(
            query, top_k=related_k, filters={"exclude_ids": [clause.get("idx")]}
        )
        if precedent_retriever is not None:
            item.precedent_categories = precedent_categories(clause.get("clause_type"))
            filters = {"categories": item.precedent_categories} if item.precedent_categories else None
            item.precedents = precedent_retriever.retrieve(query, top_k=precedent_k, filters=filters)
        evidence.append(item)

    logger.info(
        "Gathered RAG evidence",
        retriever=contract_retriever.name,
        num_priority=len(priority),
        num_related=sum(len(e.related) for e in evidence),
        num_precedents=sum(len(e.precedents) for e in evidence),
    )
    return evidence, contract_retriever.name, precedent_retriever is not None


def _snippet(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def format_evidence(
    evidence: Sequence[ClauseEvidence],
    clause_chars: int,
    max_chars: int,
    evidence_chars: int = EVIDENCE_CHARS,
) -> Tuple[str, Set[str]]:
    """Render evidence blocks until `max_chars`; returns (text, IDs shown).

    Whole blocks are kept or dropped so no ID is cut off mid-block.
    """
    blocks: List[str] = []
    shown: Set[str] = set()
    used = 0
    for item in evidence:
        c = item.clause
        risk = c.get("risk_score") or 0
        lines = [f"[C{c.get('idx', 0)}] PRIORITY CLAUSE ({c.get('clause_type') or 'Unknown'}, Risk: {risk:.1f}):",
                 _snippet(c.get("text", ""), clause_chars)]
        ids = {f"C{c.get('idx', 0)}"}
        if item.related:
            lines.append("  Related clauses in this contract:")
            for r in item.related:
                lines.append(f"  [C{r.clause_id}] {_snippet(r.text, evidence_chars)}")
                ids.add(f"C{r.clause_id}")
        if item.precedents:
            label = ", ".join(item.precedent_categories) if item.precedent_categories else "any category"
            lines.append(f"  Precedent clauses from reference contracts (CUAD: {label}):")
            for r in item.precedents:
                lines.append(f"  [P{r.clause_id}] {_snippet(r.text, evidence_chars)}")
                ids.add(f"P{r.clause_id}")
        block = "\n".join(lines) + "\n"
        if used + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        shown |= ids
        used += len(block)
    return "\n".join(blocks), shown


def build_context(
    priority: Sequence[Dict[str, Any]],
    clauses: Sequence[Dict[str, Any]],
    session=None,
    document_id: Optional[int] = None,
    clause_chars: int = 500,
    max_chars: int = 6000,
) -> EvidenceContext:
    try:
        evidence, retriever_name, precedents_enabled = gather_evidence(
            priority, clauses, session=session, document_id=document_id
        )
    except Exception as e:
        # Keep generation working if vector retrieval fails mid-request
        logger.error("Vector retrieval failed, falling back to TF-IDF without precedents", error=str(e))
        if session is not None:
            session.rollback()
        evidence, retriever_name, precedents_enabled = gather_evidence(priority, clauses, session=None)
    text, shown = format_evidence(evidence, clause_chars=clause_chars, max_chars=max_chars)
    return EvidenceContext(
        text=text,
        shown_ids=shown,
        analyzed_ids={f"C{c.get('idx')}" for c in clauses},
        retriever_name=retriever_name,
        precedents_enabled=precedents_enabled,
    )


CITATION_INSTRUCTIONS = """EVIDENCE IDS:
Each clause above is labelled [C<n>] (a clause of this contract) or [P<n>] (a precedent clause from reference contracts).
For every item you produce, put the IDs of the evidence you relied on in "evidence_ids" (e.g. ["C4", "P1043"]) and cite them in "citation".
Only use IDs that appear above. Precedents illustrate common market language; they are not part of this contract."""


@dataclass
class GroundingReport:
    total: int
    ungrounded: List[str]
    invalid_clause_indices: List[int]

    @property
    def ungrounded_rate(self) -> Optional[float]:
        return len(self.ungrounded) / self.total if self.total else None


def extract_citation_ids(texts: Iterable[str]) -> List[str]:
    ids: List[str] = []
    for t in texts:
        ids.extend(f"{kind}{num}" for kind, num in CITATION_PATTERN.findall(t or ""))
    return ids


def check_grounding(items: Sequence[Any], context: EvidenceContext, kind: str) -> GroundingReport:
    """Flag citations that don't map to an analyzed clause or a shown precedent.

    `items` are ClauseRecommendation/RedlineSuggestion-like objects with
    clause_index, citation and evidence_ids attributes.
    """
    cited: List[str] = []
    invalid_indices: List[int] = []
    analyzed_idx = {int(i[1:]) for i in context.analyzed_ids}
    for item in items:
        ids = list(getattr(item, "evidence_ids", None) or [])
        ids += extract_citation_ids([getattr(item, "citation", "") or ""])
        cited.extend(dict.fromkeys(ids))  # de-duplicate per item, keep order
        clause_index = getattr(item, "clause_index", None)
        if clause_index is not None and clause_index not in analyzed_idx:
            invalid_indices.append(clause_index)

    allowed = context.allowed_ids
    ungrounded = [i for i in cited if i not in allowed]
    report = GroundingReport(total=len(cited), ungrounded=ungrounded, invalid_clause_indices=invalid_indices)
    log = logger.warning if (ungrounded or invalid_indices) else logger.info
    log(
        "Citation grounding check",
        kind=kind,
        citations=report.total,
        ungrounded=len(ungrounded),
        ungrounded_rate=report.ungrounded_rate,
        ungrounded_ids=ungrounded,
        invalid_clause_indices=invalid_indices,
    )
    return report
