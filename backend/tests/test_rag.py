"""Tests for RAG context building and citation grounding (LLM stubbed)."""
from unittest.mock import patch

import pytest

from app.services import playbook as playbook_module
from app.services import redlines as redlines_module
from app.services import rag
from app.services.playbook import ClauseRecommendation, NegotiationPlaybook, generate_playbook
from app.services.redlines import RedlineSuggestion, RedlineSuggestions, generate_redlines
from app.services.retrieval import RetrievalResult

CLAUSES = [
    {"idx": 0, "text": "Definitions. Confidential Information means all non-public information disclosed by either party.", "clause_type": "Confidentiality", "risk_score": 40.0},
    {"idx": 1, "text": "Either party may terminate this Agreement for convenience upon thirty days written notice.", "clause_type": "Termination", "risk_score": 70.0},
    {"idx": 2, "text": "Customer shall indemnify Provider against all third-party claims arising from Customer Data.", "clause_type": "Indemnification", "risk_score": 90.0},
    {"idx": 3, "text": "Provider's total liability shall not exceed the fees paid in the twelve months before the claim.", "clause_type": "Liability Cap", "risk_score": 70.0},
    {"idx": 4, "text": "Notices shall be sent to the addresses set out above.", "clause_type": None, "risk_score": 65.0},
]


# --- Priority ordering -----------------------------------------------------------

def test_priority_ordered_by_risk_desc_ties_by_index():
    ordered = rag.order_priority_clauses(CLAUSES, min_risk=60, limit=10)
    assert [c["idx"] for c in ordered] == [2, 1, 3, 4]


def test_priority_threshold_limit_and_type():
    ordered = rag.order_priority_clauses(CLAUSES, min_risk=50, limit=2, require_type=True)
    assert [c["idx"] for c in ordered] == [2, 1]


def test_priority_fallback_fills_to_three_by_risk_then_index():
    clauses = [
        {"idx": 0, "text": "a", "clause_type": "Termination", "risk_score": 10.0},
        {"idx": 1, "text": "b", "clause_type": "Termination", "risk_score": 80.0},
        {"idx": 2, "text": "c", "clause_type": "Insurance", "risk_score": 20.0},
        {"idx": 3, "text": "d", "clause_type": "Assignment", "risk_score": 20.0},
        {"idx": 4, "text": "e", "clause_type": "Assignment", "risk_score": 5.0},
    ]
    with patch.object(rag, "logger") as logger:
        ordered = rag.order_priority_clauses(clauses, min_risk=60, limit=10)
    assert [c["idx"] for c in ordered] == [1, 2, 3]  # 2 and 3 tie at 20 -> document order
    logger.info.assert_called_once()
    assert logger.info.call_args.kwargs["filled_idx"] == [2, 3]


def test_priority_no_fallback_when_enough_pass():
    with patch.object(rag, "logger") as logger:
        ordered = rag.order_priority_clauses(CLAUSES, min_risk=60, limit=10)
    assert len(ordered) == 4
    logger.info.assert_not_called()


def test_priority_fallback_with_fewer_clauses_than_minimum_and_type_requirement():
    clauses = [
        {"idx": 0, "text": "a", "clause_type": None, "risk_score": 50.0},
        {"idx": 1, "text": "b", "clause_type": "Termination", "risk_score": 10.0},
    ]
    assert [c["idx"] for c in rag.order_priority_clauses(clauses, min_risk=60, limit=8)] == [0, 1]
    assert [c["idx"] for c in rag.order_priority_clauses(clauses, min_risk=60, limit=8, require_type=True)] == [1]
    assert rag.order_priority_clauses([], min_risk=60, limit=8) == []


# --- Category map ------------------------------------------------------------------

def test_category_map_covers_all_app_types():
    from app.services.onnx_infer import CLAUSE_TYPES
    mapping = rag.load_category_map()
    assert set(mapping) == set(CLAUSE_TYPES)
    assert mapping["Indemnification"] is None and mapping["Confidentiality"] is None
    for entry in mapping.values():
        if entry:
            assert set(entry["loose"]) <= set(entry["categories"])
    assert mapping["Termination"]["loose"] == ["Notice Period To Terminate Renewal"]


def test_category_map_spellings_match_cuad():
    """Mapped names must be real CUAD categories (needs bench/corpus/cuad_split.json)."""
    import json
    from pathlib import Path
    split = Path(__file__).resolve().parents[2] / "bench/corpus/cuad_split.json"
    if not split.exists():
        pytest.skip("bench/corpus/cuad_split.json not available (run outside the repo checkout)")
    cuad = set(json.loads(split.read_text())["final_categories"])
    mapped = {c for entry in rag.load_category_map().values() if entry for c in entry["categories"]}
    assert mapped <= cuad, mapped - cuad


