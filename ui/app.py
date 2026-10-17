"""Streamlit UI for the graph fraud investigation agent."""

import sys
from pathlib import Path

# Make project root importable when Streamlit runs ui/app.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components

from agent.graph import run_investigation


st.set_page_config(page_title="Graph Fraud Agent", layout="wide")
st.title("Graph Fraud Investigation Agent")
st.caption(
    "Multi-hop reasoning over connected data  |  "
    "Explainable results  |  Actions on graph state"
)

query = st.text_input(
    "Investigation query",
    value=(
        "Find paths from a4 to a7 within 4 hops. "
        "Then list high risk actors above 0.7 and flag the highest-risk one for review."
    ),
)

if st.button("Investigate", type="primary"):
    with st.spinner("Traversing graph..."):
        try:
            state = asyncio.run(run_investigation(query))
        except Exception as e:
            st.error(f"Investigation failed: {e}")
            st.stop()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Verdict")
        st.write(state.get("verdict", "No verdict."))

        st.subheader("Graph Path (Explainability)")
        st.code(state.get("path_explanation", "No path recorded."))

        st.subheader("Actions Taken")
        actions = state.get("actions_taken", [])
        if actions:
            for a in actions:
                if "error" in a:
                    st.warning(f"Action error: {a['error']}")
                    continue
                args = a.get("args", {})
                st.success(
                    f"Flagged **{args.get('node_id')}** for review\n\n"
                    f"Reason: {args.get('reason', '')}"
                )
        else:
            st.info("No actions taken.")

        st.subheader("Tool Calls")
        for i, tc in enumerate(state.get("tool_calls", [])):
            with st.expander(f"{i+1}. {tc['tool']}({json.dumps(tc['args'])})"):
                st.code(tc["result"][:1200])

    with col2:
        st.subheader("Graph Trace")
        trace = state.get("graph_trace", [])
        if trace:
            net = Network(
                height="600px",
                width="100%",
                bgcolor="#1a1a2e",
                font_color="white",
                directed=True,
            )
            added = set()
            for hop in trace:
                src, edge, dst = hop[0], hop[1], hop[2]
                for n in (src, dst):
                    if n not in added:
                        color = "#e94560" if n in ("p5", "p3", "p7") else "#4e9af1"
                        net.add_node(n, label=n, title=n, color=color)
                        added.add(n)
                net.add_edge(src, dst, label=edge)

            net.save_graph("graph_trace.html")
            with open("graph_trace.html", "r", encoding="utf-8") as f:
                                st.iframe(Path("graph_trace.html"), height=620)
        else:
            st.info("No graph trace captured.")