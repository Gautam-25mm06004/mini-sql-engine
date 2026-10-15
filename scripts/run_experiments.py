"""(1) Differential testing against SQLite on 6,000 random queries; (2) optimiser ablation on a join workload."""
import json, random, sqlite3, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
from minisql import Database  # noqa
from minisql.fuzz import make_data, random_query  # noqa
from test_engine import load, norm  # noqa

R = {}
# 1) Differential testing
rng = random.Random(2026)
n, mism, nonempty, kinds = 0, 0, 0, Counter()
t0 = time.time()
for round_ in range(25):
    data = make_data(rng)
    db, con = load(data)
    for _ in range(240):
        q = random_query(rng)
        want = con.execute(q).fetchall()
        _, got = db.execute(q)
        n += 1; nonempty += bool(want); mism += norm(got) != norm(want)
        kinds["GROUP BY"] += "GROUP BY" in q; kinds["LEFT JOIN"] += "LEFT JOIN" in q; kinds["3-way join"] += "t3" in q
        kinds["DISTINCT"] += "DISTINCT" in q
    con.close()
R["differential"] = {"queries": n, "mismatches": mism, "non_empty_results": nonempty, "features": dict(kinds), "seconds": round(time.time() - t0, 1)}

# 2) Optimiser ablation
rng = random.Random(1)
cust = [(i, rng.choice(["IN", "US", "DE", "JP"]), rng.randint(18, 80)) for i in range(2000)]
orders = [(i, rng.randrange(2000), rng.randint(1, 500), rng.choice([2024, 2025, 2026])) for i in range(20000)]
queries = {
    "join + selective filters": "SELECT c.country, COUNT(*), SUM(o.amount) FROM orders o JOIN customers c ON o.cid = c.id "
                                "WHERE c.age > 70 AND o.year = 2026 GROUP BY c.country",
    "join, no filter": "SELECT COUNT(*) FROM orders o JOIN customers c ON o.cid = c.id",
    "left join anti-pattern": "SELECT COUNT(*) FROM customers c LEFT JOIN orders o ON o.cid = c.id AND o.amount > 495 WHERE o.id IS NULL",
}
abl = []
for label, (pd, hj) in {"no optimisation (nested loop, filter on top)": (False, False), "predicate pushdown only": (True, False),
                        "hash join only": (False, True), "pushdown + hash join": (True, True)}.items():
    db = Database(pd, hj)
    db.execute("CREATE TABLE customers (id INT, country TEXT, age INT)"); db.tables["customers"][1].extend(cust)
    db.execute("CREATE TABLE orders (id INT, cid INT, amount INT, year INT)"); db.tables["orders"][1].extend(orders)
    row = {"configuration": label}
    for qn, q in queries.items():
        t = time.perf_counter(); _, res = db.execute(q); row[qn + " (s)"] = round(time.perf_counter() - t, 3)
    abl.append(row)
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE customers (id INT, country TEXT, age INT)"); con.executemany("INSERT INTO customers VALUES (?,?,?)", cust)
con.execute("CREATE TABLE orders (id INT, cid INT, amount INT, year INT)"); con.executemany("INSERT INTO orders VALUES (?,?,?,?)", orders)
row = {"configuration": "SQLite (reference, no indexes)"}
for qn, q in queries.items():
    t = time.perf_counter(); con.execute(q).fetchall(); row[qn + " (s)"] = round(time.perf_counter() - t, 3)
abl.append(row)
R["ablation"] = abl
db = Database(); db.execute("CREATE TABLE customers (id INT, country TEXT, age INT)"); db.execute("CREATE TABLE orders (id INT, cid INT, amount INT, year INT)")
R["example_plan"] = db.explain(queries["join + selective filters"])

(ROOT / "results" / "results.json").write_text(json.dumps(R, indent=2))
d = R["differential"]
md = f"# Results\n\n## Differential testing vs SQLite\n\n{d['queries']} random queries over 25 random databases (with NULLs): **{d['mismatches']} mismatches**; " \
     f"{d["non_empty_results"]} had non-empty results. Features exercised: {d['features']}. ({d['seconds']} s)\n\n"
md += "## Optimiser ablation (20,000 orders x 2,000 customers)\n\n"
cols = list(abl[0]); md += "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n" + "".join("| " + " | ".join(str(r[c]) for c in cols) + " |\n" for r in abl)
md += f"\n## Example plan\n\n```\n{R['example_plan']}```\n"
(ROOT / "results" / "summary.md").write_text(md)
print(md)
