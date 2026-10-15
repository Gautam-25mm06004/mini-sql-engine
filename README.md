# Mini SQL Engine — Parser, Optimiser and Executor, Differentially Tested Against SQLite

A small relational query engine written from scratch in Python (standard library only):

- **Lexer + recursive-descent parser** for `SELECT [DISTINCT] … FROM … [INNER|LEFT] JOIN … ON … WHERE … GROUP BY … HAVING …
  ORDER BY … LIMIT`, arithmetic, comparisons, `AND/OR/NOT`, `IS [NOT] NULL`, `COUNT/SUM/AVG/MIN/MAX [DISTINCT]`, plus
  `CREATE TABLE` and `INSERT`.
- **Rule-based optimiser**: splits `WHERE` into conjuncts and pushes single-table predicates down to scans (never below the
  nullable side of a `LEFT JOIN`); turns equality join conditions into **hash joins**, otherwise nested loops.
- **Iterator (Volcano) executor** with SQL three-valued logic, NULL-aware grouping and ordering, and SQLite-compatible integer
  division; `explain()` prints the physical plan.

## Correctness: differential testing
A random query generator builds joins (inner/left, 2–3 tables), nested predicates with NULLs, arithmetic, `GROUP BY`/`HAVING`
and `DISTINCT`. Each query runs on this engine and on SQLite over the same random data, and results are compared as multisets.

**6,000 random queries over 25 random databases: 0 mismatches** (2,375 with GROUP BY, 2,569 with LEFT JOIN,
1,693 three-way joins). The unit tests run another 1,200 queries, with the optimiser both on and off.

## Performance: what each optimisation buys (20,000 orders × 2,000 customers)

| Configuration | Join + selective filters | Join, no filter | LEFT JOIN anti-join |
|---|---|---|---|
| No optimisation (nested loop, filter on top) | 14.36 s | 14.78 s | 15.38 s |
| Predicate pushdown only | 0.77 s | 15.20 s | 15.11 s |
| Hash join only | 0.026 s | 0.021 s | 0.022 s |
| **Pushdown + hash join** | **0.010 s** | 0.022 s | 0.026 s |
| SQLite (C, reference) | 0.002 s | 0.006 s | 0.001 s |

Hash joins turn an O(n·m) join into O(n + m) — a ~700× speed-up here; pushdown shrinks join inputs and gives a further 2.6×
on selective queries.

```
Aggregate keys=[c.country] aggs=[COUNT(*), SUM(o.amount)]
  HashJoin INNER ON o.cid = c.id
    Scan orders AS o WHERE (o.year = 2026)
    Scan customers AS c WHERE (c.age > 70)
```

## Run
```bash
python -m unittest discover -s tests -v
python scripts/run_experiments.py       # ~80 s, mostly the unoptimised nested loops
```
```python
from minisql import Database
db = Database()
db.execute("CREATE TABLE t (a INT, b TEXT)")
db.execute("INSERT INTO t VALUES (1, 'x'), (2, NULL)")
print(db.execute("SELECT b, COUNT(*) FROM t GROUP BY b"))
```
