import re

KEYWORDS = {"SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "JOIN", "INNER", "LEFT", "ON", "GROUP", "BY", "HAVING",
            "ORDER", "ASC", "DESC", "LIMIT", "AS", "CREATE", "TABLE", "INSERT", "INTO", "VALUES", "NULL", "IS",
            "COUNT", "SUM", "AVG", "MIN", "MAX", "INT", "INTEGER", "REAL", "TEXT", "DISTINCT"}
TOKEN = re.compile(r"\s*(?:(?P<num>\d+\.\d*|\d+)|(?P<str>'(?:[^']|'')*')|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
                   r"|(?P<op><=|>=|<>|!=|[=<>+\-*/(),.;]))")


class Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind, value):
        self.kind, self.value = kind, value

    def __repr__(self):
        return f"{self.kind}:{self.value}"


def tokenize(sql):
    pos, out = 0, []
    sql = sql.rstrip()
    while pos < len(sql):
        m = TOKEN.match(sql, pos)
        if not m or m.end() == pos:
            raise SyntaxError(f"unexpected character at {pos}: {sql[pos:pos + 10]!r}")
        pos = m.end()
        if m.group("num"):
            v = m.group("num")
            out.append(Token("num", float(v) if "." in v else int(v)))
        elif m.group("str"):
            out.append(Token("str", m.group("str")[1:-1].replace("''", "'")))
        elif m.group("name"):
            up = m.group("name").upper()
            out.append(Token("kw", up) if up in KEYWORDS else Token("name", m.group("name").lower()))
        else:
            out.append(Token("op", m.group("op")))
    out.append(Token("eof", None))
    return out
