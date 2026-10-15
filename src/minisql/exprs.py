"""Compile AST expressions into Python closures over a row tuple, with SQL three-valued logic and SQLite-compatible
arithmetic (integer division truncates toward zero, division by zero gives NULL)."""
from . import ast as A


class Schema:
    """Ordered list of (table_alias, column) for the tuples flowing through an operator."""
    def __init__(self, cols):
        self.cols = list(cols)

    def index(self, c: A.Col):
        hits = [i for i, (t, n) in enumerate(self.cols) if n == c.name and (c.table is None or c.table == t)]
        if not hits:
            raise KeyError(f"unknown column {c.table + '.' if c.table else ''}{c.name}")
        if len(hits) > 1:
            raise KeyError(f"ambiguous column {c.name}")
        return hits[0]

    def has(self, c: A.Col):
        try:
            self.index(c); return True
        except KeyError:
            return False

    def __add__(self, other):
        return Schema(self.cols + other.cols)


def _div(a, b):
    if b == 0:
        return None
    if isinstance(a, int) and isinstance(b, int):
        q = abs(a) // abs(b)
        return q if (a >= 0) == (b >= 0) else -q
    return a / b


ARITH = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b, "/": _div}
CMPS = {"=": lambda a, b: a == b, "<>": lambda a, b: a != b, "<": lambda a, b: a < b, ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}


def compile_expr(e, schema: Schema, agg_slots=None):
    """agg_slots: dict Agg-node -> position in the row (used after aggregation)."""
    if agg_slots is not None and isinstance(e, A.Agg):
        i = agg_slots[e]
        return lambda r: r[i]
    if isinstance(e, A.Lit):
        v = e.value
        return lambda r: v
    if isinstance(e, A.Col):
        i = schema.index(e)
        return lambda r: r[i]
    if isinstance(e, A.Not):
        f = compile_expr(e.expr, schema, agg_slots)
        def neg(r):
            v = f(r)
            return None if v is None else (not v)
        return neg
    if isinstance(e, A.IsNull):
        f = compile_expr(e.expr, schema, agg_slots)
        return (lambda r: f(r) is not None) if e.negate else (lambda r: f(r) is None)
    if isinstance(e, A.BinOp):
        L, R = compile_expr(e.left, schema, agg_slots), compile_expr(e.right, schema, agg_slots)
        if e.op == "AND":
            def and_(r):
                a = L(r)
                if a is False:
                    return False
                b = R(r)
                if b is False:
                    return False
                return None if a is None or b is None else True
            return and_
        if e.op == "OR":
            def or_(r):
                a = L(r)
                if a is True:
                    return True
                b = R(r)
                if b is True:
                    return True
                return None if a is None or b is None else False
            return or_
        fn = ARITH.get(e.op) or CMPS[e.op]
        def binop(r):
            a, b = L(r), R(r)
            return None if a is None or b is None else fn(a, b)
        return binop
    if isinstance(e, A.Agg):
        raise ValueError("aggregate used outside an aggregate context")
    raise TypeError(e)


def columns_of(e):
    """All Col references in an expression."""
    if isinstance(e, A.Col):
        return {e}
    if isinstance(e, A.BinOp):
        return columns_of(e.left) | columns_of(e.right)
    if isinstance(e, (A.Not, A.IsNull)):
        return columns_of(e.expr)
    if isinstance(e, A.Agg):
        return columns_of(e.arg) if e.arg is not None else set()
    return set()


def aggs_of(e):
    if isinstance(e, A.Agg):
        return [e]
    if isinstance(e, A.BinOp):
        return aggs_of(e.left) + aggs_of(e.right)
    if isinstance(e, (A.Not, A.IsNull)):
        return aggs_of(e.expr)
    return []


def conjuncts(e):
    if isinstance(e, A.BinOp) and e.op == "AND":
        return conjuncts(e.left) + conjuncts(e.right)
    return [e] if e is not None else []
