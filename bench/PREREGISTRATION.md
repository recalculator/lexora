# Retrieval benchmark: pre-registered design

Written on 2026-10-01, before any benchmark results were produced. Every
reported number must come from a results file in `bench/results/` produced by
`bench/run_bench.py`; nothing here is a result.

## Data

- Corpus: CUAD v1 (`theatticusproject/cuad@a3c393f5d103fd0c516374e4fdff676c8176dcb1`), built by
  `bench/build_cuad_corpus.py`. Metadata categories (Document Name, Parties, Agreement Date,
  Effective Date) excluded; 37 categories remain (`bench/corpus/cuad_split.json`).
- Rows: identical span texts within one contract are merged into one row carrying the set of all
  their categories.
- Split: by contract, seed 42, 20% eval. Reference rows are the index (`reference_clauses`); eval
  rows are queries. No contract appears in both.

## Queries and relevance (Part A)

- Query set 1, clause-as-query: one query per (eval row, category) pair; query text = the row text.
  A retrieved reference row is relevant iff the query's category is in the row's category set.
- Query set 2, category questions: one query per category, text = CUAD's natural-language question
  for that category (37 queries). Relevance as above. Reported separately; small n.
- Each method returns its top 10 reference rows per query.

## Metrics

Headline: **Precision@3** (the app shows the LLM 3 precedents) and **Precision@10**.

Also reported: MRR@10, nDCG@10, HitRate@3, HitRate@10, Recall@10 with its per-query maximum.

