"""Generate a synthetic fraud investigation graph in Kuzu."""
import kuzu
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("KUZU_DB_PATH", "./fraud_graph.db")


def seed():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(DB_PATH + ".wal"):
        os.remove(DB_PATH + ".wal")

    db = kuzu.Database(DB_PATH)
    conn = kuzu.Connection(db)

    conn.execute("CREATE NODE TABLE Person(id STRING, name STRING, risk_score DOUBLE, PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE Company(id STRING, name STRING, country STRING, PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE Account(id STRING, bank STRING, opened_at STRING, PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE Transaction(id STRING, amount DOUBLE, ts STRING, PRIMARY KEY(id))")

    conn.execute("CREATE REL TABLE OWNS(FROM Person TO Account)")
    conn.execute("CREATE REL TABLE DIRECTOR_OF(FROM Person TO Company)")
    conn.execute("CREATE REL TABLE SENT(FROM Account TO Account, amount DOUBLE, ts STRING)")
    conn.execute("CREATE REL TABLE SHARES_ADDRESS(FROM Company TO Company)")

    persons = [
        ("p1", "Alice Chen", 0.9), ("p2", "Bob Martinez", 0.1),
        ("p3", "Carol Webb", 0.85), ("p4", "David Okafor", 0.2),
        ("p5", "Eva Petrov", 0.95), ("p6", "Frank Liu", 0.05),
        ("p7", "Grace Adeyemi", 0.8),
    ]
    for p in persons:
        conn.execute("CREATE (:Person {id: $id, name: $name, risk_score: $risk})",
                     {"id": p[0], "name": p[1], "risk": p[2]})

    companies = [
        ("c1", "Apex Holdings", "US"), ("c2", "Vantage Trading", "CY"),
        ("c3", "Northwind Logistics", "US"), ("c4", "Orion Capital", "KY"),
        ("c5", "Pinnacle Services", "US"),
    ]
    for c in companies:
        conn.execute("CREATE (:Company {id: $id, name: $name, country: $country})",
                     {"id": c[0], "name": c[1], "country": c[2]})

    accounts = [
        ("a1", "First National", "2020-01-01"), ("a2", "CryptoBank", "2021-06-15"),
        ("a3", "First National", "2019-03-20"), ("a4", "Offshore Trust", "2022-01-10"),
        ("a5", "CryptoBank", "2021-09-01"), ("a6", "Metro Credit", "2018-11-05"),
        ("a7", "Offshore Trust", "2022-03-15"),
    ]
    for a in accounts:
        conn.execute("CREATE (:Account {id: $id, bank: $bank, opened_at: $opened})",
                     {"id": a[0], "bank": a[1], "opened": a[2]})

    owns = [("p1","a1"),("p2","a6"),("p3","a2"),("p4","a3"),("p5","a4"),("p6","a5"),("p7","a7")]
    for o in owns:
        conn.execute("MATCH (p:Person {id: $pid}), (a:Account {id: $aid}) CREATE (p)-[:OWNS]->(a)",
                     {"pid": o[0], "aid": o[1]})

    directors = [("p1","c1"),("p3","c2"),("p5","c4"),("p2","c3"),("p7","c5"),("p4","c5")]
    for d in directors:
        conn.execute("MATCH (p:Person {id: $pid}), (c:Company {id: $cid}) CREATE (p)-[:DIRECTOR_OF]->(c)",
                     {"pid": d[0], "cid": d[1]})

    flows = [
        ("a4","a2",95000,"2024-01-15"), ("a2","a7",92000,"2024-01-16"),
        ("a7","a4",88000,"2024-01-17"), ("a1","a2",12000,"2024-01-10"),
        ("a3","a2",8000,"2024-01-11"),
    ]
    for i, f in enumerate(flows):
        conn.execute("CREATE (:Transaction {id: $id, amount: $amt, ts: $ts})",
                     {"id": f"t{i}", "amt": f[2], "ts": f[3]})
        conn.execute("MATCH (a:Account {id: $src}), (b:Account {id: $dst}) "
                     "CREATE (a)-[:SENT {amount: $amt, ts: $ts}]->(b)",
                     {"src": f[0], "dst": f[1], "amt": f[2], "ts": f[3]})

    conn.execute("MATCH (c1:Company {id: 'c1'}), (c2:Company {id: 'c2'}) CREATE (c1)-[:SHARES_ADDRESS]->(c2)")
    conn.execute("MATCH (c4:Company {id: 'c4'}), (c5:Company {id: 'c5'}) CREATE (c4)-[:SHARES_ADDRESS]->(c5)")

    print(f"[OK] Seeded fraud graph at {DB_PATH}")
    print("[INFO] High-risk entities: p5 (Eva), p3 (Carol), p7 (Grace)")
    print("[INFO] Fraud path: a4 -> a2 -> a7 -> a4 (circular flow)")


if __name__ == "__main__":
    seed()