def test_unmapped_type_means_unfiltered():
    assert rag.precedent_categories("Indemnification") is None
    assert rag.precedent_categories(None) is None
    assert rag.precedent_categories("Governing Law") == ["Governing Law"]


# --- Formatting ------------------------------------------------------------------

def make_evidence():
    item = rag.ClauseEvidence(
        clause=CLAUSES[1],
        related=[RetrievalResult(0, CLAUSES[0]["text"], 0.5)],
        precedents=[RetrievalResult(1043, "Either party may terminate for convenience.", 0.8)],
        precedent_categories=["Termination For Convenience"],
    )
    return [item, rag.ClauseEvidence(clause=CLAUSES[2])]


def test_format_evidence_labels_ids():
    text, shown = rag.format_evidence(make_evidence(), clause_chars=500, max_chars=10_000)
    assert "[C1] PRIORITY CLAUSE (Termination, Risk: 70.0)" in text
    assert "[C0]" in text and "[P1043]" in text and "[C2]" in text
    assert shown == {"C1", "C0", "P1043", "C2"}


def test_format_evidence_budget_drops_whole_blocks():
    first_only, _ = rag.format_evidence(make_evidence()[:1], clause_chars=500, max_chars=10_000)
    text, shown = rag.format_evidence(make_evidence(), clause_chars=500, max_chars=len(first_only) + 5)
    assert shown == {"C1", "C0", "P1043"}
    assert "[C2]" not in text


# --- Grounding check -------------------------------------------------------------------

def make_context(shown=frozenset({"C1", "C0", "P1043"})):
    return rag.EvidenceContext(
        text="", shown_ids=set(shown), analyzed_ids={f"C{c['idx']}" for c in CLAUSES},
        retriever_name="tfidf", precedents_enabled=True,
    )


def rec(clause_index, citation, evidence_ids):
    return ClauseRecommendation(
        clause_index=clause_index, clause_type="Termination", risk_level="high", concern="c",
        recommendation="r", negotiation_strategy="s", citation=citation, evidence_ids=evidence_ids,
    )


def test_grounding_all_valid():
    report = rag.check_grounding([rec(1, "See C1 and P1043", ["C1", "P1043"])], make_context(), "playbook")
    assert report.total == 2  # de-duplicated within the item
    assert report.ungrounded == [] and report.ungrounded_rate == 0.0


def test_grounding_flags_unshown_precedent_and_unknown_clause():
    items = [
        rec(1, "C1", ["C1", "P1043"]),       # 2 valid
        rec(3, "C3 (analyzed but not shown is OK)", []),  # 1 valid
        rec(2, "Per P999 and C42", ["P999"]),  # P999 not shown, C42 not analyzed
        rec(77, "", []),                      # clause_index not analyzed
    ]
    report = rag.check_grounding(items, make_context(), "playbook")
    assert report.total == 5
    assert report.ungrounded == ["P999", "C42"]
    assert report.ungrounded_rate == pytest.approx(2 / 5)
    assert report.invalid_clause_indices == [77]


def test_grounding_no_citations_rate_is_none():
    assert rag.check_grounding([], make_context(), "playbook").ungrounded_rate is None


def test_citation_regex_ignores_non_ids():
    assert rag.extract_citation_ids(["Section 4, C12, P7, CP3, AC5, C-1, (C2)"]) == ["C12", "P7", "C2"]


# --- End-to-end with stubbed LLM (no DB: TF-IDF, no precedents) ------------------------

def capture_grounding():
    reports = []

    def run(*args, **kwargs):
        report = rag.check_grounding(*args, **kwargs)
        reports.append(report)
        return report

    return reports, run


def stub_playbook(prompt, schema, **kwargs):
    stub_playbook.prompt = prompt
    return NegotiationPlaybook(
        document_summary="s", overall_risk_assessment="high", general_recommendations=[], key_provisions=[],
        priority_clauses=[rec(2, "C2", ["C2"]), rec(1, "P5", ["P5"])],
    )


def test_generate_playbook_uses_retrieval_and_checks_grounding():
    reports, run = capture_grounding()
    with patch.object(playbook_module, "call_llm_with_schema", side_effect=stub_playbook), \
            patch.object(playbook_module, "log_prompt"), \
            patch.object(playbook_module, "check_grounding", side_effect=run):
        result = generate_playbook(CLAUSES, "doc", document_id=None, db=None)

    prompt = stub_playbook.prompt
    assert "# Truncate" not in prompt
    # Highest risk first
    assert prompt.index("[C2] PRIORITY") < prompt.index("[C1] PRIORITY") < prompt.index("[C3] PRIORITY")
    assert "Related clauses in this contract:" in prompt
    assert "evidence_ids" in prompt
    assert len(reports) == 1
    assert reports[0].ungrounded == ["P5"]  # no precedents were shown without a DB
    assert len(result.priority_clauses) == 2


