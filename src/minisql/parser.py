"""Recursive-descent parser. Precedence (low -> high): OR, AND, NOT, comparison / IS NULL, + -, * /, unary -, primary."""
from .lexer import tokenize
from . import ast as A

AGGS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
CMP = {"=", "<>", "!=", "<", ">", "<=", ">="}


class Parser:
    def __init__(self, sql):
        self.t, self.i = tokenize(sql), 0

    # ---- helpers ----
    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]; self.i += 1; return tok

    def accept(self, kind, value=None):
        tok = self.peek()
        if tok.kind == kind and (value is None or tok.value == value):
            self.i += 1
            return tok
        return None

    def expect(self, kind, value=None):
        tok = self.accept(kind, value)
        if not tok:
            raise SyntaxError(f"expected {value or kind}, got {self.peek().value!r}")
        return tok

    # ---- statements ----
    def statement(self):
        if self.accept("kw", "SELECT"):
            s = self.select()
        elif self.accept("kw", "CREATE"):
            self.expect("kw", "TABLE")
            name = self.expect("name").value
            self.expect("op", "(")
            cols = []
            while True:
                cols.append(self.expect("name").value)
                while self.peek().kind in ("kw", "name") and self.peek().value not in (",", ")"):
                    self.next()                      # ignore type names
                if not self.accept("op", ","):
                    break
            self.expect("op", ")")
            s = A.CreateTable(name, cols)
        elif self.accept("kw", "INSERT"):
            self.expect("kw", "INTO")
            name = self.expect("name").value
            self.expect("kw", "VALUES")
            rows = []
            while True:
                self.expect("op", "(")
                row = [self.literal_value()]
                while self.accept("op", ","):
                    row.append(self.literal_value())
                self.expect("op", ")")
                rows.append(row)
                if not self.accept("op", ","):
                    break
            s = A.Insert(name, rows)
        else:
            raise SyntaxError(f"unsupported statement starting with {self.peek().value!r}")
        self.accept("op", ";")
        self.expect("eof")
        return s

    def literal_value(self):
        neg = self.accept("op", "-")
        tok = self.next()
        if tok.kind == "kw" and tok.value == "NULL":
            return None
        if tok.kind == "num":
            return -tok.value if neg else tok.value
        if tok.kind == "str":
            return tok.value
        raise SyntaxError(f"bad literal {tok.value!r}")

    def table_ref(self):
        name = self.expect("name").value
        self.accept("kw", "AS")
        alias = self.accept("name")
        return A.TableRef(name, alias.value if alias else name)

    def select(self):
        distinct = bool(self.accept("kw", "DISTINCT"))
        items = [self.select_item()]
        while self.accept("op", ","):
            items.append(self.select_item())
        self.expect("kw", "FROM")
        s = A.Select(items, self.table_ref(), distinct=distinct)
        while True:
            if self.accept("kw", "LEFT"):
                kind = "LEFT"; self.expect("kw", "JOIN")
            elif self.accept("kw", "INNER"):
                kind = "INNER"; self.expect("kw", "JOIN")
            elif self.accept("kw", "JOIN"):
                kind = "INNER"
            else:
                break
            tref = self.table_ref()
            self.expect("kw", "ON")
            s.joins.append(A.Join(kind, tref, self.expr()))
        if self.accept("kw", "WHERE"):
            s.where = self.expr()
        if self.accept("kw", "GROUP"):
            self.expect("kw", "BY")
            s.group_by = [self.expr()]
            while self.accept("op", ","):
                s.group_by.append(self.expr())
        if self.accept("kw", "HAVING"):
            s.having = self.expr()
        if self.accept("kw", "ORDER"):
            self.expect("kw", "BY")
            while True:
                e = self.expr()
                desc = bool(self.accept("kw", "DESC"))
                if not desc:
                    self.accept("kw", "ASC")
                s.order_by.append((e, desc))
                if not self.accept("op", ","):
                    break
        if self.accept("kw", "LIMIT"):
            s.limit = self.expect("num").value
        return s

    def select_item(self):
        if self.accept("op", "*"):
            return A.SelectItem(A.Star(), None)
        e = self.expr()
        alias = None
        if self.accept("kw", "AS"):
            alias = self.expect("name").value
        elif self.peek().kind == "name":
            alias = self.next().value
        return A.SelectItem(e, alias)

    # ---- expressions ----
    def expr(self):
        e = self.and_()
        while self.accept("kw", "OR"):
            e = A.BinOp("OR", e, self.and_())
        return e

    def and_(self):
        e = self.not_()
        while self.accept("kw", "AND"):
            e = A.BinOp("AND", e, self.not_())
        return e

    def not_(self):
        if self.accept("kw", "NOT"):
            return A.Not(self.not_())
        return self.cmp()

    def cmp(self):
        e = self.add()
        if self.peek().kind == "op" and self.peek().value in CMP:
            op = self.next().value
            return A.BinOp("<>" if op == "!=" else op, e, self.add())
        if self.accept("kw", "IS"):
            neg = bool(self.accept("kw", "NOT"))
            self.expect("kw", "NULL")
            return A.IsNull(e, neg)
        return e

    def add(self):
        e = self.mul()
        while self.peek().kind == "op" and self.peek().value in "+-":
            op = self.next().value
            e = A.BinOp(op, e, self.mul())
        return e

    def mul(self):
        e = self.unary()
        while self.peek().kind == "op" and self.peek().value in "*/":
            op = self.next().value
            e = A.BinOp(op, e, self.unary())
        return e

    def unary(self):
        if self.accept("op", "-"):
            return A.BinOp("-", A.Lit(0), self.unary())
        return self.primary()

    def primary(self):
        tok = self.peek()
        if tok.kind == "num" or tok.kind == "str":
            self.next(); return A.Lit(tok.value)
        if tok.kind == "kw" and tok.value == "NULL":
            self.next(); return A.Lit(None)
        if tok.kind == "kw" and tok.value in AGGS:
            self.next(); self.expect("op", "(")
            if tok.value == "COUNT" and self.accept("op", "*"):
                self.expect("op", ")"); return A.Agg("COUNT", None)
            distinct = bool(self.accept("kw", "DISTINCT"))
            arg = self.expr(); self.expect("op", ")")
            return A.Agg(tok.value, arg, distinct)
        if self.accept("op", "("):
            e = self.expr(); self.expect("op", ")"); return e
        if tok.kind == "name":
            self.next()
            if self.accept("op", "."):
                return A.Col(tok.value, self.expect("name").value)
            return A.Col(None, tok.value)
        raise SyntaxError(f"unexpected token {tok.value!r}")


def parse(sql):
    return Parser(sql).statement()
