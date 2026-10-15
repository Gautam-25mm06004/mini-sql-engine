"""Planner, rule-based optimiser and Volcano-style (iterator) executor."""
import functools
from . import ast as A
from .exprs import Schema, compile_expr, columns_of, aggs_of, conjuncts
from .parser import parse


# ----------------------------------------------------------------------------------------------- physical operators
class Scan:
    def __init__(self, table, alias, rows, cols, preds=()):
        self.table, self.alias, self.rows = table, alias, rows
        self.schema = Schema([(alias, c) for c in cols])
        self.preds = list(preds)
        self._f = [compile_expr(p, self.schema) for p in self.preds]

    def __iter__(self):
        f = self._f
        for r in self.rows:
            if all(g(r) is True for g in f):
                yield r

    def explain(self, d=0):
        w = f" WHERE {' AND '.join(map(show, self.preds))}" if self.preds else ""
        return "  " * d + f"Scan {self.table} AS {self.alias}{w}\n"


class Filter:
    def __init__(self, child, preds):
        self.child, self.preds, self.schema = child, preds, child.schema
        self._f = [compile_expr(p, self.schema) for p in preds]

    def __iter__(self):
        f = self._f
        for r in self.child:
            if all(g(r) is True for g in f):
                yield r

    def explain(self, d=0):
        return "  " * d + f"Filter {' AND '.join(map(show, self.preds))}\n" + self.child.explain(d + 1)


class HashJoin:
    """Equi-join: build a hash table on the right input, probe with the left. Supports LEFT OUTER."""
    def __init__(self, left, right, lkeys, rkeys, residual, kind):
        self.left, self.right, self.kind = left, right, kind
        self.schema = left.schema + right.schema
        self.lk = [compile_expr(k, left.schema) for k in lkeys]
        self.rk = [compile_expr(k, right.schema) for k in rkeys]
        self.lkeys, self.rkeys, self.residual = lkeys, rkeys, residual
        self._res = [compile_expr(p, self.schema) for p in residual]
        self.nr = len(right.schema.cols)

    def __iter__(self):
        table = {}
        for r in self.right:
            key = tuple(f(r) for f in self.rk)
            if None not in key:
                table.setdefault(key, []).append(r)
        pad = (None,) * self.nr
        for l in self.left:
            key = tuple(f(l) for f in self.lk)
            matched = False
            if None not in key:
                for r in table.get(key, ()):
                    row = l + r
                    if all(g(row) is True for g in self._res):
                        matched = True
                        yield row
            if not matched and self.kind == "LEFT":
                yield l + pad

    def explain(self, d=0):
        cond = " AND ".join(f"{show(a)} = {show(b)}" for a, b in zip(self.lkeys, self.rkeys))
        extra = f" (+ {' AND '.join(map(show, self.residual))})" if self.residual else ""
        return "  " * d + f"HashJoin {self.kind} ON {cond}{extra}\n" + self.left.explain(d + 1) + self.right.explain(d + 1)


class NestedLoopJoin:
    def __init__(self, left, right, on, kind):
        self.left, self.right, self.kind, self.on = left, right, kind, on
        self.schema = left.schema + right.schema
        self._on = [compile_expr(p, self.schema) for p in on]
        self.nr = len(right.schema.cols)

    def __iter__(self):
        right = list(self.right)
        pad = (None,) * self.nr
        for l in self.left:
            matched = False
            for r in right:
                row = l + r
                if all(g(row) is True for g in self._on):
                    matched = True
                    yield row
            if not matched and self.kind == "LEFT":
                yield l + pad

    def explain(self, d=0):
        return "  " * d + f"NestedLoopJoin {self.kind} ON {' AND '.join(map(show, self.on)) or 'TRUE'}\n" + self.left.explain(d + 1) + self.right.explain(d + 1)