For a query with relevant set R (|R| = reference rows containing the query's category) and ranked
results r_1..r_10:

- Precision@k = |{i <= k : r_i relevant}| / k (denominator is k even if fewer than k results return)
- HitRate@k = 1 if any r_i (i <= k) is relevant, else 0
- MRR@10 = 1 / (rank of the first relevant result within the top 10), else 0
- nDCG@10 = DCG / IDCG, DCG = sum_i rel_i / log2(i + 1), binary rel; IDCG uses min(|R|, 10) relevant items
- Recall@10 = |{i <= 10 : r_i relevant}| / |R|; MaxRecall@10 = min(10, |R|) / |R|

Aggregation: mean over queries. Per-category breakdown = mean over that category's queries. Each
method's 5 weakest categories are ranked by Precision@10 ascending (ties by category name), over
categories with at least one query. 95% confidence intervals for the headline metrics: percentile
bootstrap over queries, 1,000 resamples, seed 42.

## Methods (Part A)

- `tfidf`: scikit-learn TF-IDF over the reference rows, same vectorizer settings as the app
  (`max_features=5000, stop_words='english', ngram_range=(1,2), min_df=1, max_df=0.95`), cosine.
- `vector_exact`: pgvector cosine distance, `ORDER BY embedding <=> q LIMIT 10` with index scans
  disabled for the transaction; EXPLAIN must show no index on the embedding.
- `vector_hnsw`: same query using the HNSW index (m=16, ef_construction=64, hnsw.ef_search=40);
  EXPLAIN must show the HNSW index.
- `hybrid`: Reciprocal Rank Fusion (k=60) of `tfidf` and the HNSW index, 50 candidates each. The
  HNSW leg runs with hnsw.ef_search=50 because pgvector's HNSW scan returns at most ef_search rows
  (amended before any results, 2026-10-01).

Embeddings: sentence-transformers/all-MiniLM-L6-v2 at the pinned revision, L2-normalized; inputs
longer than 256 tokens are truncated by the model (counts in `bench/corpus/cuad_corpus_meta.json`).

## Part B: ANN tradeoffs

- Ground truth: exact top-10 by cosine distance (sequential scan) for each eval row (unique texts).
- HNSW `hnsw.ef_search` in {10, 20, 40, 80, 160}: recall@10 = |ANN top-10 ∩ exact top-10| / 10.
- IVFFlat lists = round(N/1000) with probes {1, 5, 10, 20} (probes >= lists labelled "scans all
  lists"), and lists = round(sqrt(N)) with probes {1, 3, 5, 10}.
- Latency: single client connection, sequential queries. Before each timed pass, 100 warmup
  queries (a fixed seeded sample of eval rows) are run and discarded; the timed pass then runs
  every eval row once (at least 500 timed queries). Client round trip (execute + fetch) p50/p95/p99 and QPS (timed queries /
  wall time). Server-side execution time from `EXPLAIN (ANALYZE, BUFFERS)` "Execution Time",
  measured in a separate pass.
- Indexed configurations run with `enable_seqscan = off` so the index is actually exercised (a dry
  run showed the planner choosing a sequential scan for IVFFlat at higher probes); the plan the
  planner picks without that setting is recorded per configuration (amended before any results,
  2026-10-01).
- Index build time and `pg_relation_size` for each index. The default HNSW index is restored at the
  end and the final index set is checked against the migrations.
- Filtered search: the 10 most and 10 least frequent categories in the reference split, filter
  `categories @> ARRAY[category]`, a fixed sample of 200 eval rows as queries (seed 42). Recall@10
  against exact filtered kNN, mean result count and share of queries returning fewer than 10 rows,
  under: planner default; HNSW forced; HNSW forced with `hnsw.iterative_scan` = `relaxed_order` and
  `strict_order` (only if the installed pgvector supports it; otherwise recorded as unsupported).
  The plan used is recorded per category and mode.

## Part C: end to end

Bundled `sample_contract.pdf`, stages timed separately: extract, segment, classify, embed, insert
(rolled back afterwards), retrieve (related clauses + precedents for the priority clauses). 3 warmup
runs discarded, 20 timed; median and p95 per stage.

## Amendment, 2026-10-01: made after results were seen (post-hoc)

This amendment was written **after** the results in
`bench/results/20261001T165752Z_local.json` were seen. Both analyses below are **post-hoc** and are
reported as such. They do not change any pre-registered metric, query set, or method, and the
original results file and its companions are left unmodified. Their outputs go to a new results file
(`bench/results/<timestamp>_<env>_posthoc.json`) written by `bench/posthoc.py`.

1. **Exact filtered search latency (post-hoc).** For the same 20 categories as the filtered-search
   section (10 most and 10 least frequent in the reference split) and the same 200-query sample
   (seed 42), measure exact filtered search, i.e. `enable_indexscan = off` and
   `enable_seqscan = off` so Postgres uses the GIN index on `categories` and sorts by exact
   distance, as the app now does for filtered precedent lookups. Report client round-trip p50/p95
   and server execution p50/p95 (`EXPLAIN (ANALYZE, BUFFERS)`, separate pass), recall@10 against
   exact filtered kNN, mean result count, and the plan. The existing filtered modes (planner
   default, HNSW forced, HNSW forced with iterative scan relaxed/strict) are re-run in the same
   pass so all modes in the new file come from one run.
2. **Paired bootstrap (post-hoc).** On the clause-as-query set of the original run (per-query
   rankings in `bench/results/20261001T165752Z_local_perquery.json.gz`), compute per-query P@3 and
   P@10 and the paired differences hybrid − tfidf and vector_exact − tfidf. Report the mean paired
   difference with a 95% percentile bootstrap CI (10,000 resamples of queries, seed 42). The
   per-method means recomputed from the per-query file must equal the means in the original results
   file; the script fails otherwise.

## Amendment, 2026-10-01: Azure protocol (made before any Azure results)

Written **before** any Azure benchmark results were produced. At the time of writing, the only
Azure artifacts are the setup checks and the corpus load record
(`bench/results/load_20261001T204133Z_azure.json`); `make bench ENV=azure` has not been run. This
amendment adds to the design above and changes nothing in it. All Part A/B/C definitions, metrics,
query sets and methods are unchanged.

**Environment.** Azure Database for PostgreSQL Flexible Server, Burstable B1ms (1 vCore, 2 GiB RAM,
32 GiB storage, P4 120 IOPS), PostgreSQL 16.15, pgvector 0.8.2, region Canada Central, SSL required.
The client is the same machine and Docker image as the local run, in Champaign, Illinois, on a home
network. Two known differences from the local run are recorded and not controlled for: pgvector
0.8.2 on Azure vs 0.8.6 locally, and x86_64 (Azure) vs aarch64 (local Docker) server builds. The
results file records the server hostname only as `<azure-flexible-server>`; the connection string
is never recorded.

1. **Index built after load, then VACUUM ANALYZE (protocol difference).** Locally the HNSW index
   existed before the corpus was loaded, so it was built incrementally by the inserts. On Azure the
   corpus is loaded, then `ix_reference_clauses_embedding_hnsw` is dropped and recreated with the
   migration defaults (m=16, ef_construction=64), then `VACUUM ANALYZE reference_clauses` is run.
   This affects the index Part A uses. Part B rebuilds the index itself in both environments. The
   harness records the index definition, its size and the table's vacuum/analyze timestamps at the
   start of the run (`index_state_at_start`).
2. **Network baseline.** Before Part A, the harness times `SELECT 1` on the benchmark connection
   (20 warmup queries discarded, then 500 timed) and records client round-trip p50/p95/p99
   (`network_baseline_start`). The same measurement is repeated at the very end
   (`network_baseline_end`). From this amendment on it is recorded for every environment.
3. **Server-side execution time is the primary cross-environment comparison.** Client round-trip
   latency on Azure includes the Champaign to Canada Central network path and is reported
   alongside, not used as the comparison. Latency comparisons between local and Azure use
   `EXPLAIN (ANALYZE, BUFFERS)` "Execution Time".
4. **Throttling check (repeated first configuration).** B1ms is burstable: when CPU credits run
   out the server is held to baseline CPU. At the very end of the run (after Part C), the harness
   re-measures Part B's first configuration (`exact`, `enable_indexscan = off`) with the same
   warmup sample and queries, and records it next to the first measurement with repeat/first
   ratios of client p50 and server execution p50 (`throttle_check`). Interpretation rule, fixed
   now: if the repeat's server execution p50 is more than 1.2× the first's, the run's latency
   results are reported as possibly affected by throttling. Quality metrics (Part A) are not
   affected by throttling and are reported as usual. No latency number is adjusted or corrected.
5. **User-reported CPU credits.** Before the run starts and after it ends, the harness pauses and
   asks the operator for the Azure portal value of the metric "CPU Credits Remaining"
   (`cpu_credits_remaining`; Monitoring > Metrics). The answer and the data-point time are stored
   verbatim with `"source": "user-reported from Azure portal"`
   (`cpu_credits_user_reported`). The harness doesn't verify, parse or infer these values. Microsoft
   documents that this metric can be displayed up to five minutes late, so a value may not reflect
   the exact moment of entry.
