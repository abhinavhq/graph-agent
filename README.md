# Graph Fraud Investigation Agent


**Track 01 — Agents That Act on Connected Data**

A fully local, multi-hop reasoning agent that investigates financial fraud by traversing a knowledge graph. It discovers hidden relationships, explains its reasoning with exact graph paths, and takes action by flagging high-risk entities for review.

No API keys are required — this runs 100% locally using Ollama.

---

## 📸 Demo

![Demo Screenshot](screenshot.png)
*(Add a screenshot of your Streamlit UI here)*

**Example Query:**
> "Find paths from a4 to a7 within 4 hops. Then list high risk actors above 0.7 and flag the highest-risk one for review."

**What happens:**
1. The agent queries the graph to find paths between two accounts.
2. It discovers a circular flow: `a4 → SENT → a2 → SENT → a7`.
3. It lists high-risk actors and identifies `p5` (Eva Petrov) as connected to the flow.
4. It flags `p5` for review, writing the exact reasoning to `review_queue.jsonl`.

---

## 🏗️ Architecture

```text
User Query (Streamlit UI / CLI)
      ↓
LangChain Agent (llama3.2 via Ollama)
      ↓ selects tool (find_paths, get_neighbors, etc.)
MCP Client (Raw JSON-RPC over stdio)
      ↓ spawns
MCP Server (Python process)
      ↓ queries
Kuzu Graph DB (Embedded property graph)
