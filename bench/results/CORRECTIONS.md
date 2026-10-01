# Corrections to results files

Results files in this directory are never edited after they are written. Errors found later are
recorded here.

## 2026-10-01: `20261001T192230Z_local_posthoc.json` (and its `.md`)

- **Field:** `diagnostics.note`
- **Says:** "Measured on the current index (rebuilt by part B of the original run), not the index Part A
  used."
- **Correct:** the HNSW index `ix_reference_clauses_embedding_hnsw` was rebuilt by a manual
  `REINDEX INDEX ix_reference_clauses_embedding_hnsw`, run immediately before this post-hoc run, after
  rolled-back inserts from database tests had grown it to 39,559,168 bytes. After the REINDEX it was
  13,762,560 bytes (the original run's Part B build was 13,754,368 bytes). The note was a hardcoded
  string in `bench/posthoc.py`; it is still true that the diagnostics were not measured on the index
  Part A used.
- **Impact on numbers:** none. The measured values in the file are unaffected; only the description of
  the index's history was wrong.
- **Fix:** `bench/posthoc.py` now records the index definition and size at start, and records a
  REINDEX only when it performs one itself (`--reindex`, or `make bench-posthoc REINDEX=1`).