class Aggregate:
    def __init__(self, child, keys, aggs):
        self.child, self.keys, self.aggs = child, keys, aggs
        self._k = [compile_expr(k, child.schema) for k in keys]
        self._a = [compile_expr(a.arg, child.schema) if a.arg is not None else None for a in aggs]
        # output row = group keys + one value per aggregate; key expressions keep their identity for later lookup
        self.schema = Schema([("#key", show(k)) for k in keys] + [("#agg", show(a)) for a in aggs])

    def __iter__(self):
        groups = {}
        for r in self.child:
            key = tuple(f(r) for f in self._k)
            st = groups.get(key)
            if st is None:
                st = groups[key] = [[] for _ in self.aggs]
            for j, f in enumerate(self._a):
                st[j].append(1 if f is None else f(r))
        if not groups and not self.keys:                    # aggregate over empty input: one row
            groups[()] = [[] for _ in self.aggs]
        for key, st in groups.items():
            yield key + tuple(finish(a, vals) for a, vals in zip(self.aggs, st))

    def explain(self, d=0):
        return "  " * d + f"Aggregate keys=[{', '.join(map(show, self.keys))}] aggs=[{', '.join(map(show, self.aggs))}]\n" + self.child.explain(d + 1)


def finish(a, vals):
    if a.func == "COUNT" and a.arg is None:
        return len(vals)
    vals = [v for v in vals if v is not None]
    if a.distinct:
        vals = list(dict.fromkeys(vals))
    if a.func == "COUNT":
        return len(vals)
    if not vals:
        return None
    if a.func == "SUM":
        return sum(vals)
    if a.func == "AVG":
        return sum(vals) / len(vals)
    return min(vals) if a.func == "MIN" else max(vals)


def show(e):
    if isinstance(e, A.Col):
        return f"{e.table}.{e.name}" if e.table else e.name
    if isinstance(e, A.Lit):
        return "NULL" if e.value is None else repr(e.value)
    if isinstance(e, A.BinOp):
        return f"({show(e.left)} {e.op} {show(e.right)})"
    if isinstance(e, A.Not):
        return f"NOT {show(e.expr)}"
    if isinstance(e, A.IsNull):
        return f"{show(e.expr)} IS {'NOT ' if e.negate else ''}NULL"
    if isinstance(e, A.Agg):
        return f"{e.func}({'DISTINCT ' if e.distinct else ''}{'*' if e.arg is None else show(e.arg)})"
    return str(e)


def sql_sort_key(v):
    """SQLite ordering: NULL < numbers < text."""
    if v is None:
        return (0, 0)
    if isinstance(v, (int, float)):
        return (1, v)
    return (2, v)


