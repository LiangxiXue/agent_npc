from __future__ import annotations

from dataclasses import asdict
from html import escape
from time import perf_counter
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.agent.display_translation import TRANSLATION_CACHE_PATH, translate_debug_text
from src.agent.embedding_client import get_embedding_settings
from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.agent.lore_retrieval import ensure_lore_embeddings, retrieve_lore
from src.agent.llm_client import get_provider_status
from src.agent.memory_jobs import process_pending_memory_jobs
from src.agent.player_actions import run_player_action
from src.agent.semantic_retrieval import ensure_embeddings_for_memories
from src.agent.trace_export import build_trace_export_payload, write_trace_export
from src.agent.autonomous_tick import run_autonomous_tick
from src.agent.workflow import run_agent_turn
from src.storage import database


RetrievalMode = Literal["typed", "hybrid", "semantic", "legacy", "off"]
PreviewMode = Literal["full"]

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


class TurnRequest(BaseModel):
    npc_id: str = Field(default="lina")
    player_input: str = Field(min_length=1)
    retrieval_mode: RetrievalMode = Field(default="hybrid")


class PreviewRequest(BaseModel):
    npc_id: str = Field(default="lina")
    player_input: str = Field(min_length=1)
    retrieval_mode: RetrievalMode = Field(default="hybrid")
    preview_mode: PreviewMode = Field(default="full")


class NpcRequest(BaseModel):
    npc_id: str = Field(default="lina")


class MemoryJobRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


class TranslationRequest(BaseModel):
    source: str = Field(default="player_ui")
    text: str = Field(min_length=1, max_length=4000)


class WorldEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)
    source_type: str = Field(min_length=1, max_length=80)
    source_id: str | None = Field(default=None, max_length=120)
    location_id: str | None = Field(default=None, max_length=120)
    visibility: Literal["public", "location", "private", "npc_only"] = Field(default="public")
    payload: dict[str, Any] = Field(default_factory=dict)


class AutonomousTickRequest(BaseModel):
    trigger_event_id: int | None = Field(default=None)
    mode: Literal["llm_constrained", "deterministic_fallback"] = Field(default="llm_constrained")
    retrieval_mode: RetrievalMode = Field(default="hybrid")


class PlayerActionRequest(BaseModel):
    action_type: Literal["investigate_scene", "submit_evidence", "share_rumor", "wait"]
    target_id: str = Field(default="", max_length=120)
    content: str = Field(default="", max_length=4000)
    retrieval_mode: RetrievalMode = Field(default="hybrid")


