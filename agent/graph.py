"""Investigation agent. Talks to the MCP server over stdio via raw JSON-RPC.

Uses a local Ollama model. No API key needed.
"""

import os
import sys
import re
import json
import asyncio
from typing import TypedDict
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from .prompts import SYSTEM_PROMPT, TOOL_SELECTION_PROMPT

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


class InvestigationState(TypedDict):
    query: str
    tool_calls: list
    graph_trace: list
    verdict: str
    path_explanation: str
    actions_taken: list


class MCPClient:
    """Minimal stdio JSON-RPC client. Spawns python -m mcp_server.server."""

    def __init__(self):
        self.proc = None
        self._id = 0

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "mcp_server.server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fraud-agent", "version": "0.1.0"},
        })
        await self._send_notification("notifications/initialized", {})

    async def stop(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self.proc.kill()

    async def _send(self, method, params):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        self.proc.stdin.write((json.dumps(req) + "\n").encode())
        await self.proc.stdin.drain()
        line = await self.proc.stdout.readline()
        if not line:
            err = (await self.proc.stderr.read()).decode()[:1000]
            raise RuntimeError("MCP server closed. stderr: " + err)
        resp = json.loads(line.decode())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp.get("result", {})

    async def _send_notification(self, method, params):
        req = {"jsonrpc": "2.0", "method": method, "params": params}
        self.proc.stdin.write((json.dumps(req) + "\n").encode())
        await self.proc.stdin.drain()

    async def call_tool(self, name, args):
        result = await self._send("tools/call", {"name": name, "arguments": args})
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""


def _extract_trace(result_text, trace):
    """Parse FalkorDB output (and fallback to Kuzu) into hop triples."""
    try:
        data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(data, list):
        return

    def get_id(node_str):
        if isinstance(node_str, dict):
            return node_str.get("id") or node_str.get("_label", "?")
        # FalkorDB string format: '(:Person{id:"p5",...})'
        match = re.search(r'id:\\?"([^"\\]+)\\?"', str(node_str))
        return match.group(1) if match else str(node_str)[:10]

    def get_rel(rel_str):
        if isinstance(rel_str, dict):
            return rel_str.get("_label", "edge")
        # FalkorDB string format: '()-[:SENT{...}]->()'
        match = re.search(r'\[:([A-Z_]+)', str(rel_str))
        return match.group(1) if match else "edge"

    def walk(node):
        if not isinstance(node, list):
            return
        # Kuzu shape: [nodes_list, rels_list]
        if len(node) == 2 and isinstance(node[0], list) and isinstance(node[1], list):
            nodes, rels = node
            if nodes and rels and isinstance(nodes[0], dict) and isinstance(rels[0], dict):
                for i in range(len(nodes) - 1):
                    src_id = get_id(nodes[i])
                    dst_id = get_id(nodes[i + 1])
                    rel_label = get_rel(rels[i]) if i < len(rels) else "edge"
                    trace.append([str(src_id), str(rel_label), str(dst_id)])
                return
        # FalkorDB shape: [src_str, rel_str, tgt_str]
        if len(node) == 3 and all(isinstance(x, str) for x in node):
            src_id = get_id(node[0])
            rel_label = get_rel(node[1])
            dst_id = get_id(node[2])
            if src_id and dst_id and src_id != dst_id:
                trace.append([str(src_id), str(rel_label), str(dst_id)])
            return
        for item in node:
            walk(item)

    for row in data:
        walk(row)


async def run_investigation(query: str, max_steps: int = 6):
    llm = ChatOllama(model=OLLAMA_MODEL, temperature=0)

    state: InvestigationState = {
        "query": query,
        "tool_calls": [],
        "graph_trace": [],
        "verdict": "",
        "path_explanation": "",
        "actions_taken": [],
    }

    client = MCPClient()
    await client.start()
    try:
        for _ in range(max_steps):
            prompt = TOOL_SELECTION_PROMPT.format(state=json.dumps(state, default=str)[:4000])
            resp = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            raw = resp.content.strip().strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
            try:
                parsed = json.loads(raw)
                tool_name = parsed["tool"]
                args = parsed.get("args", {}) or {}
            except (json.JSONDecodeError, KeyError):
                tool_name, args = "get_schema", {}

            # Sanitize args from small models
            if tool_name == "find_paths":
                h = args.get("max_hops", 4)
                try:
                    h = int(h)
                except (TypeError, ValueError):
                    h = 4
                args["max_hops"] = max(1, min(h, 6))
            if tool_name in ("find_paths", "get_neighbors", "flag_for_review"):
                for key in ("start_id", "end_id", "node_id"):
                    if key in args and not isinstance(args[key], str):
                        args[key] = str(args[key])

            try:
                result_text = await client.call_tool(tool_name, args)
            except Exception as e:
                result_text = "TOOL ERROR: " + str(e)

            _extract_trace(result_text, state["graph_trace"])

            # Compact summary for the model
            if tool_name == "find_paths":
                if state["graph_trace"]:
                    lines = [
                        h[0] + " -[" + h[1] + "]-> " + h[2]
                        for h in state["graph_trace"][-6:]
                    ]
                    summary = "Found path: " + " ; ".join(lines)
                else:
                    summary = "No paths found. Preview: " + result_text[:300]
            elif tool_name == "high_risk_actors":
                summary = "High-risk actors: " + result_text[:400]
            elif tool_name == "get_neighbors":
                summary = "Neighbors: " + result_text[:600]
            else:
                summary = result_text[:600]

            state["tool_calls"].append({
                "tool": tool_name, "args": args, "result": summary,
            })
            if tool_name == "flag_for_review":
                state["actions_taken"].append({"args": args})

            decide = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=(
                    "Query: " + query + "\n"
                    "Tool calls: " + json.dumps(state["tool_calls"], default=str)[:3000] + "\n"
                    "Graph trace: " + json.dumps(state["graph_trace"], default=str)[:2000] + "\n\n"
                    "Decide now. Rules:\n"
                    "- If graph_trace is non-empty, you HAVE evidence. Do not say insufficient.\n"
                    "- Summarize the chain as the PATH.\n"
                    "- If a high-risk actor (p5, p3, p7) is connected, recommend flagging.\n\n"
                    "Respond with:\n"
                    "VERDICT: <one sentence>\n"
                    "PATH: <A -> edge -> B -> edge -> C>\n"
                    "CONFIDENCE: <0-1>\n"
                    "Or if truly no evidence: NEED_MORE"
                )),
            ])
            if "NEED_MORE" not in decide.content:
                state["verdict"] = decide.content
                for line in decide.content.split("\n"):
                    if line.startswith("PATH:"):
                        state["path_explanation"] = line.replace("PATH:", "").strip()
                break

        if not state["verdict"]:
            state["verdict"] = "Max steps reached without final verdict."
            state["path_explanation"] = " -> ".join(
                h[0] + " -[" + h[1] + "]-> " + h[2] for h in state["graph_trace"][:8]
            ) or "No path extracted."

        # --- Post-verdict action: flag the highest-risk actor connected to the trace ---
        if state["graph_trace"]:
            try:
                hr_raw = await client.call_tool("high_risk_actors", {"threshold": 0.7})
                hr = json.loads(hr_raw) if hr_raw else []
                trace_ids = set()
                for h in state["graph_trace"]:
                    trace_ids.add(h[0])
                    trace_ids.add(h[2])

                connected_high = []
                for actor in hr:
                    if not isinstance(actor, list) or len(actor) < 3:
                        continue
                    pid = actor[0]
                    # direct hit
                    if pid in trace_ids:
                        connected_high.append(actor)
                        continue
                    # one hop out
                    nb_raw = await client.call_tool("get_neighbors", {"node_id": pid})
                    if isinstance(nb_raw, str) and any(t in nb_raw for t in trace_ids):
                        connected_high.append(actor)

                if connected_high:
                    target = connected_high[0]
                    reason = (
                        "Connected to suspicious multi-hop flow. Path: "
                        + (state["path_explanation"] or "see graph_trace")
                        + ". Risk score: " + str(target[2])
                    )
                    await client.call_tool("flag_for_review", {
                        "node_id": target[0],
                        "reason": reason,
                    })
                    state["actions_taken"].append({
                        "tool": "flag_for_review",
                        "args": {"node_id": target[0], "reason": reason},
                    })
                    state["verdict"] = state["verdict"] + (
                        "\nACTION: Flagged " + str(target[1]) + " (" + str(target[0])
                        + ", risk=" + str(target[2]) + ") for review."
                    )
            except Exception as e:
                state["actions_taken"].append({"error": str(e)})
    finally:
        await client.stop()

    return state


if __name__ == "__main__":
    q = "Find paths from a4 to a7 within 4 hops. Then list high risk actors above 0.7 and flag the highest-risk one for review."
    print(json.dumps(asyncio.run(run_investigation(q)), indent=2, default=str))