# ----------------------------------------------------------------------------------------------------- database
class Database:
    def __init__(self, pushdown=True, hash_join=True):
        self.tables = {}                 # name -> (columns, rows)
        self.pushdown, self.hash_join = pushdown, hash_join

    def execute(self, sql):
        st = parse(sql)
        if isinstance(st, A.CreateTable):
            self.tables[st.name] = (st.columns, [])
            return [], []
        if isinstance(st, A.Insert):
            cols, rows = self.tables[st.table]
            for r in st.rows:
                if len(r) != len(cols):
                    raise ValueError("column count mismatch")
                rows.append(tuple(r))
            return [], []
        plan, names, post = self.plan(st)
        return names, post(plan)

    def explain(self, sql):
        plan, _, _ = self.plan(parse(sql))
        return plan.explain()

    # ---- planning ----
    def plan(self, s: A.Select):
        refs = [s.base] + [j.table for j in s.joins]
        scans = {}
        for t in refs:
            cols, rows = self.tables[t.name]
            scans[t.alias] = (t, cols, rows)
        schemas = {a: Schema([(a, c) for c in cols]) for a, (_, cols, _) in scans.items()}
        where = conjuncts(s.where)
        # tables on the nullable side of a LEFT JOIN must not receive WHERE predicates (would change semantics)
        nullable = {j.table.alias for j in s.joins if j.kind == "LEFT"}
        pushed = {a: [] for a in scans}
        remaining = []
        for p in where:
            owners = {a for a in scans if all(schemas[a].has(c) for c in columns_of(p))} if columns_of(p) else set()
            if self.pushdown and len(owners) == 1 and not aggs_of(p) and next(iter(owners)) not in nullable:
                pushed[next(iter(owners))].append(p)
            else:
                remaining.append(p)

        def scan(alias):
            t, cols, rows = scans[alias]
            return Scan(t.name, alias, rows, cols, pushed[alias])

        node = scan(s.base.alias)
        for j in s.joins:
            right = scan(j.table.alias)
            on = conjuncts(j.on)
            lk, rk, residual = [], [], []
            for p in on:
                if isinstance(p, A.BinOp) and p.op == "=" and isinstance(p.left, A.Col) and isinstance(p.right, A.Col):
                    if node.schema.has(p.left) and right.schema.has(p.right):
                        lk.append(p.left); rk.append(p.right); continue
                    if node.schema.has(p.right) and right.schema.has(p.left):
                        lk.append(p.right); rk.append(p.left); continue
                residual.append(p)
            if self.hash_join and lk:
                node = HashJoin(node, right, lk, rk, residual, j.kind)
            else:
                node = NestedLoopJoin(node, right, on, j.kind)
        if remaining:
            node = Filter(node, remaining)

        # ---- aggregation ----
        items = []
        for it in s.items:
            if isinstance(it.expr, A.Star):
                items += [A.SelectItem(A.Col(t, c), None) for t, c in node.schema.cols]
            else:
                items.append(it)
        all_aggs = []
        for e in [it.expr for it in items] + ([s.having] if s.having is not None else []) + [e for e, _ in s.order_by]:
            for a in aggs_of(e):
                if a not in all_aggs:
                    all_aggs.append(a)
        alias_map = {it.alias: it.expr for it in items if it.alias}
        if all_aggs or s.group_by:
            agg = Aggregate(node, s.group_by, all_aggs)
            slots = {a: len(s.group_by) + i for i, a in enumerate(all_aggs)}
            key_schema = Schema([(c.table if isinstance(c, A.Col) else "#", c.name if isinstance(c, A.Col) else f"#k{i}")
                                 for i, c in enumerate(s.group_by)] + [("#agg", f"a{i}") for i in range(len(all_aggs))])
            def comp(e):
                return compile_expr(alias_map.get(e.name, e) if isinstance(e, A.Col) and e.table is None and e.name in alias_map
                                    and not key_schema.has(e) else e, key_schema, slots)
            node = agg
            if s.having is not None:
                hv = comp(s.having)
                node = _FilterFn(node, hv, "Having " + show(s.having))
            out_f = [comp(it.expr) for it in items]
            order_f = [(comp(e), d) for e, d in s.order_by]
        else:
            def comp(e):
                if isinstance(e, A.Col) and e.table is None and e.name in alias_map and not node.schema.has(e):
                    e = alias_map[e.name]
                return compile_expr(e, node.schema)
            out_f = [comp(it.expr) for it in items]
            order_f = [(comp(e), d) for e, d in s.order_by]
        names = [it.alias or show(it.expr) for it in items]

        def post(plan):
            rows = [(tuple(f(r) for f in out_f), tuple(g(r) for g, _ in order_f)) for r in plan]
            if s.distinct:
                seen, uniq = set(), []
                for r in rows:
                    if r[0] not in seen:
                        seen.add(r[0]); uniq.append(r)
                rows = uniq
            if order_f:
                def cmp(a, b):
                    for (x, y), (_, desc) in zip(zip(a[1], b[1]), order_f):
                        kx, ky = sql_sort_key(x), sql_sort_key(y)
                        if kx != ky:
                            return (-1 if kx < ky else 1) * (-1 if desc else 1)
                    return 0
                rows.sort(key=functools.cmp_to_key(cmp))
            out = [r[0] for r in rows]
            return out[: s.limit] if s.limit is not None else out
        return node, names, post


class _FilterFn:
    def __init__(self, child, f, label):
        self.child, self.f, self.label, self.schema = child, f, label, child.schema

    def __iter__(self):
        for r in self.child:
            if self.f(r) is True:
                yield r

    def explain(self, d=0):
        return "  " * d + self.label + "\n" + self.child.explain(d + 1)
