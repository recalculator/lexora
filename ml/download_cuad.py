"""Download the official CUAD v1 release and verify it.

Source: Hugging Face dataset repo `theatticusproject/cuad` (The Atticus
Project), file `CUAD_v1/CUAD_v1.json`, pinned to a fixed revision. The legacy
`load_dataset("cuad")` script loader no longer works with current `datasets`
releases, and `theatticusproject/cuad-qa` is also script-only.

This script fails loudly (non-zero exit) if the download or any check fails;
it never substitutes toy data.

Usage (from ml/):  python download_cuad.py [--out data/cuad]
"""
import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO_ID = "theatticusproject/cuad"
REVISION = "a3c393f5d103fd0c516374e4fdff676c8176dcb1"
FILENAME = "CUAD_v1/CUAD_v1.json"

# Published CUAD v1 facts (Hendrycks et al., 2021) used as integrity checks
EXPECTED_CONTRACTS = 510
EXPECTED_CATEGORIES = 41


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path) -> dict:
    """Check the SQuAD-style structure and counts; raise on any problem."""
    with open(path, "r") as f:
        data = json.load(f)
    contracts = data["data"]
    categories = Counter()
    questions = {}
    qas_total = 0
    answers_total = 0
    for contract in contracts:
        if len(contract["paragraphs"]) != 1:
            raise ValueError(f"Expected one paragraph per contract: {contract['title']}")
        for qa in contract["paragraphs"][0]["qas"]:
            qas_total += 1
            category = qa["id"].rsplit("__", 1)[1]
            categories[category] += 1
            questions.setdefault(category, qa["question"])
            answers_total += len(qa["answers"])

    if len(contracts) != EXPECTED_CONTRACTS:
        raise ValueError(f"Expected {EXPECTED_CONTRACTS} contracts, found {len(contracts)}")
    if len(categories) != EXPECTED_CATEGORIES:
        raise ValueError(f"Expected {EXPECTED_CATEGORIES} categories, found {len(categories)}")
    uneven = {c: n for c, n in categories.items() if n != len(contracts)}
    if uneven:
        raise ValueError(f"Every category should have one question per contract: {uneven}")
    if answers_total == 0:
        raise ValueError("No answer spans found")

    return {
        "contracts": len(contracts),
        "categories": len(categories),
        "questions": qas_total,
        "answer_spans": answers_total,
        "category_names": sorted(categories),
    }


def download_cuad(out_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download

    print(f"Downloading {REPO_ID}@{REVISION}:{FILENAME} ...")
    cached = hf_hub_download(repo_id=REPO_ID, filename=FILENAME, repo_type="dataset", revision=REVISION)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "CUAD_v1.json"
    shutil.copyfile(cached, target)

    stats = verify(target)
    stats.update({"source": f"hf://datasets/{REPO_ID}@{REVISION}/{FILENAME}", "sha256": sha256(target)})
    with open(out_dir / "CUAD_v1.source.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Verified: {stats['contracts']} contracts, {stats['categories']} categories, "
          f"{stats['questions']} questions, {stats['answer_spans']} answer spans")
    print(f"sha256: {stats['sha256']}")
    print(f"Saved to {target}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/cuad", type=Path)
    args = parser.parse_args()
    try:
        download_cuad(args.out)
    except Exception as e:
        print(f"ERROR: CUAD download/verification failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
