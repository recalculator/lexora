"""Metric functions against hand-computed values."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import metrics as M  # noqa: E402

# Ranked relevance for one query: relevant at ranks 2, 3 and 7; |R| = 4
RANKED = [False, True, True, False, False, False, True, False, False, False]


def test_precision():
    assert M.precision_at_k(RANKED, 3) == pytest.approx(2 / 3)
    assert M.precision_at_k(RANKED, 10) == pytest.approx(3 / 10)
    # Fewer than k results: denominator stays k
    assert M.precision_at_k([True], 3) == pytest.approx(1 / 3)


def test_hit_rate():
    assert M.hit_rate_at_k(RANKED, 1) == 0.0
    assert M.hit_rate_at_k(RANKED, 3) == 1.0


def test_mrr():
    assert M.mrr_at_k(RANKED, 10) == pytest.approx(1 / 2)
    assert M.mrr_at_k([False] * 10, 10) == 0.0
    assert M.mrr_at_k([False] * 10 + [True], 10) == 0.0


def test_ndcg_hand_computed():
    dcg = 1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(8)
    idcg = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5)  # min(|R|=4, 10)
    assert M.ndcg_at_k(RANKED, 4, 10) == pytest.approx(dcg / idcg)
    # |R| larger than k: ideal is 10 relevant items
    idcg10 = sum(1 / math.log2(i + 1) for i in range(1, 11))
    assert M.ndcg_at_k(RANKED, 500, 10) == pytest.approx(dcg / idcg10)
    assert M.ndcg_at_k([True] * 10, 10, 10) == pytest.approx(1.0)


def test_recall_and_max_recall():
    assert M.recall_at_k(RANKED, 4, 10) == pytest.approx(3 / 4)
    assert M.max_recall_at_k(4, 10) == 1.0
    assert M.recall_at_k(RANKED, 500, 10) == pytest.approx(3 / 500)
    assert M.max_recall_at_k(500, 10) == pytest.approx(10 / 500)


def test_query_metrics_keys():
    qm = M.query_metrics(RANKED, 4)
    assert set(qm) == {"precision@3", "precision@10", "hit_rate@3", "hit_rate@10", "mrr@10", "ndcg@10",
                       "recall@10", "max_recall@10"}


def test_ann_recall():
    assert M.ann_recall([1, 2, 3, 4], [1, 2, 5, 6]) == pytest.approx(0.5)
    assert M.ann_recall([1, 2], [1, 2]) == 1.0  # fewer than 10 rows match the filter
    assert M.ann_recall([], []) == 1.0


def test_bootstrap_ci_contains_mean_and_is_deterministic():
    values = [0.0, 1.0] * 50
    lo, hi = M.bootstrap_ci(values, seed=42)
    assert lo < 0.5 < hi
    assert M.bootstrap_ci(values, seed=42) == [lo, hi]


def test_percentiles():
    p = M.percentiles(list(range(1, 101)))
    assert p["n"] == 100 and p["p50"] == pytest.approx(50.5) and p["mean"] == pytest.approx(50.5)
