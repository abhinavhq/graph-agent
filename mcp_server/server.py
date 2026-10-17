"""Minimal MCP server over stdio. No external MCP API dependency."""

import sys
import json
import os
import kuzu
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("KUZU_DB_PATH", "./fraud_graph.db")

_db = None
_conn = None


def get_conn():
    global _db, _conn
    if _conn is None:
        _db = kuzu.Database(DB_PATH)
        _conn = kuzu.Connection(_db)
    return _conn


def rows_to_list(result):
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return rows


TOOLS = [
    {"name": "get_schema", "description": "Return the graph schema.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "run_cypher", "description": "Execute a read-only Cypher query.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "find_paths", "description": "Find bounded paths between two nodes.",
     "inputSchema": {"type": "object",
                     "properties": {"start_id": {"type": "string"},
                                    "end_id": {"type": "string"},
                                    "max_hops": {"type": "integer"}},
                     "required": ["start_id", "end_id"]}},
    {"name": "get_neighbors", "description": "Get neighbors of a node.",
     "inputSchema": {"type": "object",
                     "properties": {"node_id": {"type": "string"},
                                    "edge_type": {"type": "string"}},
                     "required": ["node_id"]}},
    {"name": "high_risk_actors", "description": "List persons above a risk threshold.",
     "inputSchema": {"type": "object",
                     "properties": {"threshold": {"type": "number"}},
                     "required": ["threshold"]}},
    {"name": "flag_for_review", "description": "ACTION: Flag a node for fraud review.",
     "inputSchema": {"type": "object",
                     "properties": {"node_id": {"type": "string"},
                                    "reason": {"type": "string"}},
                     "required": ["node_id", "reason"]}},
]


def call_tool(name, args):
    conn = get_conn()
    if name == "get_schema":
        return json.dumps(rows_to_list(conn.execute("CALL show_tables() RETURN *")), default=str)
    if name == "run_cypher":
        try:
            return json.dumps(rows_to_list(conn.execute(args["query"])), default=str)
        except Exception as e:
            return "ERROR: " + str(e)
    if name == "find_paths":
        s = args["start_id"]
        e = args["end_id"]
        h = args.get("max_hops", 4)
        q = ("MATCH p = (a {id: '" + s + "'})-[*1.." + str(h) + "]->(b {id: '" + e + "'}) "
             "RETURN nodes(p) AS nodes, rels(p) AS rels LIMIT 5")
        try:
            return json.dumps(rows_to_list(conn.execute(q)), default=str)
        except Exception as ex:
            return "ERROR: " + str(ex)
    if name == "get_neighbors":
        nid = args["node_id"]
        et = args.get("edge_type", "")
        if et:
            q = "MATCH (n {id: '" + nid + "'})-[r:" + et + "]-(m) RETURN n, r, m LIMIT 50"
        else:
            q = "MATCH (n {id: '" + nid + "'})-[r]-(m) RETURN n, r, m LIMIT 50"
        try:
            return json.dumps(rows_to_list(conn.execute(q)), default=str)
        except Exception as ex:
            return "ERROR: " + str(ex)
    if name == "high_risk_actors":
        t = args.get("threshold", 0.7)
        q = ("MATCH (p:Person) WHERE p.risk_score >= " + str(t) +
             " RETURN p.id, p.name, p.risk_score ORDER BY p.risk_score DESC")
        return json.dumps(rows_to_list(conn.execute(q)), default=str)
    if name == "flag_for_review":
        with open("review_queue.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"action": "FLAG_FOR_REVIEW",
                                "node_id": args["node_id"],
                                "reason": args["reason"]}) + "\n")
        return "[ACTION] Flagged " + args["node_id"] + " for review."
    return "Unknown tool: " + name


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rid = req.get("id")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fraud-graph-tools", "version": "0.1.0"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            try:
                text = call_tool(name, args)
                send({"jsonrpc": "2.0", "id": rid,
                      "result": {"content": [{"type": "text", "text": text}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": rid,
                      "result": {"content": [{"type": "text", "text": "ERROR: " + str(e)}],
                                 "isError": True}})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": "Method not found: " + str(method)}})


if __name__ == "__main__":
    main()