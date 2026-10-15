# Results

## Differential testing vs SQLite

6000 random queries over 25 random databases (with NULLs): **0 mismatches**; 5090 had non-empty results. Features exercised: {'GROUP BY': 2375, 'LEFT JOIN': 2569, '3-way join': 1693, 'DISTINCT': 523}. (2.2 s)

## Optimiser ablation (20,000 orders x 2,000 customers)

| configuration | join + selective filters (s) | join, no filter (s) | left join anti-pattern (s) |
|---|---|---|---|
| no optimisation (nested loop, filter on top) | 14.358 | 14.776 | 15.384 |
| predicate pushdown only | 0.771 | 15.198 | 15.114 |
| hash join only | 0.026 | 0.021 | 0.022 |
| pushdown + hash join | 0.01 | 0.022 | 0.026 |
| SQLite (reference, no indexes) | 0.002 | 0.006 | 0.001 |

## Example plan

```
Aggregate keys=[c.country] aggs=[COUNT(*), SUM(o.amount)]
  HashJoin INNER ON o.cid = c.id
    Scan orders AS o WHERE (o.year = 2026)
    Scan customers AS c WHERE (c.age > 70)
```
