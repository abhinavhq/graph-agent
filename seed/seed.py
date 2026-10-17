"""Generate a synthetic fraud investigation graph in FalkorDB."""
from falkordb import FalkorDB

def seed():
    # Connect to the FalkorDB Docker container running on localhost:6379
    db = FalkorDB(host='localhost', port=6379)
    graph = db.select_graph('fraud')

    # Clear existing graph to start fresh
    try:
        graph.delete()
    except Exception:
        pass

    # Seed Persons
    persons = [
        ("p1", "Alice Chen", 0.9), ("p2", "Bob Martinez", 0.1),
        ("p3", "Carol Webb", 0.85), ("p4", "David Okafor", 0.2),
        ("p5", "Eva Petrov", 0.95), ("p6", "Frank Liu", 0.05),
        ("p7", "Grace Adeyemi", 0.8)
    ]
    for p in persons:
        graph.query(f"CREATE (:Person {{id: '{p[0]}', name: '{p[1]}', risk_score: {p[2]}}})")

    # Seed Companies
    companies = [
        ("c1", "Apex Holdings", "US"), ("c2", "Vantage Trading", "CY"),
        ("c3", "Northwind Logistics", "US"), ("c4", "Orion Capital", "KY"),
        ("c5", "Pinnacle Services", "US")
    ]
    for c in companies:
        graph.query(f"CREATE (:Company {{id: '{c[0]}', name: '{c[1]}', country: '{c[2]}'}})")

    # Seed Accounts
    accounts = [
        ("a1", "First National", "2020-01-01"), ("a2", "CryptoBank", "2021-06-15"),
        ("a3", "First National", "2019-03-20"), ("a4", "Offshore Trust", "2022-01-10"),
        ("a5", "CryptoBank", "2021-09-01"), ("a6", "Metro Credit", "2018-11-05"),
        ("a7", "Offshore Trust", "2022-03-15")
    ]
    for a in accounts:
        graph.query(f"CREATE (:Account {{id: '{a[0]}', bank: '{a[1]}', opened_at: '{a[2]}'}})")

    # Seed Relationships
    owns = [("p1","a1"),("p2","a6"),("p3","a2"),("p4","a3"),("p5","a4"),("p6","a5"),("p7","a7")]
    for o in owns:
        graph.query(f"MATCH (p:Person {{id: '{o[0]}'}}), (a:Account {{id: '{o[1]}'}}) CREATE (p)-[:OWNS]->(a)")

    directors = [("p1","c1"),("p3","c2"),("p5","c4"),("p2","c3"),("p7","c5"),("p4","c5")]
    for d in directors:
        graph.query(f"MATCH (p:Person {{id: '{d[0]}'}}), (c:Company {{id: '{d[1]}'}}) CREATE (p)-[:DIRECTOR_OF]->(c)")

    flows = [
        ("a4","a2",95000,"2024-01-15"), ("a2","a7",92000,"2024-01-16"),
        ("a7","a4",88000,"2024-01-17"), ("a1","a2",12000,"2024-01-10"),
        ("a3","a2",8000,"2024-01-11")
    ]
    for i, f in enumerate(flows):
        graph.query(f"CREATE (:Transaction {{id: 't{i}', amount: {f[2]}, ts: '{f[3]}'}})")
        graph.query(f"MATCH (a:Account {{id: '{f[0]}'}}), (b:Account {{id: '{f[1]}'}}) CREATE (a)-[:SENT {{amount: {f[2]}, ts: '{f[3]}'}}]->(b)")

    graph.query("MATCH (c1:Company {id: 'c1'}), (c2:Company {id: 'c2'}) CREATE (c1)-[:SHARES_ADDRESS]->(c2)")
    graph.query("MATCH (c4:Company {id: 'c4'}), (c5:Company {id: 'c5'}) CREATE (c4)-[:SHARES_ADDRESS]->(c5)")

    print("[OK] Seeded FalkorDB fraud graph successfully!")
    print("[INFO] High-risk entities: p5 (Eva), p3 (Carol), p7 (Grace)")
    print("[INFO] Fraud path: a4 -> a2 -> a7 -> a4 (circular flow)")

if __name__ == "__main__":
    seed()