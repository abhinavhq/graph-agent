"""MCP server over stdio - FalkorDB version."""
import sys, json
from falkordb import FalkorDB

# Connect to FalkorDB
db = FalkorDB(host='localhost', port=6379)
graph = db.select_graph('fraud')

TOOLS = [
    {"name": "get_schema", "description": "Return the graph schema.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "run_cypher", "description": "Execute a read-only Cypher query.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "find_paths", "description": "Find bounded paths between two nodes.", "inputSchema": {"type": "object", "properties": {"start_id": {"type": "string"}, "end_id": {"type": "string"}, "max_hops": {"type": "integer"}}, "required": ["start_id", "end_id"]}},
    {"name": "get_neighbors", "description": "Get neighbors of a node.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}},
    {"name": "high_risk_actors", "description": "List persons above a risk threshold.", "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number"}}, "required": ["threshold"]}},
    {"name": "flag_for_review", "description": "ACTION: Flag a node for fraud review.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["node_id", "reason"]}}
]

def call_tool(name, args):
    if name == "get_schema":
        return "Nodes: Person(id, name, risk_score), Company(id, name, country), Account(id, bank, opened_at), Transaction(id, amount, ts). Edges: OWNS, DIRECTOR_OF, SENT, SHARES_ADDRESS."
        
    if name == "run_cypher":
        try:
            result = graph.query(args["query"])
            return json.dumps(result.result_set, default=str)
        except Exception as e:
            return f"ERROR: {e}"
            
    if name == "find_paths":
        s, e = args["start_id"], args["end_id"]
        h = args.get("max_hops", 4)
        q = f"MATCH p=(a {{id: '{s}'}})-[*1..{h}]->(b {{id: '{e}'}}) RETURN nodes(p), relationships(p) LIMIT 5"
        try:
            result = graph.query(q)
            return json.dumps(result.result_set, default=str)
        except Exception as ex:
            return f"ERROR: {ex}"
            
    if name == "get_neighbors":
        nid = args["node_id"]
        q = f"MATCH (n {{id: '{nid}'}})-[r]-(m) RETURN n, r, m LIMIT 50"
        try:
            result = graph.query(q)
            return json.dumps(result.result_set, default=str)
        except Exception as ex:
            return f"ERROR: {ex}"
            
    if name == "high_risk_actors":
        t = args.get("threshold", 0.7)
        q = f"MATCH (p:Person) WHERE p.risk_score >= {t} RETURN p.id, p.name, p.risk_score ORDER BY p.risk_score DESC"
        result = graph.query(q)
        return json.dumps(result.result_set, default=str)
        
    if name == "flag_for_review":
        with open("review_queue.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"action": "FLAG_FOR_REVIEW", "node_id": args["node_id"], "reason": args["reason"]}) + "\n")
        return f"[ACTION] Flagged {args['node_id']} for review."
    return f"Unknown tool: {name}"

def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except: continue

        method, rid = req.get("method"), req.get("id")
        
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "falkor-tools", "version": "0.1.0"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = req.get("params", {})
            try:
                text = call_tool(params.get("name"), params.get("arguments", {}))
                send({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})

if __name__ == "__main__":
    main()