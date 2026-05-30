from __future__ import annotations

import json
import traceback
from html import escape
from typing import Any

import streamlit as st

from src.agent.embedding_client import get_embedding_settings
from src.agent.display_translation import TRANSLATION_CACHE_PATH, translate_debug_text
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

STATUS_META = {
    "waiting": ("等待输入", "待机", "等待玩家输入。"),
    "running": ("运行中", "执行", "正在检索上下文、生成决策并写入 trace。"),
    "completed": ("已完成", "完成", "上一轮 workflow 已完成。"),
    "error": ("出错", "异常", "上一轮执行发生错误。"),
}

CONTEXT_LAYER_META = {
    "retrieved_lore": ("世界观资料", "稳定设定、地点规则、NPC 背景"),
    "retrieved_memories": ("长期记忆", "当前 NPC 对玩家过往行为的记忆"),
    "state_snapshot": ("当前事实", "SQLite 中的 NPC、玩家、任务状态"),
    "recent_context": ("短期上下文", "最近几轮对话，用于保持连续性"),
}


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
        "dynamic_translation_enabled": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_page_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --surface: #ffffff;
            --surface-muted: #f8fafc;
            --line: #dbe3ea;
            --line-strong: #b7c5d1;
            --text: #111827;
            --muted: #64748b;
            --accent: #2563eb;
            --ok: #047857;
            --warn: #b45309;
            --danger: #b91c1c;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2.5rem;
            max-width: 1500px;
        }
        div[data-testid="stMetric"] {
            background: var(--surface-muted);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stExpander"] {
            border-radius: 8px;
        }
        div[data-testid="stTextArea"] textarea {
            border-radius: 8px;
            border-color: var(--line-strong);
            min-height: 104px;
        }
        .app-title {
            border-bottom: 1px solid var(--line);
            padding: 0.1rem 0 0.85rem;
            margin-bottom: 0.9rem;
        }
        .app-title h1 {
            margin: 0;
            font-size: 1.7rem;
            line-height: 1.2;
        }
        .app-title p {
            color: var(--muted);
            margin: 0.35rem 0 0;
            font-size: 0.95rem;
        }
        .status-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.6rem;
            margin: 0.5rem 0 1.1rem;
        }
        .status-item {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.75rem 0.85rem;
            background: var(--surface);
            min-height: 104px;
        }
        .status-label {
            color: var(--muted);
            font-size: 0.78rem;
            margin-bottom: 0.2rem;
        }
        .status-value {
            color: var(--text);
            font-size: 0.94rem;
            font-weight: 650;
            line-height: 1.3;
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.12rem 0.5rem;
            font-size: 0.76rem;
            font-weight: 650;
            border: 1px solid var(--line);
            color: var(--accent);
            background: #eff6ff;
            margin-left: 0.35rem;
        }
        .panel-card,
        .memory-card,
        .turn-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.8rem;
            margin-bottom: 0.65rem;
            background: var(--surface);
        }
        .turn-card {
            border-color: #bfdbfe;
            background: #f8fbff;
        }
        .turn-speaker {
            color: var(--muted);
            font-size: 0.82rem;
            font-weight: 650;
            margin-bottom: 0.25rem;
        }
        .turn-text {
            color: var(--text);
            line-height: 1.65;
            white-space: pre-wrap;
        }
        .section-kicker {
            color: var(--muted);
            font-size: 0.82rem;
            font-weight: 650;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .layer-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.25rem 0 0.85rem;
        }
        .layer-card {
            border: 1px solid var(--line);
            border-left: 4px solid var(--accent);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            background: var(--surface);
        }
        .layer-count {
            font-size: 1.15rem;
            font-weight: 720;
            color: var(--text);
            line-height: 1.1;
        }
        .timeline {
            border-left: 2px solid var(--line);
            margin: 0.25rem 0 0.75rem 0.45rem;
            padding-left: 0.9rem;
        }
        .timeline-item {
            position: relative;
            margin-bottom: 0.75rem;
        }
        .timeline-item::before {
            content: "";
            position: absolute;
            left: -1.25rem;
            top: 0.2rem;
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: var(--accent);
            border: 2px solid #ffffff;
        }
        .timeline-title {
            font-weight: 650;
            color: var(--text);
            margin-bottom: 0.1rem;
        }
        .muted {
            color: var(--muted);
            font-size: 0.9rem;
        }
        .translation-note {
            border-left: 3px solid #22c55e;
            background: #f0fdf4;
            color: #14532d;
            margin-top: 0.45rem;
            padding: 0.45rem 0.55rem;
            border-radius: 6px;
            line-height: 1.55;
        }
        .translation-label {
            font-size: 0.78rem;
            font-weight: 700;
            color: #166534;
            margin-right: 0.35rem;
        }
        .compact-list {
            margin: 0.15rem 0 0.2rem 1rem;
            padding: 0;
        }
        .compact-list li {
            margin-bottom: 0.2rem;
        }
        @media (max-width: 1100px) {
            .status-strip,
            .layer-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def h(value: Any) -> str:
    return escape(str(value), quote=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def short_text(value: Any, limit: int = 120) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def dynamic_translation_enabled() -> bool:
    return bool(st.session_state.get("dynamic_translation_enabled", False))


def translation_html(text: Any, source: str) -> str:
    if not dynamic_translation_enabled():
        return ""
    result = translate_debug_text(text, source=source)
    translated_text = result.get("translated_text", "")
    if result.get("status") not in {"translated", "cached"} or not translated_text:
        return ""
    suffix = "（原文较长，仅翻译前段）" if result.get("truncated") else ""
    return (
        '<div class="translation-note">'
        '<span class="translation-label">中文辅助</span>'
        f"{h(translated_text)}{h(suffix)}"
        "</div>"
    )


def render_translation_caption(text: Any, source: str) -> None:
    if not dynamic_translation_enabled():
        return
    result = translate_debug_text(text, source=source)
    translated_text = result.get("translated_text", "")
    if result.get("status") in {"translated", "cached"} and translated_text:
        suffix = "（原文较长，仅翻译前段）" if result.get("truncated") else ""
        st.caption(f"中文辅助：{translated_text}{suffix}")


def render_page_header() -> None:
    st.markdown(
        """
        <div class="app-title">
            <h1>NPC 对话调试台</h1>
            <p>用自然语言跑一轮 Agent，并直接查看它参考了哪些资料、做了什么决策、有没有改状态或写记忆。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def readable_status() -> tuple[str, str]:
    status = st.session_state.run_status
    if st.session_state.paused:
        return "已暂停", "已暂停发送新输入。"
    title, _, help_text = STATUS_META.get(
        status,
        ("未知", "未知", st.session_state.status_message),
    )
    return title, help_text


def render_global_status(retrieval_mode: str, npc_id: str) -> None:
    npc = database.get_npc(npc_id)
    quest = database.get_primary_quest_for_npc(npc_id)
    player = database.get_player_state()
    logs = database.get_interaction_logs(limit=100)
    memories = database.get_recent_memories(npc_id=npc_id, limit=100)
    lore_count = len(database.get_lore_documents(npc_id=npc_id, limit=100))
    status_label, status_help = readable_status()
    if st.session_state.paused:
        status_pill = "暂停"
    else:
        _, status_pill, _ = STATUS_META.get(
            st.session_state.run_status,
            ("未知", "未知", st.session_state.status_message),
        )

    st.markdown(
        f"""
        <div class="status-strip">
            <div class="status-item">
                <div class="status-label">运行状态</div>
                <div class="status-value">{h(status_label)}<span class="status-pill">{h(status_pill)}</span></div>
                <div class="muted">{h(status_help)}</div>
            </div>
            <div class="status-item">
                <div class="status-label">检索模式</div>
                <div class="status-value">{h(RETRIEVAL_LABELS[retrieval_mode])}</div>
                <div class="muted">{'会检索长期记忆并显示分数' if retrieval_mode != 'off' else '当前不使用长期记忆'}</div>
            </div>
            <div class="status-item">
                <div class="status-label">NPC / 任务</div>
                <div class="status-value">{h(npc['name'])} / {h(quest['status'])}</div>
                <div class="muted">信任 {h(npc['trust'])}，好感 {h(npc['affection'])}，立场 {h(npc.get('hidden_alignment', 'neutral'))}</div>
            </div>
            <div class="status-item">
                <div class="status-label">上下文</div>
                <div class="status-value">{lore_count} 条 lore / {len(memories)} 条记忆</div>
                <div class="muted">{len(logs)} 条日志；地点：{h(player['location'])}</div>
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
        st.header("控制台")
        npcs = database.list_npcs()
        npc_ids = [npc["npc_id"] for npc in npcs]
        if st.session_state.selected_npc not in npc_ids:
            st.session_state.selected_npc = npc_ids[0]
        npc_id = st.selectbox(
            "本轮对话对象",
            options=npc_ids,
            index=npc_ids.index(st.session_state.selected_npc),
            format_func=lambda value: next(
                f"{npc['name']} - {npc['role']}" for npc in npcs if npc["npc_id"] == value
            ),
            help="选择本轮交互的 NPC。长期记忆、短期上下文和任务状态按 NPC 隔离。",
        )
        st.session_state.selected_npc = npc_id

        retrieval_mode = st.selectbox(
            "长期记忆检索方式",
            options=["typed", "hybrid", "semantic", "legacy", "off"],
            format_func=lambda value: RETRIEVAL_LABELS[value],
            index=1,
            help="选择本轮长期记忆检索方式。默认推荐 Hybrid RAG 观察语义分数。",
        )

        st.toggle(
            "暂停发送新输入",
            key="paused",
            help="暂停后不会发送新的玩家输入；已保存的状态不受影响。",
        )
        st.toggle(
            "动态内容中文翻译",
            key="dynamic_translation_enabled",
            help="仅翻译页面显示中的英文自然语言值，原始 trace、数据库和 JSON 字段不会被修改。",
        )

        control_left, control_right = st.columns(2)
        with control_left:
            if st.button("重置状态", use_container_width=True):
                database.reset_database()
                st.session_state.last_run = None
                st.session_state.retrieval_preview = []
                st.session_state.lore_preview = []
                st.session_state.run_status = "waiting"
                st.session_state.status_message = "SQLite demo state has been reset."
                st.session_state.last_error = None
                st.toast("Demo 状态已重置。")
        with control_right:
            if st.button("清空对话", use_container_width=True):
                database.clear_interaction_history(npc_id)
                st.session_state.last_run = None
                st.session_state.retrieval_preview = []
                st.session_state.lore_preview = []
                st.session_state.run_status = "waiting"
                st.session_state.status_message = "Conversation context and logs have been cleared."
                st.session_state.last_error = None
                st.toast("对话上下文已清空。")

        if st.button("重建记忆索引", use_container_width=True):
            lore_writes = ensure_lore_embeddings(npc_id)
            writes = ensure_embeddings_for_memories(npc_id)
            st.session_state.status_message = (
                f"Indexed {len(lore_writes)} lore document(s) and {len(writes)} memory record(s)."
            )
            st.toast(f"已索引 {len(lore_writes)} 条 lore + {len(writes)} 条记忆。")

        st.divider()
        st.subheader("运行配置")
        render_runtime_summary()

        st.divider()
        st.subheader("试用输入")
        for index, prompt in enumerate(SUGGESTED_INPUTS, start=1):
            if st.button(prompt, key=f"prompt_{index}", use_container_width=True):
                st.session_state.selected_prompt = prompt

    return retrieval_mode, st.session_state.paused, npc_id


def render_runtime_summary() -> None:
    provider = get_provider_status()
    embedding = get_embedding_settings()
    llm_state = "已配置" if provider["configured"] else "未配置，主回合需要 OpenAI-compatible LLM"
    embedding_state = "可用" if embedding["configured"] else "未配置"
    translation_state = "已启用" if dynamic_translation_enabled() else "已关闭"
    if dynamic_translation_enabled() and not (
        provider["provider"] == "openai_compatible" and provider["uses_api_key"]
    ):
        translation_state = "已开启，但 LLM 未配置；不会自动翻译动态值"
    runtime_rows = [
        {"项目": "LLM", "当前值": provider["provider"], "状态": llm_state},
        {
            "项目": "Embedding",
            "当前值": embedding["provider"],
            "状态": f"{embedding_state}; backend={embedding['retrieval_backend']}",
        },
        {
            "项目": "中文辅助翻译",
            "当前值": "display-only",
            "状态": translation_state,
        },
        {"项目": "FAISS", "当前值": "可用" if embedding["faiss_available"] else "不可用", "状态": "自动回退到 SQLite cosine"},
    ]
    st.dataframe(runtime_rows, use_container_width=True, hide_index=True)
    with st.expander("原始运行配置", expanded=False):
        st.json(
            {
                "llm": provider,
                "embedding": embedding,
                "display_translation": {
                    "enabled": dynamic_translation_enabled(),
                    "cache_path": str(TRANSLATION_CACHE_PATH),
                    "scope": "UI display only; original trace/database values are unchanged.",
                },
            }
        )


def render_state_panel(npc_id: str) -> None:
    npc = database.get_npc(npc_id)
    player = database.get_player_state()
    quest = database.get_primary_quest_for_npc(npc_id)
    world_events = database.get_world_events(limit=5)

    st.subheader("当前状态")
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

    inventory = ", ".join(player["inventory"]) if player["inventory"] else "空"
    locations = ", ".join(player["unlocked_locations"]) if player["unlocked_locations"] else "暂无"
    st.markdown(
        f"""
        <div class="panel-card">
            <div class="section-kicker">Player</div>
            <div><strong>背包</strong>：{h(inventory)}</div>
            <div><strong>已解锁地点</strong>：{h(locations)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if world_events:
        with st.expander("最近世界事件", expanded=False):
            for event in world_events:
                st.write(f"{event['created_at']} - {event['content']}")
                render_translation_caption(event["content"], f"world_event:{event['id']}:content")
    else:
        st.info("暂无世界事件。")


def render_interaction_area(retrieval_mode: str, paused: bool, npc_id: str) -> None:
    st.subheader("对话输入")

    selected_prompt = st.session_state.selected_prompt
    player_input = st.text_area(
        "玩家要说的话",
        value=selected_prompt,
        placeholder=f"对 {database.get_npc(npc_id)['name']} 说些什么...",
        height=110,
        disabled=paused,
    )
    st.session_state.selected_prompt = player_input

    send_col, preview_col, export_col = st.columns([1, 1, 1])
    with send_col:
        send_clicked = st.button(
            "运行一轮",
            type="primary",
            use_container_width=True,
            disabled=paused or not player_input.strip(),
        )
    with preview_col:
        preview_clicked = st.button(
            "先看会检索到什么",
            use_container_width=True,
            disabled=not player_input.strip(),
        )
    with export_col:
        if st.button("导出 trace", use_container_width=True):
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
        with st.status("正在运行 Agent workflow", expanded=True) as status:
            status.write("1. 读取短期上下文、长期记忆和世界观资料。")
            status.write("2. 生成结构化决策。")
            status.write("3. 执行工具并更新 SQLite 状态。")
            status.write("4. 生成 NPC 回复并记录 trace。")
            st.session_state.last_run = run_agent_turn(
                player_input,
                npc_id=npc_id,
                memory_retrieval_mode=retrieval_mode,
            )
            status.update(label="Workflow 已完成", state="complete", expanded=False)
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

    st.markdown("#### 最新一轮")
    npc = database.get_npc(run.npc_id)
    st.markdown(
        f"""
        <div class="turn-card">
            <div class="turn-speaker">玩家 -> {h(npc['name'])}</div>
            <div class="turn-text">{h(run.player_input)}</div>
        </div>
        <div class="turn-card">
            <div class="turn-speaker">{h(npc['name'])} 的回复</div>
            <div class="turn-text">{h(run.npc_response)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_turn_summary(run)

    render_workflow_progress(run.workflow_steps)

    with st.expander("本轮状态变化", expanded=bool(run.state_changes)):
        if run.state_changes:
            st.dataframe(
                [
                    {
                        "对象": f"{change['scope']}.{change['field']}",
                        "之前": change["before"],
                        "之后": change["after"],
                    }
                    for change in run.state_changes
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("本轮没有改变 SQLite 状态。")


def render_workflow_progress(workflow_steps: list[dict[str, str]]) -> None:
    st.markdown("#### Workflow 时间线")
    if not workflow_steps:
        st.info("没有 workflow 步骤。")
        return
    html = ['<div class="timeline">']
    for index, step in enumerate(workflow_steps, start=1):
        result = step["result"]
        translated_result = translation_html(result, f"workflow:{step['stage']}")
        html.append(
            f"""
            <div class="timeline-item">
                <div class="timeline-title">{index}. {h(step['stage'])}</div>
                <div class="muted">{h(result)}</div>
                {translated_result}
            </div>
            """
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_turn_summary(run: Any) -> None:
    summary = [
        {
            "检查项": "当前意图",
            "这代表什么": explain_intent(run.decision["intent"]),
            "当前值": run.decision["intent"],
        },
        {
            "检查项": "检索到的世界观 lore",
            "这代表什么": "本轮 Agent 用来参考的世界观和 NPC 基础设定文档数量。",
            "当前值": len(run.retrieved_lore),
        },
        {
            "检查项": "社交意图",
            "这代表什么": "本轮 NPC 的话术策略，不直接拥有工具权限。",
            "当前值": run.decision.get("social_intent", "cooperate"),
        },
        {
            "检查项": "社交立场",
            "这代表什么": "本轮社交策略的对象、态度和强度。",
            "当前值": format_social_stance(run.decision.get("social_stance", {})),
        },
        {
            "检查项": "检索到的长期记忆",
            "这代表什么": "本轮 Agent 用来参考的长期记忆数量。",
            "当前值": len(run.retrieved_memories),
        },
        {
            "检查项": "执行的工具",
            "这代表什么": "本轮实际调用了多少个会修改或记录 SQLite 状态的工具。",
            "当前值": len(run.tool_calls),
        },
        {
            "检查项": "状态变化",
            "这代表什么": "本轮造成了多少处 NPC、玩家或任务状态变化。",
            "当前值": len(run.state_changes),
        },
        {
            "检查项": "写入长期记忆",
            "这代表什么": "Memory Policy 本轮新写入了多少条长期记忆。",
            "当前值": len(run.memory_writes),
        },
    ]
    st.markdown("#### 本轮诊断摘要")
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

    tabs = st.tabs(["上下文", "长期记忆", "执行过程", "原始调试", "历史日志"])
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
    st.markdown("#### Agent 本轮看到的信息")
    recent_context = run.recent_context if run else []
    state_snapshot = run.state_snapshot if run else {}
    layer_counts = {
        "retrieved_lore": len(lore),
        "retrieved_memories": len(memories),
        "state_snapshot": 1 if state_snapshot else 0,
        "recent_context": len(recent_context),
    }
    layer_html = ['<div class="layer-grid">']
    for key, count in layer_counts.items():
        title, desc = CONTEXT_LAYER_META[key]
        layer_html.append(
            f"""
            <div class="layer-card">
                <div class="layer-count">{count}</div>
                <div><strong>{h(title)}</strong></div>
                <div class="muted">{h(key)}：{h(desc)}</div>
            </div>
            """
        )
    layer_html.append("</div>")
    st.markdown("".join(layer_html), unsafe_allow_html=True)
    st.caption(
        "这四层会一起进入决策和回复阶段。数量为 0 不一定是错误，但它能解释为什么 NPC 没有引用某些背景或记忆。"
    )
    if lore:
        st.markdown("#### 本轮命中的世界观资料")
        for item in lore:
            render_lore_card(item)
    else:
        st.info("当前没有可展示的 lore 检索结果。")
    with st.expander("当前事实状态 state_snapshot", expanded=False):
        st.json(state_snapshot)
    with st.expander("短期上下文 recent_context", expanded=False):
        st.json(recent_context)


def render_lore_card(item: dict[str, Any]) -> None:
    score_line = (
        f"retrieval_score={item.get('retrieval_score', '-')} "
        f"semantic_score={item.get('semantic_score', '-')}"
    )
    if item.get("query_embedding_provider"):
        score_line += f" provider={item['query_embedding_provider']}"
    tags = ", ".join(item.get("tags", [])) or "no tags"
    excerpt = item.get("excerpt", "")
    translated_excerpt = translation_html(excerpt, f"lore:{item.get('lore_id', 'unknown')}:excerpt")
    st.markdown(
        f"""
        <div class="memory-card">
            <strong>{h(item.get('title', item.get('lore_id', 'lore')))}</strong>
            <div>{h(excerpt)}</div>
            {translated_excerpt}
            <div class="muted">{h(score_line)}</div>
            <div class="muted">scope={h(item.get('scope'))} tags: {h(tags)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if item.get("retrieval_reason"):
        st.caption(f"为什么命中：{item['retrieval_reason']}")
        render_translation_caption(item["retrieval_reason"], f"lore:{item.get('lore_id', 'unknown')}:retrieval_reason")
    fallback_reason = item.get("backend_fallback_reason") or item.get("query_embedding_fallback_reason")
    if fallback_reason:
        st.caption(f"回退原因：{fallback_reason}")


def render_memory_panel(memories: list[dict[str, Any]], preview_mode: bool = False) -> None:
    title = "预检索结果" if preview_mode else "本轮使用的长期记忆"
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
    facets = ", ".join(memory.get("facets", [])) or "no facets"
    content = memory.get("content", "")
    translated_content = translation_html(content, f"memory:{memory.get('id', 'unknown')}:content")
    st.markdown(
        f"""
        <div class="memory-card">
            <strong>{h(memory.get('memory_type', 'memory'))}</strong>
            <div>{h(content)}</div>
            {translated_content}
            <div class="muted">{h(score_line)}</div>
            <div class="muted">scope: {h(memory.get('scope', 'npc_specific'))}</div>
            <div class="muted">facets: {h(facets)}</div>
            <div class="muted">tags: {h(tags)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reason = memory.get("retrieval_reason") or memory.get("semantic_reason")
    if reason:
        st.caption(f"为什么命中：{reason}")
        render_translation_caption(reason, f"memory:{memory.get('id', 'unknown')}:retrieval_reason")
    fallback_reason = memory.get("backend_fallback_reason") or memory.get("query_embedding_fallback_reason")
    if fallback_reason:
        st.caption(f"回退原因：{fallback_reason}")
    if memory.get("score_breakdown"):
        with st.expander("分数细节", expanded=False):
            st.json(memory["score_breakdown"])


def render_tool_results(run: Any) -> None:
    st.markdown("#### 工具调用")
    if run.tool_calls:
        st.dataframe(
            [
                {
                    "工具": tool["name"],
                    "参数": compact_json(tool.get("arguments", {})),
                    "结果": short_text(tool.get("result", tool.get("status", "")), 180),
                }
                for tool in run.tool_calls
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("本轮没有执行工具。")
    render_tool_result_translations(run.tool_calls)

    st.markdown("#### 记忆写入策略")
    policy_summary = run.memory_policy.get("summary", "No policy summary.")
    st.write(policy_summary)
    render_translation_caption(policy_summary, "memory_policy:summary")
    if run.memory_writes:
        st.dataframe(run.memory_writes, use_container_width=True)
        render_memory_write_translations(run.memory_writes)
    with st.expander("记忆策略原始详情", expanded=False):
        st.json(run.memory_policy)


def render_tool_result_translations(tool_calls: list[dict[str, Any]]) -> None:
    if not dynamic_translation_enabled():
        return
    translated_rows = []
    for index, tool in enumerate(tool_calls, start=1):
        result = tool.get("result", tool.get("status", ""))
        if isinstance(result, (dict, list)):
            result = compact_json(result)
        translation = translate_debug_text(result, source=f"tool:{tool.get('name', 'unknown')}:{index}:result")
        if translation.get("status") in {"translated", "cached"} and translation.get("translated_text"):
            translated_rows.append(
                {
                    "工具": tool.get("name", "unknown"),
                    "原始结果": short_text(result, 120),
                    "中文辅助": translation["translated_text"],
                }
            )
    if translated_rows:
        with st.expander("工具结果中文辅助", expanded=False):
            st.dataframe(translated_rows, use_container_width=True, hide_index=True)


def render_memory_write_translations(memory_writes: list[dict[str, Any]]) -> None:
    if not dynamic_translation_enabled():
        return
    rows = []
    for index, write in enumerate(memory_writes, start=1):
        arguments = write.get("arguments", {})
        content = arguments.get("content", "") if isinstance(arguments, dict) else ""
        translation = translate_debug_text(content, source=f"memory_write:{index}:content")
        if translation.get("status") in {"translated", "cached"} and translation.get("translated_text"):
            rows.append(
                {
                    "类型": arguments.get("memory_type", "memory"),
                    "原文": content,
                    "中文辅助": translation["translated_text"],
                }
            )
    if rows:
        with st.expander("写入记忆中文辅助", expanded=True):
            st.dataframe(rows, use_container_width=True, hide_index=True)


def render_debug_panel(run: Any) -> None:
    if run is None:
        st.info("暂无调试信息。运行一轮后可查看 decision、工具调用和原始 trace。")
        return

    st.caption("这里保留给排查问题使用。普通阅读可以先看“上下文 / 长期记忆 / 执行过程”三个标签。")
    with st.expander("结构化决策 decision", expanded=True):
        st.json(run.decision)
    with st.expander("原始 retrieved_lore", expanded=False):
        st.json(run.retrieved_lore)
    with st.expander("原始 retrieved_memories", expanded=False):
        st.json(run.retrieved_memories)
    with st.expander("原始 state_snapshot", expanded=False):
        st.json(run.state_snapshot)
    with st.expander("原始 tool_calls", expanded=False):
        st.json(run.tool_calls)
    with st.expander("原始 memory_writes", expanded=False):
        st.json(run.memory_writes)


def render_logs() -> None:
    logs = database.get_interaction_logs(limit=10)
    if not logs:
        st.info("暂无历史记录。")
        return

    export_payload = build_trace_export_payload(limit=10)
    export_path = write_trace_export(limit=10)
    st.caption(f"Trace JSON 会同步写入：{export_path}")
    st.download_button(
        label="下载 Trace JSON",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2),
        file_name="agent_trace_export.json",
        mime="application/json",
        use_container_width=True,
    )

    for log in logs:
        title = f"#{log['id']} - {log['created_at']} - {log['player_input']}"
        with st.expander(title, expanded=False):
            st.markdown(
                f"""
                <div class="turn-card">
                    <div class="turn-speaker">NPC 回复</div>
                    <div class="turn-text">{h(log["npc_response"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.dataframe(
                [
                    {"检查项": "世界观资料", "数量": len(log["retrieved_lore"])},
                    {"检查项": "长期记忆", "数量": len(log["retrieved_memories"])},
                    {"检查项": "工具调用", "数量": len(log["tool_calls"])},
                    {"检查项": "记忆写入", "数量": len(log["memory_writes"])},
                ],
                use_container_width=True,
                hide_index=True,
            )
            nested_tabs = st.tabs(["执行过程", "记忆证据", "决策", "状态"])
            with nested_tabs[0]:
                st.table(log["workflow_steps"])
                st.json(log["tool_calls"])
            with nested_tabs[1]:
                if log["retrieved_lore"] or log["retrieved_memories"] or log["memory_writes"]:
                    st.markdown("中文辅助视图")
                    for item in log["retrieved_lore"]:
                        render_lore_card(item)
                    for memory in log["retrieved_memories"]:
                        render_memory_card(memory)
                    render_memory_write_translations(log["memory_writes"])
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

render_page_header()
render_global_status(retrieval_mode, selected_npc)

main_col, state_col = st.columns([1.65, 1.0], gap="large")
with main_col:
    render_interaction_area(retrieval_mode, paused, selected_npc)

with state_col:
    render_state_panel(selected_npc)

st.divider()
st.subheader("调试证据")
render_observation_panel()