app = FastAPI(title="Agent NPC Player API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    database.initialize_database()


@app.get("/api/bootstrap")
def bootstrap(
    npc_id: str = Query(default="lina"),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    database.initialize_database()
    selected_npc_id = ensure_npc_id(npc_id)
    return build_client_state(selected_npc_id, limit=limit)


@app.post("/api/turn")
def run_turn(request: TurnRequest) -> dict[str, Any]:
    npc_id = ensure_npc_id(request.npc_id)
    player_input = request.player_input.strip()
    if not player_input:
        raise HTTPException(status_code=400, detail="player_input cannot be empty")

    run = run_agent_turn(
        player_input,
        npc_id=npc_id,
        memory_retrieval_mode=request.retrieval_mode,
    )
    return {
        "run": asdict(run),
        "state": build_client_state(npc_id, limit=10),
    }


@app.post("/api/retrieve-preview")
def retrieve_preview(request: PreviewRequest) -> dict[str, Any]:
    total_started = perf_counter()
    timings: dict[str, float] = {}
    npc_id = ensure_npc_id(request.npc_id)
    player_input = request.player_input.strip()
    if not player_input:
        raise HTTPException(status_code=400, detail="player_input cannot be empty")

    lore_started = perf_counter()
    retrieved_lore = retrieve_lore(player_input, npc_id=npc_id)
    timings["lore_preview_ms"] = elapsed_ms(lore_started)
    memory_started = perf_counter()
    retrieved_memories = database.search_memories(
        player_input,
        npc_id=npc_id,
        mode=request.retrieval_mode,
    )
    timings["memory_preview_ms"] = elapsed_ms(memory_started)
    timings["total_ms"] = elapsed_ms(total_started)
    return {
        "preview_mode": request.preview_mode,
        "retrieved_lore": retrieved_lore,
        "retrieved_memories": retrieved_memories,
        "timings": timings,
    }


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    database.reset_database()
    return build_client_state("lina", limit=10)


@app.post("/api/clear-chat")
def clear_chat(request: NpcRequest) -> dict[str, Any]:
    npc_id = ensure_npc_id(request.npc_id)
    database.clear_interaction_history(npc_id)
    return build_client_state(npc_id, limit=10)


@app.post("/api/rebuild-index")
def rebuild_index(request: NpcRequest) -> dict[str, Any]:
    npc_id = ensure_npc_id(request.npc_id)
    lore_writes = ensure_lore_embeddings(npc_id)
    memory_writes = ensure_embeddings_for_memories(npc_id)
    return {
        "indexed_lore": len(lore_writes),
        "indexed_memories": len(memory_writes),
        "state": build_client_state(npc_id, limit=10),
    }


@app.post("/api/process-memory-jobs")
def process_memory_jobs(request: MemoryJobRequest) -> dict[str, Any]:
    jobs = process_pending_memory_jobs(limit=request.limit)
    return {
        "processed": len(jobs),
        "jobs": [
            {
                "id": job["id"],
                "npc_id": job["npc_id"],
                "status": job["status"],
                "memory_writes": len(job.get("memory_writes", [])),
                "embedding_updates": len(job.get("embedding_updates", [])),
                "error": job.get("error", ""),
            }
            for job in jobs
        ],
        "memory_jobs": database.get_memory_job_counts(),
    }


@app.post("/api/world/events")
def create_world_event(request: WorldEventRequest) -> dict[str, Any]:
    database.initialize_database()
    event = database.create_world_event(
        event_type=request.event_type,
        content=request.content,
        source_type=request.source_type,
        source_id=request.source_id,
        location_id=request.location_id,
        visibility=request.visibility,
        payload=request.payload,
    )
    inbox_items = dispatch_world_event_to_inbox(event)
    return {
        "event": event,
        "inbox_items": inbox_items,
    }


@app.post("/api/player/actions")
def player_action(request: PlayerActionRequest) -> dict[str, Any]:
    database.initialize_database()
    try:
        result = run_player_action(
            action_type=request.action_type,
            target_id=request.target_id,
            content=request.content,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown scene object: {request.target_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    action_result = result["action_result"]
    if not isinstance(action_result, dict):
        action_result = asdict(action_result)
    return {
        "action_result": action_result,
        "created_events": result["created_events"],
        "inbox_items": result["inbox_items"],
        "arc_state": result["arc_state"],
        "state": build_client_state("lina", limit=10),
    }


@app.get("/api/npcs/{npc_id}/inbox")
def npc_inbox(
    npc_id: str,
    include_seen: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    selected_npc_id = ensure_npc_id(npc_id)
    return {
        "npc_id": selected_npc_id,
        "items": database.get_npc_event_inbox(selected_npc_id, include_seen=include_seen, limit=limit),
    }


@app.get("/api/npcs/{npc_id}/runtime")
def npc_runtime(npc_id: str) -> dict[str, Any]:
    selected_npc_id = ensure_npc_id(npc_id)
    return {
        "npc_id": selected_npc_id,
        "runtime": database.get_npc_runtime_state(selected_npc_id),
    }


@app.post("/api/npcs/{npc_id}/tick")
def npc_tick(npc_id: str, request: AutonomousTickRequest) -> dict[str, Any]:
    selected_npc_id = ensure_npc_id(npc_id)
    result = run_autonomous_tick(
        selected_npc_id,
        mode=request.mode,
        trigger_event_id=request.trigger_event_id,
        memory_retrieval_mode=request.retrieval_mode,
    )
    return {
        "result": asdict(result),
        "state": build_client_state(selected_npc_id, limit=10),
    }


@app.get("/api/npcs/messages")
def npc_messages(
    npc_id: str | None = Query(default=None),
    delivered: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    if npc_id is not None:
        ensure_npc_id(npc_id)
    return {
        "messages": database.get_proactive_messages(npc_id=npc_id, delivered=delivered, limit=limit),
    }


@app.post("/api/npcs/messages/{message_id}/delivered")
def mark_message_delivered(message_id: int) -> dict[str, Any]:
    message = database.mark_proactive_message_delivered(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail=f"Proactive message not found: {message_id}")
    return {"message": message}


@app.get("/api/npcs/{npc_id}/plan")
def npc_plan(npc_id: str) -> dict[str, Any]:
    selected_npc_id = ensure_npc_id(npc_id)
    return {
        "npc_id": selected_npc_id,
        "plan": database.get_npc_plan(selected_npc_id),
    }


@app.get("/api/trace")
def trace(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    path = write_trace_export(limit=limit)
    return {
        "path": str(path),
        "payload": build_trace_export_payload(limit=limit),
    }


@app.get("/api/trace/autonomous/{tick_log_id}", response_model=None)
def autonomous_trace(
    tick_log_id: int,
    format: Literal["json", "html"] = Query(default="json"),
):
    tick_log = database.get_autonomous_tick_log(tick_log_id)
    if tick_log is None:
        raise HTTPException(status_code=404, detail=f"Autonomous tick log not found: {tick_log_id}")
    payload = build_autonomous_trace_payload(tick_log)
    if format == "html":
        return HTMLResponse(render_autonomous_trace_html(payload))
    return {"trace": payload}


@app.post("/api/translate-debug")
def translate_debug(request: TranslationRequest) -> dict[str, Any]:
    return translate_debug_text(request.text, source=request.source)


def ensure_npc_id(npc_id: str) -> str:
    npc_ids = {npc["npc_id"] for npc in database.list_npcs()}
    if npc_id not in npc_ids:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return npc_id


def build_client_state(npc_id: str, limit: int = 10) -> dict[str, Any]:
    npcs = database.list_npcs()
    logs = database.get_interaction_logs(limit=limit)
    selected_npc = database.get_npc(npc_id)
    return {
        "npcs": npcs,
        "selected_npc": selected_npc,
        "selected_quest": database.get_primary_quest_for_npc(npc_id),
        "quests": [database.get_primary_quest_for_npc(npc["npc_id"]) for npc in npcs],
        "player": database.get_player_state(),
        "memories": database.get_recent_memories(npc_id=npc_id, limit=20),
        "recent_interactions": database.get_recent_interactions(npc_id=npc_id, limit=20),
        "interaction_logs": [
            log for log in logs if log["npc_id"] == npc_id
        ],
        "world_events": database.get_world_events(limit=12),
        "world_arc": database.get_world_arc_state("ruins_chapter_1"),
        "scene_objects": database.list_scene_objects(),
        "npc_locations": database.list_npc_locations(),
        "npc_routines": database.list_npc_routines(),
        "runtime": {
            "llm": get_provider_status(),
            "embedding": get_embedding_settings(),
            "display_translation": get_display_translation_status(),
            "memory_jobs": database.get_memory_job_counts(),
        },
        "retrieval_modes": [
            {"value": key, "label": label}
            for key, label in RETRIEVAL_LABELS.items()
        ],
        "suggested_inputs": SUGGESTED_INPUTS,
    }


def get_display_translation_status() -> dict[str, Any]:
    provider = get_provider_status()
    return {
        "enabled": provider["provider"] == "openai_compatible" and provider["uses_api_key"],
        "mode": "display-only",
        "cache_path": str(TRANSLATION_CACHE_PATH),
    }


def build_autonomous_trace_payload(tick_log: dict[str, Any]) -> dict[str, Any]:
    message = None
    if tick_log.get("proactive_message_id"):
        message = database.get_proactive_message(int(tick_log["proactive_message_id"]))
    return {
        "id": tick_log["id"],
        "npc_id": tick_log["npc_id"],
        "trigger_event_id": tick_log["trigger_event_id"],
        "mode": tick_log["mode"],
        "observation": tick_log["observation"],
        "retrieved_memories": tick_log["retrieved_memories"],
        "available_actions": tick_log["available_actions"],
        "unavailable_actions": tick_log["unavailable_actions"],
        "llm_decision": tick_log["llm_decision"],
        "proposed_action": tick_log["proposed_action"],
        "validation": tick_log["validation"],
        "action_result": tick_log["action_result"],
        "plan_update": tick_log["plan_update"],
        "memory_candidate": tick_log["memory_candidate"],
        "reflection": tick_log["reflection"],
        "proactive_message": message,
        "created_at": tick_log["created_at"],
    }


def render_autonomous_trace_html(payload: dict[str, Any]) -> str:
    def block(title: str, value: Any) -> str:
        return (
            f"<section><h2>{escape(title)}</h2>"
            f"<pre>{escape(database.json_dumps(value))}</pre></section>"
        )

    title = f"Autonomous Trace #{payload['id']} - {payload['npc_id']}"
    return "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'>",
            f"<title>{escape(title)}</title>",
            "<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.4}"
            "section{border:1px solid #ddd;margin:12px 0;padding:12px;border-radius:6px}"
            "pre{white-space:pre-wrap;background:#f7f7f7;padding:10px}</style>",
            "</head><body>",
            f"<h1>{escape(title)}</h1>",
            block("Observation", payload["observation"]),
            block("Retrieved Memories", payload["retrieved_memories"]),
            block("Available Actions", payload["available_actions"]),
            block("Unavailable Actions", payload["unavailable_actions"]),
            block("LLM Decision", payload["llm_decision"]),
            block("Validation", payload["validation"]),
            block("Action Result", payload["action_result"]),
            block("Plan Update", payload["plan_update"]),
            block("Proactive Message", payload["proactive_message"]),
            "</body></html>",
        ]
    )


def add_run_translations(run: dict[str, Any]) -> dict[str, Any]:
    translated = dict(run)
    translated = add_text_translation(translated, "npc_response", "npc_response_zh", "run:npc_response")
    translated["retrieved_lore"] = add_lore_translations(
        translated.get("retrieved_lore", []),
        "run_lore",
    )
    translated["retrieved_memories"] = add_memory_translations(
        translated.get("retrieved_memories", []),
        "run_memory",
    )
    translated["recent_context"] = add_interaction_translations(
        translated.get("recent_context", [])
    )
    translated["workflow_steps"] = add_workflow_translations(
        translated.get("workflow_steps", [])
    )
    translated["tool_calls"] = add_tool_call_translations(
        translated.get("tool_calls", [])
    )
    translated["memory_writes"] = add_memory_write_translations(
        translated.get("memory_writes", [])
    )
    if isinstance(translated.get("memory_policy"), dict):
        translated["memory_policy"] = add_text_translation(
            translated["memory_policy"],
            "summary",
            "summary_zh",
            "run:memory_policy:summary",
        )
    return translated


def add_trace_translations(payload: dict[str, Any]) -> dict[str, Any]:
    translated = dict(payload)
    logs = translated.get("logs", [])
    if isinstance(logs, list):
        translated["logs"] = [add_log_translations(log) for log in logs]
    return translated


def add_log_translations(log: dict[str, Any]) -> dict[str, Any]:
    translated = dict(log)
    log_id = translated.get("id", "unknown")
    translated = add_text_translation(
        translated,
        "npc_response",
        "npc_response_zh",
        f"log:{log_id}:npc_response",
    )
    translated["retrieved_lore"] = add_lore_translations(
        translated.get("retrieved_lore", []),
        f"log:{log_id}:lore",
    )
    translated["retrieved_memories"] = add_memory_translations(
        translated.get("retrieved_memories", []),
        f"log:{log_id}:memory",
    )
    translated["recent_context"] = add_interaction_translations(
        translated.get("recent_context", [])
    )
    translated["workflow_steps"] = add_workflow_translations(
        translated.get("workflow_steps", [])
    )
    translated["tool_calls"] = add_tool_call_translations(
        translated.get("tool_calls", [])
    )
    translated["memory_writes"] = add_memory_write_translations(
        translated.get("memory_writes", [])
    )
    if isinstance(translated.get("memory_policy"), dict):
        translated["memory_policy"] = add_text_translation(
            translated["memory_policy"],
            "summary",
            "summary_zh",
            f"log:{log_id}:memory_policy:summary",
        )
    return translated


def add_lore_translations(items: list[dict[str, Any]], source_prefix: str) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        source_id = copy.get("lore_id", index)
        copy = add_text_translation(
            copy,
            "excerpt",
            "excerpt_zh",
            f"{source_prefix}:{source_id}:excerpt",
        )
        copy = add_text_translation(
            copy,
            "retrieval_reason",
            "retrieval_reason_zh",
            f"{source_prefix}:{source_id}:retrieval_reason",
        )
        translated.append(copy)
    return translated


def add_memory_translations(items: list[dict[str, Any]], source_prefix: str) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        source_id = copy.get("id", index)
        copy = add_text_translation(
            copy,
            "content",
            "content_zh",
            f"{source_prefix}:{source_id}:content",
        )
        copy = add_text_translation(
            copy,
            "retrieval_reason",
            "retrieval_reason_zh",
            f"{source_prefix}:{source_id}:retrieval_reason",
        )
        copy = add_text_translation(
            copy,
            "semantic_reason",
            "semantic_reason_zh",
            f"{source_prefix}:{source_id}:semantic_reason",
        )
        translated.append(copy)
    return translated


def add_interaction_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        source_id = copy.get("id", index)
        copy = add_text_translation(
            copy,
            "player_input",
            "player_input_zh",
            f"interaction:{source_id}:player_input",
        )
        copy = add_text_translation(
            copy,
            "npc_response",
            "npc_response_zh",
            f"interaction:{source_id}:npc_response",
        )
        translated.append(copy)
    return translated


def add_world_event_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for item in items:
        copy = dict(item)
        copy = add_text_translation(
            copy,
            "content",
            "content_zh",
            f"world_event:{copy.get('id', 'unknown')}:content",
        )
        translated.append(copy)
    return translated


def add_workflow_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        copy = add_text_translation(
            copy,
            "result",
            "result_zh",
            f"workflow:{copy.get('stage', index)}:result",
        )
        translated.append(copy)
    return translated


def add_tool_call_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        result = copy.get("result", copy.get("status", ""))
        if isinstance(result, (dict, list)):
            result = str(result)
        translation = maybe_translate_text(
            result,
            f"tool:{copy.get('name', index)}:{index}:result",
        )
        if translation:
            copy["result_zh"] = translation
        translated.append(copy)
    return translated


def add_memory_write_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for index, item in enumerate(items):
        copy = dict(item)
        arguments = copy.get("arguments")
        if isinstance(arguments, dict):
            translated_arguments = dict(arguments)
            translation = maybe_translate_text(
                translated_arguments.get("content", ""),
                f"memory_write:{index}:content",
            )
            if translation:
                translated_arguments["content_zh"] = translation
            copy["arguments"] = translated_arguments
        translated.append(copy)
    return translated


def add_text_translation(
    item: dict[str, Any],
    field: str,
    translated_field: str,
    source: str,
) -> dict[str, Any]:
    copy = dict(item)
    translation = maybe_translate_text(copy.get(field, ""), source)
    if translation:
        copy[translated_field] = translation
    return copy


def maybe_translate_text(text: Any, source: str) -> str:
    result = translate_debug_text(text, source=source)
    if result.get("status") in {"translated", "cached"}:
        return str(result.get("translated_text", ""))
    return ""


def elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