def stub_redlines(prompt, schema, **kwargs):
    stub_redlines.prompt = prompt
    suggestion = RedlineSuggestion(
        clause_index=2, clause_type="Indemnification", original_text="o", suggested_change="[DEL: all]",
        rationale="r", risk_reduction="x", citation="C2", evidence_ids=["C2"],
    )
    return RedlineSuggestions(summary="s", priority_redlines=[suggestion], optional_redlines=[], general_notes=[])


def test_generate_redlines_requires_type_and_checks_grounding():
    reports, run = capture_grounding()
    with patch.object(redlines_module, "call_llm_with_schema", side_effect=stub_redlines), \
            patch.object(redlines_module, "log_prompt"), \
            patch.object(redlines_module, "check_grounding", side_effect=run):
        generate_redlines(CLAUSES, "doc", document_id=None, db=None)

    prompt = stub_redlines.prompt
    assert "# Truncate" not in prompt
    assert "[C4] PRIORITY" not in prompt  # untyped clause excluded from redlines
    assert prompt.index("[C2] PRIORITY") < prompt.index("[C1] PRIORITY")
    assert len(reports) == 1 and reports[0].ungrounded == []


def test_schema_evidence_ids_optional():
    data = rec(1, "C1", []).model_dump()
    data.pop("evidence_ids")
    assert ClauseRecommendation.model_validate(data).evidence_ids == []


# --- With pgvector (runs only with TEST_DATABASE_URL) ----------------------------------

def test_precedents_filtered_by_mapped_category(pg_session):
    from sqlalchemy import insert, text
    from app.db.models import Clause, Document, ReferenceClause
    from app.services.retrieval import get_embedder

    embedder = get_embedder()
    if embedder is None:
        pytest.skip("Embedding model unavailable")
    doc = Document(filename="t.pdf", original_filename="t.pdf")
    pg_session.add(doc)
    pg_session.flush()
    vecs = embedder.encode([c["text"] for c in CLAUSES])
    pg_session.execute(insert(Clause), [
        {"document_id": doc.id, "idx": c["idx"], "text": c["text"], "start_char": 0, "end_char": 1,
         "clause_type": c["clause_type"], "risk_score": c["risk_score"], "confidence": 0.5, "embedding": vecs[i]}
        for i, c in enumerate(CLAUSES)
    ])
    refs = [
        ("Termination For Convenience", "Either party may terminate this agreement at any time for convenience on notice."),
        ("Governing Law", "This agreement is governed by the laws of Delaware."),
        ("Cap On Liability", "In no event shall liability exceed the amounts paid hereunder."),
    ]
    ref_vecs = embedder.encode([t for _, t in refs])
    pg_session.execute(insert(ReferenceClause), [
        {"source_contract": "test", "categories": [cat], "text": t, "embedding": ref_vecs[i]}
        for i, (cat, t) in enumerate(refs)
    ])
    pg_session.flush()
    ids = dict(pg_session.execute(
        text("select categories[1], id from reference_clauses where source_contract = 'test'")
    ).fetchall())

    priority = rag.order_priority_clauses(CLAUSES, min_risk=60, limit=10)
    context = rag.build_context(priority, CLAUSES, session=pg_session, document_id=doc.id)

    assert context.retriever_name == "hybrid"
    assert context.precedents_enabled

    def precedent_categories_in(block):
        pids = [int(n) for kind, n in rag.CITATION_PATTERN.findall(block) if kind == "P"]
        assert pids, "expected precedents in block"
        rows = pg_session.execute(
            text("select id, categories from reference_clauses where id = any(:ids)"), {"ids": pids}
        ).fetchall()
        return [set(cats) for _, cats in rows]

    # Termination clause (C1) only gets Termination-mapped precedents
    # (works whether or not the real CUAD corpus is loaded alongside the test rows)
    block_c1 = context.text.split("[C1] PRIORITY")[1].split("PRIORITY CLAUSE")[0]
    mapped = set(rag.precedent_categories("Termination"))
    assert all(cats & mapped for cats in precedent_categories_in(block_c1))
    assert f"[P{ids['Governing Law']}]" not in block_c1
    # Indemnification (C2) is unmapped -> unfiltered search, labelled as such
    block_c2 = context.text.split("[C2] PRIORITY")[1].split("PRIORITY CLAUSE")[0]
    assert "(CUAD: any category)" in block_c2
    precedent_categories_in(block_c2)
