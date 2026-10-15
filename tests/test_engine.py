import random, sqlite3, sys, unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from minisql import Database, parse  # noqa
from minisql.fuzz import TABLES, make_data, random_query  # noqa


def norm(rows):
    return Counter(tuple(round(v, 9) if isinstance(v, float) else v for v in r) for r in rows)


def load(data, pushdown=True, hash_join=True):
    db = Database(pushdown, hash_join)
    con = sqlite3.connect(":memory:")
    for t, cols in TABLES.items():
        db.execute(f"CREATE TABLE {t} ({', '.join(c + ' INT' for c in cols)})")
        con.execute(f"CREATE TABLE {t} ({', '.join(c + ' INT' for c in cols)})")
        db.tables[t][1].extend(data[t])
        con.executemany(f"INSERT INTO {t} VALUES ({','.join('?' * len(cols))})", data[t])
    return db, con


class TestBasics(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.db.execute("CREATE TABLE p (id INT, name TEXT, age INT)")
        self.db.execute("INSERT INTO p VALUES (1, 'ann', 30), (2, 'bob', NULL), (3, 'cy', 25), (4, 'di''s', 30)")

    def test_null_three_valued_logic(self):
        _, rows = self.db.execute("SELECT name FROM p WHERE age > 26 OR age < 26")
        self.assertEqual(sorted(r[0] for r in rows), ["ann", "cy", "di's"])        # NULL row excluded
        _, rows = self.db.execute("SELECT name FROM p WHERE NOT (age = 30)")
        self.assertEqual([r[0] for r in rows], ["cy"])

    def test_group_order_limit(self):
        _, rows = self.db.execute("SELECT age, COUNT(*) AS n FROM p GROUP BY age ORDER BY n DESC, age LIMIT 2")
        self.assertEqual(rows, [(30, 2), (None, 1)])

    def test_aggregate_empty_input(self):
        _, rows = self.db.execute("SELECT COUNT(*), SUM(age), MAX(age) FROM p WHERE id > 99")
        self.assertEqual(rows, [(0, None, None)])

    def test_integer_division_like_sqlite(self):
        _, rows = self.db.execute("SELECT 7 / 2, -7 / 2, 7 / 0 FROM p LIMIT 1")
        self.assertEqual(rows, [(3, -3, None)])

    def test_syntax_error(self):
        with self.assertRaises(SyntaxError):
            parse("SELECT FROM p")

    def test_pushdown_plan(self):
        self.db.execute("CREATE TABLE q (pid INT, v INT)")
        plan = self.db.explain("SELECT p.name FROM p JOIN q ON p.id = q.pid WHERE q.v > 3 AND p.age = 30")
        self.assertIn("HashJoin", plan)
        self.assertIn("Scan q AS q WHERE (q.v > 3)", plan)
        plan = self.db.explain("SELECT p.name FROM p LEFT JOIN q ON p.id = q.pid WHERE q.v IS NULL")
        self.assertIn("Filter q.v IS NULL", plan)                 # must not be pushed below a LEFT JOIN


class TestDifferential(unittest.TestCase):
    def test_random_queries_match_sqlite(self):
        rng = random.Random(7)
        checked = 0
        for round_ in range(5):
            data = make_data(rng)
            for config in ((True, True), (False, False)):
                db, con = load(data, *config)
                for _ in range(120):
                    q = random_query(rng)
                    want = con.execute(q).fetchall()
                    _, got = db.execute(q)
                    self.assertEqual(norm(got), norm(want), q)
                    checked += 1
                con.close()
        self.assertEqual(checked, 1200)


if __name__ == "__main__":
    unittest.main()
