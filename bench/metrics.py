"""Retrieval metrics, as defined in bench/PREREGISTRATION.md.

All functions take `ranked`, a list of booleans (is result i relevant), best
first, and `n_relevant` = |R|, the number of relevant items in the index.
"""
import math
from typing import Dict, List, Sequence

import numpy as np


def precision_at_k(ranked: Sequence[bool], k: int) -> float:
    return sum(ranked[:k]) / k


def hit_rate_at_k(ranked: Sequence[bool], k: int) -> float:
    return 1.0 if any(ranked[:k]) else 0.0


def mrr_at_k(ranked: Sequence[bool], k: int) -> float:
    for i, rel in enumerate(ranked[:k], start=1):
        if rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[bool], n_relevant: int, k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, rel in enumerate(ranked[:k], start=1) if rel)
    ideal = min(n_relevant, k)
    if ideal == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal + 1))
    return dcg / idcg


def recall_at_k(ranked: Sequence[bool], n_relevant: int, k: int) -> float:
    return sum(ranked[:k]) / n_relevant if n_relevant else 0.0


def max_recall_at_k(n_relevant: int, k: int) -> float:
    return min(k, n_relevant) / n_relevant if n_relevant else 0.0


def query_metrics(ranked: Sequence[bool], n_relevant: int) -> Dict[str, float]:
    """All pre-registered metrics for one query."""
    return {
        "precision@3": precision_at_k(ranked, 3),
        "precision@10": precision_at_k(ranked, 10),
        "hit_rate@3": hit_rate_at_k(ranked, 3),
        "hit_rate@10": hit_rate_at_k(ranked, 10),
        "mrr@10": mrr_at_k(ranked, 10),
        "ndcg@10": ndcg_at_k(ranked, n_relevant, 10),
        "recall@10": recall_at_k(ranked, n_relevant, 10),
        "max_recall@10": max_recall_at_k(n_relevant, 10),
    }


def mean_metrics(rows: List[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {}
    return {key: float(np.mean([r[key] for r in rows])) for key in rows[0]}


def bootstrap_ci(values: Sequence[float], resamples: int = 1000, seed: int = 42, alpha: float = 0.05):
    """Percentile bootstrap CI of the mean."""
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return None
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, a.size, size=(resamples, a.size))].mean(axis=1)
    return [float(np.percentile(means, 100 * alpha / 2)), float(np.percentile(means, 100 * (1 - alpha / 2)))]


def ann_recall(ann_ids: Sequence, exact_ids: Sequence) -> float:
    """|ANN ∩ exact| / |exact| (|exact| is 10 unless fewer rows match)."""
    if not exact_ids:
        return 1.0 if not ann_ids else 0.0
    return len(set(ann_ids) & set(exact_ids)) / len(exact_ids)


def percentiles(values_ms: Sequence[float]) -> Dict[str, float]:
    a = np.asarray(values_ms, dtype=float)
    return {
        "n": int(a.size),
        "p50": float(np.percentile(a, 50)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
        "mean": float(a.mean()),
    }
