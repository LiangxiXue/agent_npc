from __future__ import annotations

import json
import traceback
from typing import Any

import streamlit as st

from src.agent.embedding_client import get_embedding_settings
from src.agent.lore_retrieval import ensure_lore_embeddings, retrieve_lore
from src.agent.llm_client import get_provider_status
from src.agent.semantic_retrieval import ensure_embeddings_for_memories
from src.agent.trace_export import build_trace_export_payload, write_trace_export
from src.agent.workflow import run_agent_turn
from src.storage import database


RETRIEVAL_LABELS = {
    "typed": "Typed rule retrieval",
    "hybrid": "Hybrid RAG",
    "semantic": "Semantic retrieval",
    "legacy": "Legacy keyword retrieval",
    "off": "Long-term memory off",
}

SUGGESTED_INPUTS = [
    "我想打听一下地下遗迹的入口。",
    "我把你丢失的钥匙找回来了。",
    "我找到守卫徽章了，登记册签名也能对上。",
    "我看到遗迹门边有三角符号和封闭石门。",
    "Sable，你知道遗迹入口或者古物线索吗？",
]


st.set_page_config(
    page_title="Memory-Driven Character Agent",
    layout="wide",
)


def initialize_app() -> None:
    database.initialize_database()
    defaults = {
        "last_run": None,
        "run_status": "waiting",
        "last_error": None,
        "status_message": "等待玩家输入。",
        "selected_prompt": "",
        "selected_npc": "lina",
        "retrieval_preview": [],
        "lore_preview": [],
        "paused": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_page_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
        }
        div[data-testid="stExpander"] {
            border-radius: 8px;
        }
        .status-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.6rem;
            margin: 0.5rem 0 1rem;
        }
        .status-item {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
            background: #ffffff;
        }
        .status-label {
            color: #64748b;
            font-size: 0.78rem;
            margin-bottom: 0.2rem;
        }
        .status-value {
            color: #0f172a;
            font-size: 0.94rem;
            font-weight: 650;
        }
        .memory-card {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.8rem;
            margin-bottom: 0.65rem;
            background: #ffffff;
        }
        .muted {
            color: #64748b;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def readable_status() -> tuple[str, str]:
    status = st.session_state.run_status
    if st.session_state.paused:
        return "Paused", "已暂停发送新输入。"
    labels = {
        "waiting": ("Waiting", "等待玩家输入。"),
        "running": ("Running", "正在执行检索、决策、工具调用和回复生成。"),
        "completed": ("Completed", "当前 workflow 已完成。"),
        "error": ("Error", "上一轮执行发生错误。"),
    }
    return labels.get(status, ("Unknown", st.session_state.status_message))


def render_global_status(retrieval_mode: str, npc_id: str) -> None:
    npc = database.get_npc(npc_id)
    quest = database.get_primary_quest_for_npc(npc_id)
    player = database.get_player_state()
    logs = database.get_interaction_logs(limit=100)
    memories = database.get_recent_memories(npc_id=npc_id, limit=100)
    lore_count = len(database.get_lore_documents(npc_id=npc_id, limit=100))
    status_label, status_help = readable_status()

    st.markdown(
        f"""
        <div class="status-strip">
            <div class="status-item">
                <div class="status-label">运行状态</div>
                <div class="status-value">{status_label}</div>
                <div class="muted">{status_help}</div>
            </div>
            <div class="status-item">
                <div class="status-label">检索模式</div>
                <div class="status-value">{RETRIEVAL_LABELS[retrieval_mode]}</div>
                <div class="muted">{'已启用记忆检索' if retrieval_mode != 'off' else '当前不使用长期记忆'}</div>
            </div>
            <div class="status-item">
                <div class="status-label">NPC / 任务</div>
                <div class="status-value">{npc['name']} / {quest['status']}</div>
                <div class="muted">trust={npc['trust']} affection={npc['affection']} alignment={npc.get('hidden_alignment', 'neutral')}</div>
            </div>
            <div class="status-item">
                <div class="status-label">上下文</div>
                <div class="status-value">{lore_count} 条 lore / {len(memories)} 条记忆</div>
                <div class="muted">{len(logs)} 条日志；地点：{player['location']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.last_error:
        error = st.session_state.last_error
        st.error(f"错误发生在：{error['step']}。原因：{error['message']}")
        st.info(f"下一步建议：{error['suggestion']}")
        with st.expander("查看错误详情", expanded=False):
            st.code(error["traceback"], language="text")


def render_sidebar() -> tuple[str, bool, str]:
    with st.sidebar:
        st.header("Control Panel")
        npcs = database.list_npcs()
        npc_ids = [npc["npc_id"] for npc in npcs]
        if st.session_state.selected_npc not in npc_ids:
            st.session_state.selected_npc = npc_ids[0]
        npc_id = st.selectbox(
            "NPC",
            options=npc_ids,
            index=npc_ids.index(st.session_state.selected_npc),
            format_func=lambda value: next(
                f"{npc['name']} - {npc['role']}" for npc in npcs if npc["npc_id"] == value
            ),
            help="选择本轮交互的 NPC。长期记忆、短期上下文和任务状态按 NPC 隔离。",
        )
        st.session_state.selected_npc = npc_id

        retrieval_mode = st.selectbox(
            "Memory retrieval",
            options=["typed", "hybrid", "semantic", "legacy", "off"],
            format_func=lambda value: RETRIEVAL_LABELS[value],
            index=1,
            help="选择本轮长期记忆检索方式。默认推荐 Hybrid RAG 观察语义分数。",
        )

        st.toggle(
            "Pause new turns",
            key="paused",
            help="暂停后不会发送新的玩家输入；已保存的状态不受影响。",
        )

        control_left, control_right = st.columns(2)
        with control_left:
            if st.button("Reset state", use_container_width=True):
                database.reset_database()
                st.session_state.last_run = None
                st.session_state.retrieval_preview = []
                st.session_state.lore_preview = []
                st.session_state.run_status = "waiting"
                st.session_state.status_message = "SQLite demo state has been reset."
                st.session_state.last_error = None
                st.toast("Demo state reset.")
        with control_right:
            if st.button("Clear chat", use_container_width=True):
                database.clear_interaction_history(npc_id)
                st.session_state.last_run = None
                st.session_state.retrieval_preview = []
                st.session_state.lore_preview = []
                st.session_state.run_status = "waiting"
                st.session_state.status_message = "Conversation context and logs have been cleared."
                st.session_state.last_error = None
                st.toast("Conversation cleared.")

        if st.button("Rebuild memory index", use_container_width=True):
            lore_writes = ensure_lore_embeddings(npc_id)
            writes = ensure_embeddings_for_memories(npc_id)
            st.session_state.status_message = (
                f"Indexed {len(lore_writes)} lore document(s) and {len(writes)} memory record(s)."
            )
            st.toast(f"Indexed {len(lore_writes)} lore + {len(writes)} memory record(s).")

        st.divider()
        st.subheader("Runtime")
        render_runtime_summary()

        st.divider()
        st.subheader("Suggested Inputs")
        for index, prompt in enumerate(SUGGESTED_INPUTS, start=1):
            if st.button(prompt, key=f"prompt_{index}", use_container_width=True):
                st.session_state.selected_prompt = prompt

    return retrieval_mode, st.session_state.paused, npc_id


def render_runtime_summary() -> None:
    provider = get_provider_status()
    embedding = get_embedding_settings()
    llm_state = "已配置" if provider["configured"] else "未配置，使用 mock 回退"
    embedding_state = "可用" if embedding["configured"] else "未配置"
    st.caption(f"LLM：{provider['provider']}，{llm_state}")
    st.caption(
        f"Embedding：{embedding['provider']}，{embedding_state}；"
        f"backend={embedding['retrieval_backend']}；faiss={'yes' if embedding['faiss_available'] else 'no'}"
    )
    with st.expander("Raw runtime settings", expanded=False):
        st.json({"llm": provider, "embedding": embedding})


def render_state_panel(npc_id: str) -> None:
    npc = database.get_npc(npc_id)
    player = database.get_player_state()
    quest = database.get_primary_quest_for_npc(npc_id)
    world_events = database.get_world_events(limit=5)

    st.subheader("Agent State")
    st.dataframe(
        [
            {
                "状态": "信任度",
                "当前值": npc["trust"],
                "说明": f"{npc['name']} 对玩家的信任程度，会影响敏感信息披露。",
            },
            {
                "状态": "好感度",
                "当前值": npc["affection"],
                "说明": f"{npc['name']} 对玩家的态度倾向。",
            },
            {
                "状态": "隐藏立场",
                "当前值": npc.get("hidden_alignment", "neutral"),
                "说明": "仅用于 debug/trace 的社交推理立场，普通回复不会直接暴露。",
            },
            {
                "状态": "任务状态",
                "当前值": quest["status"],
                "说明": f"{quest['quest_id']} 任务当前进度。",
            },
            {
                "状态": "玩家位置",
                "当前值": player["location"],
                "说明": "玩家当前所在地点。",
            },
        ],
        use_container_width=True,
        hide_index=True,
    )

    inventory = ", ".join(player["inventory"]) if player["inventory"] else "Empty"
    locations = ", ".join(player["unlocked_locations"]) if player["unlocked_locations"] else "None"
    st.caption(f"Inventory: {inventory}")
    st.caption(f"Unlocked locations: {locations}")

    if world_events:
        with st.expander("Recent world events", expanded=False):
            for event in world_events:
                st.write(f"{event['created_at']} - {event['content']}")
    else:
        st.info("暂无世界事件。")


def render_interaction_area(retrieval_mode: str, paused: bool, npc_id: str) -> None:
    st.subheader("Conversation")

    selected_prompt = st.session_state.selected_prompt
    player_input = st.text_area(
        "Player input",
        value=selected_prompt,
        placeholder=f"对 {database.get_npc(npc_id)['name']} 说些什么...",
        height=88,
        disabled=paused,
    )
    st.session_state.selected_prompt = player_input

    send_col, preview_col, export_col = st.columns([1, 1, 1])
    with send_col:
        send_clicked = st.button(
            "Run one turn",
            type="primary",
            use_container_width=True,
            disabled=paused or not player_input.strip(),
        )
    with preview_col:
        preview_clicked = st.button(
            "Preview memory retrieval",
            use_container_width=True,
            disabled=not player_input.strip(),
        )
    with export_col:
        if st.button("Export trace", use_container_width=True):
            export_path = write_trace_export(limit=10)
            st.success(f"Trace exported to {export_path}")

    if paused:
        st.warning("当前已暂停。你仍可以查看状态、日志和调试信息。")

    if preview_clicked:
        run_memory_preview(player_input.strip(), retrieval_mode, npc_id)

    if send_clicked:
        run_turn(player_input.strip(), retrieval_mode, npc_id)

    render_last_run()


def run_memory_preview(player_input: str, retrieval_mode: str, npc_id: str) -> None:
    try:
        lore = retrieve_lore(player_input, npc_id=npc_id)
        memories = database.search_memories(
            player_input,
            npc_id=npc_id,
            mode=retrieval_mode,
        )
        st.session_state.lore_preview = lore
        st.session_state.retrieval_preview = memories
        st.session_state.status_message = f"本轮预检索到 {len(lore)} 条 lore 和 {len(memories)} 条长期记忆。"
        if lore or memories:
            st.success(f"已预检索到 {len(lore)} 条 lore 和 {len(memories)} 条长期记忆。")
        else:
            st.info("当前输入没有检索到 lore 或长期记忆。")
    except Exception as exc:
        record_error("Memory retrieval preview", exc)


def run_turn(player_input: str, retrieval_mode: str, npc_id: str) -> None:
    st.session_state.run_status = "running"
    st.session_state.status_message = "正在执行本轮 workflow。"
    st.session_state.last_error = None

    try:
        with st.status("Running agent workflow", expanded=True) as status:
            status.write("读取短期上下文和长期记忆。")
            status.write("生成结构化决策。")
            status.write("执行工具并更新 SQLite 状态。")
            status.write("生成 NPC 回复并记录 trace。")
            st.session_state.last_run = run_agent_turn(
                player_input,
                npc_id=npc_id,
                memory_retrieval_mode=retrieval_mode,
            )
            status.update(label="Workflow completed", state="complete", expanded=False)
        st.session_state.run_status = "completed"
        st.session_state.status_message = "当前 workflow 已完成。"
        st.session_state.retrieval_preview = []
        st.session_state.lore_preview = []
        st.success("本轮交互已完成。")
    except Exception as exc:
        record_error("Agent workflow", exc)


def record_error(step: str, exc: Exception) -> None:
    st.session_state.run_status = "error"
    st.session_state.last_error = {
        "step": step,
        "message": str(exc),
        "suggestion": build_error_suggestion(step),
        "traceback": traceback.format_exc(),
    }
    st.error(f"{step} failed: {exc}")


def build_error_suggestion(step: str) -> str:
    if "retrieval" in step.lower():
        return "尝试切换检索模式，或点击 Rebuild memory index 后重新预检索。"
    if "workflow" in step.lower():
        return "先查看 Debug 面板中的错误详情；如果状态已混乱，可点击 Reset state 重新开始 demo。"
    return "刷新页面后重试；如果问题仍然存在，请查看错误详情。"


def render_last_run() -> None:
    run = st.session_state.last_run
    if run is None:
        st.info("等待输入。执行一轮后，这里会显示当前 NPC 的回复、workflow 进度和状态变化。")
        return

    st.markdown("#### Latest Turn")
    st.write(f"Player -> {run.npc_id}: {run.player_input}")
    st.success(run.npc_response)

    render_turn_summary(run)

    render_workflow_progress(run.workflow_steps)

    with st.expander("State changes from this turn", expanded=bool(run.state_changes)):
        if run.state_changes:
            for change in run.state_changes:
                st.write(
                    f"{change['scope']}.{change['field']}: "
                    f"{change['before']} -> {change['after']}"
                )
        else:
            st.info("本轮没有改变 SQLite 状态。")


def render_workflow_progress(workflow_steps: list[dict[str, str]]) -> None:
    st.markdown("#### Workflow Progress")
    for index, step in enumerate(workflow_steps, start=1):
        st.markdown(f"**{index}. {step['stage']}**")
        st.caption(step["result"])
        st.progress(index / len(workflow_steps))


def render_turn_summary(run: Any) -> None:
    summary = [
        {
            "项目": "当前意图",
            "含义": explain_intent(run.decision["intent"]),
            "当前值": run.decision["intent"],
        },
        {
            "项目": "检索到的世界观 lore",
            "含义": "本轮 Agent 用来参考的世界观和 NPC 基础设定文档数量。",
            "当前值": len(run.retrieved_lore),
        },
        {
            "项目": "社交意图",
            "含义": "本轮 NPC 的话术策略，不直接拥有工具权限。",
            "当前值": run.decision.get("social_intent", "cooperate"),
        },
        {
            "项目": "社交立场",
            "含义": "本轮社交策略的对象、态度和强度。",
            "当前值": format_social_stance(run.decision.get("social_stance", {})),
        },
        {
            "项目": "检索到的长期记忆",
            "含义": "本轮 Agent 用来参考的长期记忆数量。",
            "当前值": len(run.retrieved_memories),
        },
        {
            "项目": "执行的工具",
            "含义": "本轮实际调用了多少个会修改或记录 SQLite 状态的工具。",
            "当前值": len(run.tool_calls),
        },
        {
            "项目": "状态变化",
            "含义": "本轮造成了多少处 NPC、玩家或任务状态变化。",
            "当前值": len(run.state_changes),
        },
        {
            "项目": "写入长期记忆",
            "含义": "Memory Policy 本轮新写入了多少条长期记忆。",
            "当前值": len(run.memory_writes),
        },
    ]
    st.markdown("#### Turn Summary")
    st.dataframe(summary, use_container_width=True, hide_index=True)


def explain_intent(intent: str) -> str:
    explanations = {
        "general_conversation": "普通对话，不推进任务，不执行关键动作。",
        "start_lost_key_quest": "玩家询问或表示要帮忙找钥匙，开始 lost_key 任务。",
        "complete_lost_key_quest": "玩家归还钥匙，完成 lost_key 任务并提升关系。",
        "reveal_ruins_entrance": "Lina 认为玩家可信，透露地下遗迹入口。",
        "withhold_ruins_entrance": "Lina 暂不信任玩家，拒绝透露地下遗迹入口。",
        "start_gate_badge_quest": "Ron 开始 gate_badge 证据核验任务。",
        "complete_gate_badge_quest": "玩家提供守卫徽章或记录证据，完成 Ron 的任务。",
        "start_ancient_notes_quest": "Mira 开始 ancient_notes 田野笔记任务。",
        "complete_ancient_notes_quest": "玩家提供具体遗迹观察，完成 Mira 的任务。",
        "start_relic_tip_quest": "Sable 开始 relic_tip 诱导/重定向任务。",
        "complete_relic_tip_quest": "玩家透露或接受敏感线索，Sable 记录可疑古物消息。",
        "redirect_ruins_inquiry": "NPC 将遗迹询问重定向到其他线索源。",
        "probe_for_evidence": "NPC 要求证据、动机或更具体信息。",
    }
    return explanations.get(intent, "未知意图。")


def format_social_stance(stance: dict[str, Any]) -> str:
    if not stance:
        return "未记录"
    return (
        f"{stance.get('target', 'player')} / {stance.get('attitude', 'cautious')} / "
        f"{stance.get('intensity', 0)}"
    )


def render_observation_panel() -> None:
    run = st.session_state.last_run
    preview = st.session_state.retrieval_preview
    lore_preview = st.session_state.lore_preview
    memories = run.retrieved_memories if run else preview
    lore = run.retrieved_lore if run else lore_preview

    tabs = st.tabs(["Context", "Memory", "Workflow", "Debug", "Logs"])
    with tabs[0]:
        render_context_panel(run, lore, memories)
    with tabs[1]:
        render_memory_panel(memories, preview_mode=run is None and bool(preview))
    with tabs[2]:
        if run:
            st.table(run.workflow_steps)
            render_tool_results(run)
        else:
            st.info("暂无 workflow。运行一轮后会显示各阶段结果。")
    with tabs[3]:
        render_debug_panel(run)
    with tabs[4]:
        render_logs()


def render_context_panel(run: Any, lore: list[dict[str, Any]], memories: list[dict[str, Any]]) -> None:
    st.markdown("#### Context Inputs")
    recent_context = run.recent_context if run else []
    state_snapshot = run.state_snapshot if run else {}
    st.dataframe(
        [
            {"层": "retrieved_lore", "数量": len(lore), "用途": "世界观、地点规则、NPC基础设定"},
            {"层": "retrieved_memories", "数量": len(memories), "用途": "当前NPC对玩家的长期记忆"},
            {"层": "state_snapshot", "数量": 1 if state_snapshot else 0, "用途": "SQLite当前事实状态"},
            {"层": "recent_context", "数量": len(recent_context), "用途": "最近几轮短期对话"},
        ],
        use_container_width=True,
        hide_index=True,
    )
    if lore:
        st.markdown("#### Retrieved Lore")
        for item in lore:
            render_lore_card(item)
    else:
        st.info("当前没有可展示的 lore 检索结果。")
    with st.expander("State snapshot", expanded=False):
        st.json(state_snapshot)
    with st.expander("Recent context", expanded=False):
        st.json(recent_context)


def render_lore_card(item: dict[str, Any]) -> None:
    score_line = (
        f"retrieval_score={item.get('retrieval_score', '-')} "
        f"semantic_score={item.get('semantic_score', '-')}"
    )
    if item.get("query_embedding_provider"):
        score_line += f" provider={item['query_embedding_provider']}"
    tags = ", ".join(item.get("tags", [])) or "no tags"
    st.markdown(
        f"""
        <div class="memory-card">
            <strong>{item.get('title', item.get('lore_id', 'lore'))}</strong>
            <div>{item.get('excerpt', '')}</div>
            <div class="muted">{score_line}</div>
            <div class="muted">scope={item.get('scope')} tags: {tags}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if item.get("retrieval_reason"):
        st.caption(f"Why selected: {item['retrieval_reason']}")
    fallback_reason = item.get("backend_fallback_reason") or item.get("query_embedding_fallback_reason")
    if fallback_reason:
        st.caption(f"Fallback: {fallback_reason}")


def render_memory_panel(memories: list[dict[str, Any]], preview_mode: bool = False) -> None:
    title = "Memory Preview" if preview_mode else "Retrieved Long-Term Memories"
    st.markdown(f"#### {title}")
    if not memories:
        st.info("当前没有可展示的长期记忆。")
        return

    st.caption(f"本轮检索到 {len(memories)} 条相关长期记忆。")
    for memory in memories:
        render_memory_card(memory)


def render_memory_card(memory: dict[str, Any]) -> None:
    score = memory.get("retrieval_score", "-")
    semantic_score = memory.get("semantic_score")
    score_line = f"retrieval_score={score}"
    if semantic_score is not None:
        score_line += f" semantic_score={semantic_score}"
    if memory.get("retrieval_backend"):
        score_line += f" backend={memory['retrieval_backend']}"
    tags = ", ".join(memory.get("tags", [])) or "no tags"
    st.markdown(
        f"""
        <div class="memory-card">
            <strong>{memory.get('memory_type', 'memory')}</strong>
            <div>{memory.get('content', '')}</div>
            <div class="muted">{score_line}</div>
            <div class="muted">tags: {tags}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reason = memory.get("retrieval_reason") or memory.get("semantic_reason")
    if reason:
        st.caption(f"Why selected: {reason}")
    fallback_reason = memory.get("backend_fallback_reason") or memory.get("query_embedding_fallback_reason")
    if fallback_reason:
        st.caption(f"Fallback: {fallback_reason}")
    if memory.get("score_breakdown"):
        with st.expander("Score breakdown", expanded=False):
            st.json(memory["score_breakdown"])


def render_tool_results(run: Any) -> None:
    st.markdown("#### Tool Results")
    if run.tool_calls:
        for tool in run.tool_calls:
            st.write(f"{tool['name']}: {tool['arguments']}")
    else:
        st.info("本轮没有执行工具。")

    st.markdown("#### Memory Policy")
    st.write(run.memory_policy.get("summary", "No policy summary."))
    with st.expander("Memory policy details", expanded=False):
        st.json(run.memory_policy)


def render_debug_panel(run: Any) -> None:
    if run is None:
        st.info("暂无调试信息。运行一轮后可查看 decision、工具调用和原始 trace。")
        return

    with st.expander("Structured decision", expanded=True):
        st.json(run.decision)
    with st.expander("Raw retrieved lore", expanded=False):
        st.json(run.retrieved_lore)
    with st.expander("Raw retrieved memories", expanded=False):
        st.json(run.retrieved_memories)
    with st.expander("Raw state snapshot", expanded=False):
        st.json(run.state_snapshot)
    with st.expander("Raw tool calls", expanded=False):
        st.json(run.tool_calls)
    with st.expander("Raw memory writes", expanded=False):
        st.json(run.memory_writes)


def render_logs() -> None:
    logs = database.get_interaction_logs(limit=10)
    if not logs:
        st.info("暂无历史记录。")
        return

    export_payload = build_trace_export_payload(limit=10)
    export_path = write_trace_export(limit=10)
    st.caption(f"Trace JSON is also written automatically to {export_path}.")
    st.download_button(
        label="Download Trace JSON",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2),
        file_name="agent_trace_export.json",
        mime="application/json",
        use_container_width=True,
    )

    for log in logs:
        title = f"#{log['id']} - {log['created_at']} - {log['player_input']}"
        with st.expander(title, expanded=False):
            st.write(log["npc_response"])
            cols = st.columns(4)
            cols[0].metric("Lore", len(log["retrieved_lore"]))
            cols[1].metric("Memories", len(log["retrieved_memories"]))
            cols[2].metric("Tools", len(log["tool_calls"]))
            cols[3].metric("Writes", len(log["memory_writes"]))
            nested_tabs = st.tabs(["Workflow", "Memory", "Decision", "State"])
            with nested_tabs[0]:
                st.table(log["workflow_steps"])
                st.json(log["tool_calls"])
            with nested_tabs[1]:
                st.markdown("Lore")
                st.json(log["retrieved_lore"])
                st.markdown("Memories")
                st.json(log["retrieved_memories"])
                st.json(log["memory_policy"])
                st.json(log["memory_writes"])
            with nested_tabs[2]:
                st.json(log["decision"])
            with nested_tabs[3]:
                st.json(log["state_snapshot"])
                st.json(log["state_changes"])


initialize_app()
apply_page_style()

retrieval_mode, paused, selected_npc = render_sidebar()

st.title("Memory-Driven Interactive Character Agent")
st.caption("Multi-NPC context agent with retrieved_lore, retrieved_memories, state_snapshot, recent_context, and visible workflow trace.")
render_global_status(retrieval_mode, selected_npc)

state_col, main_col, observe_col = st.columns([1.05, 1.65, 1.45], gap="large")
with state_col:
    render_state_panel(selected_npc)

with main_col:
    render_interaction_area(retrieval_mode, paused, selected_npc)

with observe_col:
    render_observation_panel()
