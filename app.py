from __future__ import annotations

import json

import streamlit as st

from src.agent.llm_client import get_provider_status
from src.agent.trace_export import build_trace_export_payload, write_trace_export
from src.agent.workflow import run_agent_turn
from src.storage import database


st.set_page_config(
    page_title="Memory-Driven Character Agent",
    layout="wide",
)


def initialize_app() -> None:
    database.initialize_database()
    if "last_run" not in st.session_state:
        st.session_state.last_run = None


def render_state_panel() -> None:
    npc = database.get_npc("lina")
    player = database.get_player_state()
    quest = database.get_quest("lost_key")
    world_events = database.get_world_events(limit=5)

    st.subheader("Current NPC State")
    st.json(
        {
            "npc": npc,
            "quest": quest,
            "player": player,
            "recent_world_events": world_events,
        }
    )


def render_last_run() -> None:
    run = st.session_state.last_run
    if run is None:
        st.info("输入一句话开始与 Lina 交互。建议先试：我把你丢失的钥匙找回来了。")
        return

    st.subheader("Player Input")
    st.write(run.player_input)

    st.subheader("NPC Response")
    st.success(run.npc_response)

    st.subheader("Agent Workflow Trace")
    st.table(run.workflow_steps)

    left, right = st.columns(2)
    with left:
        st.subheader("Retrieved Memories")
        if run.retrieved_memories:
            st.json(run.retrieved_memories)
        else:
            st.write("No memories retrieved.")

        st.subheader("Structured Decision")
        st.json(run.decision)

    with right:
        st.subheader("Tool Calls")
        if run.tool_calls:
            st.json(run.tool_calls)
        else:
            st.write("No tool calls.")

        st.subheader("State Changes")
        if run.state_changes:
            st.json(run.state_changes)
        else:
            st.write("No state changes.")


def render_logs() -> None:
    st.subheader("Interaction Log")
    logs = database.get_interaction_logs(limit=10)
    if not logs:
        st.write("No interaction logs yet.")
        return

    export_payload = build_trace_export_payload(limit=10)
    export_path = write_trace_export(limit=10)
    st.caption(f"Trace JSON is also written automatically to `{export_path}`.")
    st.download_button(
        label="Download Trace JSON",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2),
        file_name="agent_trace_export.json",
        mime="application/json",
    )

    for log in logs:
        with st.expander(f"#{log['id']} - {log['created_at']} - {log['player_input']}"):
            st.write("NPC Response")
            st.write(log["npc_response"])
            st.write("Retrieved Memories")
            st.json(log["retrieved_memories"])
            st.write("Decision")
            st.json(log["decision"])
            st.write("Workflow Steps")
            st.table(log["workflow_steps"])
            st.write("Tool Calls")
            st.json(log["tool_calls"])
            st.write("State Changes")
            st.json(log["state_changes"])


initialize_app()

st.title("Memory-Driven Interactive Character Agent")
st.caption("MVP: single NPC Lina, SQLite state, mock decision logic, visible agent trace.")

with st.sidebar:
    st.header("Demo Controls")
    st.markdown("### LLM Provider")
    st.json(get_provider_status())

    if st.button("Reset SQLite Demo Data"):
        database.reset_database()
        st.session_state.last_run = None
        st.success("Demo data reset.")

    st.markdown("### Suggested Inputs")
    st.markdown("- `我想打听一下地下遗迹的入口。`")
    st.markdown("- `我把你丢失的钥匙找回来了。`")
    st.markdown("- `上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？`")

player_input = st.text_input("Player Input", placeholder="对 Lina 说些什么...")

if st.button("Send to Lina", type="primary") and player_input.strip():
    with st.spinner("Waiting for Lina's decision..."):
        st.session_state.last_run = run_agent_turn(player_input.strip())

state_col, trace_col = st.columns([1, 2])
with state_col:
    render_state_panel()

with trace_col:
    render_last_run()

st.divider()
render_logs()
