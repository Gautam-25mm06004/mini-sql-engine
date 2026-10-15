# A Differentially Tested SQL Engine: Design and Optimiser Ablation

**Gautam Jain** — IIT Bhubaneswar

## 1. Architecture
SQL text → tokens (regular-expression lexer) → AST (recursive descent with explicit precedence levels) → logical decisions in
the planner → tree of physical operators (Scan, Filter, HashJoin, NestedLoopJoin, Aggregate, Having) → rows pulled through
Python generators (the iterator / Volcano model, Graefe 1994). Expressions are compiled once into closures over row tuples,
using a schema of (table alias, column) pairs to resolve names and detect ambiguity.

## 2. Semantics
- **NULLs**: comparisons and arithmetic with NULL yield NULL; AND/OR follow Kleene three-valued logic; WHERE, ON and HAVING keep
  rows only when the condition is TRUE; aggregates ignore NULLs, COUNT(*) does not; an aggregate over empty input returns one
  row; NULL sorts first, as in SQLite.
- **Arithmetic**: integer division truncates toward zero; division by zero returns NULL (SQLite behaviour).
- **Outer joins**: unmatched left rows are padded with NULLs; ON-clause conditions are applied before padding.

## 3. Optimiser
1. **Predicate pushdown**: WHERE conjuncts that reference exactly one table are moved into that table's scan — except for
   tables on the nullable side of a LEFT JOIN, where pushing `q.v IS NULL` below the join would change the result
   (an anti-join becomes a no-op). A unit test checks this case.
2. **Join algorithm selection**: `col = col` conditions across the two inputs become hash-join keys (build on the right input,
   probe with the left); other ON conditions become residual predicates. Without an equality key, a nested-loop join is used.

## 4. Testing methodology
Differential testing (McKeeman 1998) uses SQLite as an oracle. The generator draws random tables with 10% NULLs and random
queries over them; results are compared as multisets (order is unspecified without ORDER BY), with floats rounded to 9
decimals. 6,000 queries produced no mismatch. Hand-written tests cover NULL logic, empty aggregates, division, ORDER BY with
NULLs and LIMIT, syntax errors, and the shape of optimised plans.

## 5. Results
See README. The nested-loop join over 20k × 2k rows takes ~15 s in Python; hash joins bring every query under 30 ms, and pushdown
reduces the selective query further to 10 ms. SQLite remains 4–26× faster thanks to its C implementation.

## 6. Limitations
No indexes, subqueries, window functions, transactions or cost-based join ordering; joins are planned left-deep in the written
order; all data lives in memory.

## References
1. G. Graefe. Volcano — an extensible and parallel query evaluation system. *IEEE TKDE* 6(1), 120–135, 1994.
2. P. Selinger et al. Access path selection in a relational database management system. *SIGMOD* 1979.
3. W. McKeeman. Differential testing for software. *Digital Technical Journal* 10(1), 100–107, 1998.
4. M. Rigger, Z. Su. Testing database engines via pivoted query synthesis. *OSDI* 2020.
