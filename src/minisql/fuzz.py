"""Random query generator for differential testing against SQLite."""
import random

TABLES = {"t1": ["a", "b", "c"], "t2": ["a", "d", "e"], "t3": ["d", "f"]}


def make_data(rng, n=(30, 40, 20)):
    data = {}
    for (name, cols), size in zip(TABLES.items(), n):
        rows = []
        for _ in range(size):
            rows.append(tuple(None if rng.random() < 0.1 else rng.randint(-5, 9) for _ in cols))
        data[name] = rows
    return data


def _col(rng, aliases):
    t = rng.choice(aliases)
    return f"{t}.{rng.choice(TABLES[t])}"


def _scalar(rng, aliases, depth=0):
    r = rng.random()
    if depth > 1 or r < 0.45:
        return _col(rng, aliases)
    if r < 0.6:
        return str(rng.randint(-3, 6))
    op = rng.choice(["+", "-", "*", "/"])
    return f"({_scalar(rng, aliases, depth + 1)} {op} {_scalar(rng, aliases, depth + 1)})"


def _pred(rng, aliases, depth=0):
    r = rng.random()
    if depth < 2 and r < 0.25:
        return f"({_pred(rng, aliases, depth + 1)} {rng.choice(['AND', 'OR'])} {_pred(rng, aliases, depth + 1)})"
    if depth < 2 and r < 0.32:
        return f"NOT ({_pred(rng, aliases, depth + 1)})"
    if r < 0.42:
        return f"{_col(rng, aliases)} IS {'NOT ' if rng.random() < 0.5 else ''}NULL"
    return f"{_scalar(rng, aliases)} {rng.choice(['=', '<>', '<', '>', '<=', '>='])} {_scalar(rng, aliases)}"


def random_query(rng):
    aliases = ["t1"]
    frm = "t1"
    if rng.random() < 0.7:
        kind = rng.choice(["JOIN", "LEFT JOIN"])
        on = "t1.a = t2.a" + (f" AND {_pred(rng, ['t1', 't2'])}" if rng.random() < 0.3 else "")
        frm += f" {kind} t2 ON {on}"
        aliases.append("t2")
        if rng.random() < 0.4:
            kind = rng.choice(["JOIN", "LEFT JOIN"])
            frm += f" {kind} t3 ON t2.d = t3.d"
            aliases.append("t3")
    where = f" WHERE {_pred(rng, aliases)}" if rng.random() < 0.8 else ""
    if rng.random() < 0.4:
        g = _col(rng, aliases)
        aggs = [f"{rng.choice(['COUNT', 'SUM', 'MIN', 'MAX'])}({_col(rng, aliases)})", "COUNT(*)"]
        having = f" HAVING COUNT(*) > {rng.randint(0, 3)}" if rng.random() < 0.4 else ""
        return f"SELECT {g}, {', '.join(aggs)} FROM {frm}{where} GROUP BY {g}{having}"
    items = ", ".join(_scalar(rng, aliases) for _ in range(rng.randint(1, 3)))
    distinct = "DISTINCT " if rng.random() < 0.15 else ""
    return f"SELECT {distinct}{items} FROM {frm}{where}"
