# Interview guide — Mini SQL engine

## 30-second version
"I wrote a SQL engine from scratch: a lexer and recursive-descent parser, a planner with predicate pushdown and hash joins,
and an iterator-model executor with proper NULL semantics. To prove it's correct I generated 6,000 random queries — joins,
left joins, nested predicates with NULLs, group by — and compared results with SQLite: zero mismatches. Hash joins made the
join workload about 700× faster than nested loops."

## Must-know
- **Parsing**: tokens → AST; precedence handled by one function per level (OR < AND < NOT < comparison < +,- < *,/).
- **Volcano model**: each operator is an iterator that pulls rows from its child; easy to compose, one row at a time.
- **Hash join**: build a hash table on one side keyed by the join column, probe with the other → O(n + m). NULL keys never match.
- **Predicate pushdown**: filter early so joins see fewer rows. *Not* below the nullable side of a LEFT JOIN.
- **Three-valued logic**: TRUE / FALSE / UNKNOWN (NULL). `NULL = NULL` is UNKNOWN; WHERE keeps only TRUE.
- **Differential testing**: same input to your system and a trusted one; any difference is a bug in one of them.

## Likely questions
1. *Why can't you push `WHERE right.x IS NULL` below a LEFT JOIN?* Before the join, the right table has no padded NULL rows,
   so the filter would remove everything and the anti-join would return wrong results.
2. *What would a cost-based optimiser add?* Join ordering using cardinality estimates, choice of build side, index use.
3. *How does COUNT(*) differ from COUNT(col)?* COUNT(*) counts rows, COUNT(col) skips NULLs — matters after LEFT JOINs.
4. *Why compare results as multisets?* SQL doesn't define row order without ORDER BY.
5. *What bugs did differential testing protect against?* Integer division, NULLs in join keys, empty aggregates, outer-join
   padding — all checked automatically.
