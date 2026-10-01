"""Build the clause-level CUAD corpus and the reference/eval split.

Each annotated CUAD answer span becomes a clause. Identical (whitespace-
normalized) span texts within the same contract are merged into one row that
carries the set of all their CUAD categories; relevance in the benchmark is
"query category in that set". Metadata-field categories are excluded (and
removed from category sets; a row whose set becomes empty is dropped). Contracts (not clauses) are split into reference vs eval with a
fixed seed, so no contract appears in both.

Token lengths and truncation are measured with the embedding model's own
tokenizer and max_seq_length (counts include the [CLS]/[SEP] special tokens,
because the model's limit applies to the full input).

Outputs:
  bench/data/cuad_corpus.jsonl          clause rows (gitignored)
  bench/corpus/cuad_split.json          split: seed, contracts per split, final categories
  bench/corpus/cuad_corpus_meta.json    source, exclusions, length and truncation stats

Run inside the backend image (it has the pinned embedding model):
  python bench/build_cuad_corpus.py --cuad ml/data/cuad/CUAD_v1.json
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SEED = 42
EVAL_FRACTION = 0.2
SHORT_SPAN_TOKENS = 12

# Categories that label document metadata rather than clauses. Expiration Date
# and Renewal Term were checked against the data (see meta "kept_checked").
EXCLUDED = {
    "Document Name": "Metadata field: the contract's title, not a clause.",
    "Parties": "Metadata field: party names, not a clause.",
    "Agreement Date": "Metadata field: a date, not a clause.",
    "Effective Date": "Metadata field: a date, not a clause.",
}
CHECKED_KEPT = ("Expiration Date", "Renewal Term")


def length_stats(lengths):
    a = np.asarray(lengths)
    if a.size == 0:
        return None
    return {
        "n": int(a.size),
        "min": int(a.min()),
        "median": float(np.median(a)),
        "p95": float(np.percentile(a, 95)),
        "max": int(a.max()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cuad", type=Path, default=ROOT / "ml/data/cuad/CUAD_v1.json")
    parser.add_argument("--out-data", type=Path, default=ROOT / "bench/data")
    parser.add_argument("--out-meta", type=Path, default=ROOT / "bench/corpus")
    args = parser.parse_args()

    from app.core.config import settings
    from app.services.retrieval import get_embedder

    embedder = get_embedder()
    if embedder is None:
        sys.exit("ERROR: embedding model unavailable")
    tokenizer = embedder.model.tokenizer
    max_len = int(embedder.model.max_seq_length)

    source_path = args.cuad.with_name("CUAD_v1.source.json")
    if not source_path.exists():
        sys.exit(f"ERROR: {source_path} missing; run ml/download_cuad.py first")
    source = json.loads(source_path.read_text())
    contracts = json.loads(args.cuad.read_text())["data"]
    if len(contracts) != source["contracts"]:
        sys.exit("ERROR: CUAD file does not match its verified source record")

    # --- Extract spans --------------------------------------------------------
    questions = {}
    raw_counts = Counter()
    seen = set()
    rows = []
    for contract in contracts:
        title = contract["title"]
        for qa in contract["paragraphs"][0]["qas"]:
            category = qa["id"].rsplit("__", 1)[1]
            questions.setdefault(category, qa["question"])
            for answer in qa["answers"]:
                raw_counts[category] += 1
                text = " ".join(answer["text"].split())
                key = (title, category, text)
                if not text or key in seen:
                    continue
                seen.add(key)
                rows.append({"contract": title, "category": category, "text": text})

    for row in rows:
        row["n_tokens"] = len(tokenizer(row["text"], truncation=False)["input_ids"])
        row["truncated"] = row["n_tokens"] > max_len

    by_cat = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row["n_tokens"])

    def category_profile(cat):
        lengths = by_cat[cat]
        return {
            "raw_answer_spans": raw_counts[cat],
            "dedup_spans": len(lengths),
            "contracts_with_span": len({r["contract"] for r in rows if r["category"] == cat}),
            "tokens": length_stats(lengths),
            f"share_le_{SHORT_SPAN_TOKENS}_tokens": float(np.mean(np.asarray(lengths) <= SHORT_SPAN_TOKENS)),
        }

    excluded = {cat: {"reason": reason, **category_profile(cat)} for cat, reason in EXCLUDED.items()}
    kept_checked = {
        cat: {
            "decision": "kept",
            "reason": "Spans are mostly full term/renewal provisions, not bare dates (see token stats).",
            **category_profile(cat),
        }
        for cat in CHECKED_KEPT
    }

    kept_spans = [r for r in rows if r["category"] not in EXCLUDED]
    categories = sorted({r["category"] for r in kept_spans})

    # --- Merge identical texts within a contract --------------------------------
    merged = {}
    for r in kept_spans:
        key = (r["contract"], r["text"])
        if key not in merged:
            merged[key] = {"contract": r["contract"], "text": r["text"], "categories": set(),
                           "n_tokens": r["n_tokens"], "truncated": r["truncated"]}
        merged[key]["categories"].add(r["category"])
    corpus = list(merged.values())
    for row in corpus:
        row["categories"] = sorted(row["categories"])
    multi_label_rows = sum(1 for r in corpus if len(r["categories"]) > 1)

    # --- Split by contract ------------------------------------------------------
    titles = sorted(c["title"] for c in contracts)
    rng = random.Random(SEED)
    shuffled = titles[:]
    rng.shuffle(shuffled)
    n_eval = round(len(shuffled) * EVAL_FRACTION)
    eval_contracts = sorted(shuffled[:n_eval])
    reference_contracts = sorted(shuffled[n_eval:])
    overlap = set(eval_contracts) & set(reference_contracts)
    if overlap:
        sys.exit(f"ERROR: contracts in both splits: {sorted(overlap)[:5]}")
    split_of = {t: "eval" for t in eval_contracts}
    split_of.update({t: "reference" for t in reference_contracts})

    corpus.sort(key=lambda r: (r["contract"], r["text"]))
    for i, row in enumerate(corpus):
        row["id"] = i
        row["split"] = split_of[row["contract"]]

    def rows_with(cat, part):
        return [r for r in part if cat in r["categories"]]

    per_split = {}
    for split in ("reference", "eval"):
        part = [r for r in corpus if r["split"] == split]
        per_split[split] = {
            "contracts": len(eval_contracts if split == "eval" else reference_contracts),
            "contracts_with_clauses": len({r["contract"] for r in part}),
            "clauses": len(part),
            "per_category": {cat: len(rows_with(cat, part)) for cat in categories},
        }
    missing_in_split = {
        split: [c for c in categories if per_split[split]["per_category"].get(c, 0) == 0]
        for split in per_split
    }

    truncated = [r for r in corpus if r["truncated"]]
    meta = {
        "source": source,
        "embedding_model": settings.embedding_model,
        "embedding_model_revision": settings.embedding_model_revision,
        "tokenizer": type(tokenizer).__name__,
        "max_seq_length": max_len,
        "token_count_includes_special_tokens": True,
        "clause_rule": "one row per (contract, whitespace-normalized answer span) carrying the set of its CUAD categories",
        "excluded_categories": excluded,
        "kept_checked": kept_checked,
        "merge": {
            "spans_before_merge": len(kept_spans),
            "rows_after_merge": len(corpus),
            "rows_merged_away": len(kept_spans) - len(corpus),
            "rows_with_multiple_categories": multi_label_rows,
            "max_categories_per_row": max(len(r["categories"]) for r in corpus),
        },
        "corpus": {
            "clauses": len(corpus),
            "contracts_with_clauses": len({r["contract"] for r in corpus}),
            "categories": len(categories),
            "tokens": length_stats([r["n_tokens"] for r in corpus]),
        },
        "truncation": {
            "max_seq_length": max_len,
            "clauses_over_limit": len(truncated),
            "share_over_limit": len(truncated) / len(corpus),
            "per_category": {
                cat: {
                    "clauses": len(rows_with(cat, corpus)),
                    "over_limit": len(rows_with(cat, truncated)),
                }
                for cat in categories
            },
            "per_split": {
                split: sum(1 for r in truncated if r["split"] == split) for split in ("reference", "eval")
            },
        },
        "per_category_tokens": {
            cat: length_stats([r["n_tokens"] for r in rows_with(cat, corpus)]) for cat in categories
        },
        "splits": per_split,
    }
    split_meta = {
        "seed": SEED,
        "eval_fraction": EVAL_FRACTION,
        "method": "random.Random(seed).shuffle(sorted contract titles); first round(n*eval_fraction) are eval",
        "contracts_total": len(titles),
        "contract_overlap": len(overlap),
        "final_categories": categories,
        "excluded_categories": sorted(EXCLUDED),
        "category_questions": {cat: questions[cat] for cat in categories},
        "categories_missing_from_split": missing_in_split,
        "counts": {split: {k: v for k, v in s.items() if k != "per_category"} for split, s in per_split.items()},
        "eval_contracts": eval_contracts,
        "reference_contracts": reference_contracts,
    }

    args.out_data.mkdir(parents=True, exist_ok=True)
    args.out_meta.mkdir(parents=True, exist_ok=True)
    with open(args.out_data / "cuad_corpus.jsonl", "w") as f:
        for row in corpus:
            f.write(json.dumps(row) + "\n")
    (args.out_meta / "cuad_split.json").write_text(json.dumps(split_meta, indent=2) + "\n")
    (args.out_meta / "cuad_corpus_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"merged {len(kept_spans)} spans into {len(corpus)} rows ({multi_label_rows} multi-category); "
          f"corpus clauses={len(corpus)} categories={len(categories)} "
          f"reference={per_split['reference']['clauses']} eval={per_split['eval']['clauses']} "
          f"truncated={len(truncated)}")


if __name__ == "__main__":
    main()
