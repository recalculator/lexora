# Precedent retrieval diagnostic (local)

100 eval clauses (seed 42), top 3 precedents per app clause type, app retriever and category map. 'Fix off' = filtered queries may use HNSW with a WHERE clause (pre-fix behaviour); 'fix on' = exact search over the categories GIN index.

| App clause type | Filtered | Matching rows | Fix off: mean / short | Fix on: mean / short |
|---|---|---|---|---|
| Termination | yes | 622 | 1.18 / 74 | 3.00 / 0 |
| Indemnification | no (unmapped) | 6766 | 3.00 / 0 | 3.00 / 0 |
| Liability Cap | yes | 555 | 0.98 / 78 | 3.00 / 0 |
| Confidentiality | no (unmapped) | 6766 | 3.00 / 0 | 3.00 / 0 |
| Insurance | yes | 425 | 0.49 / 90 | 3.00 / 0 |
| Intellectual Property | yes | 931 | 1.18 / 67 | 3.00 / 0 |
| Assignment | yes | 713 | 1.48 / 58 | 3.00 / 0 |
| Governing Law | yes | 373 | 0.20 / 96 | 3.00 / 0 |

Session settings: fix off {'hnsw.ef_search': '40', 'hnsw.iterative_scan': 'off'}, fix on {'hnsw.ef_search': '40', 'hnsw.iterative_scan': 'off'}.
