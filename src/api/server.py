from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.display_translation import TRANSLATION_CACHE_PATH, translate_debug_text
from src.agent.embedding_client import get_embedding_settings
from src.agent.lore_retrieval import ensure_lore_embeddings, retrieve_lore
from src.agent.llm_client import get_provider_status
from src.agent.semantic_retrieval import ensure_embeddings_for_memories
from src.agent.trace_export import build_trace_export_payload, write_trace_export
from src.agent.workflow import run_agent_turn
from src.storage import database


RetrievalMode = Literal["typed", "hybrid", "semantic", "legacy", "off"]
PreviewMode = Literal["fast", "full"]

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
    preview_mode: PreviewMode = Field(default="fast")


class NpcRequest(BaseModel):
    npc_id: str = Field(default="lina")


class TranslationRequest(BaseModel):
    source: str = Field(default="player_ui")
    text: str = Field(min_length=1, max_length=4000)


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

    if request.preview_mode == "fast":
        lore_started = perf_counter()
        retrieved_lore = retrieve_lore_fast(player_input, npc_id=npc_id)
        timings["lore_preview_ms"] = elapsed_ms(lore_started)
        memory_started = perf_counter()
        retrieved_memories = database.search_memories(
            player_input,
            npc_id=npc_id,
            mode="typed" if request.retrieval_mode in {"hybrid", "semantic"} else request.retrieval_mode,
        )
        timings["memory_preview_ms"] = elapsed_ms(memory_started)
    else:
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


@app.get("/api/trace")
def trace(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    path = write_trace_export(limit=limit)
    return {
        "path": str(path),
        "payload": build_trace_export_payload(limit=limit),
    }


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
        "runtime": {
            "llm": get_provider_status(),
            "embedding": get_embedding_settings(),
            "display_translation": get_display_translation_status(),
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


def retrieve_lore_fast(player_input: str, npc_id: str, limit: int = 5) -> list[dict[str, Any]]:
    documents = database.get_lore_documents(npc_id=npc_id, limit=100)
    keywords = extract_preview_keywords(player_input)
    candidates = []
    for document in documents:
        searchable = f"{document['title']} {document['content']} {' '.join(document['tags'])}".lower()
        matches = [keyword for keyword in keywords if keyword in searchable]
        score = len(matches) * 2.0 + float(document["importance"]) * 0.1
        if matches or document.get("npc_id") == npc_id:
            item = dict(document)
            item.update(
                {
                    "excerpt": " ".join(document["content"].split())[:360],
                    "retrieval_score": round(score, 3),
                    "matched_keywords": matches,
                    "retrieval_reason": "Fast preview keyword/NPC-scope match without embedding calls.",
                    "retrieval_backend": "fast_preview",
                }
            )
            candidates.append(item)
    candidates.sort(key=lambda item: (item["retrieval_score"], item["importance"]), reverse=True)
    return candidates[:limit]


def extract_preview_keywords(text: str) -> list[str]:
    normalized = text.lower()
    aliases = {
        "钥匙": ["钥匙", "key", "找回", "归还"],
        "徽章": ["徽章", "badge", "守卫", "巡逻", "登记"],
        "遗迹": ["遗迹", "ruins", "入口", "underground", "entrance"],
        "笔记": ["笔记", "铭文", "符号", "观察", "notes"],
        "古物": ["古物", "relic", "sable", "线索"],
    }
    keywords = [word.strip("，。！？,.!? ") for word in normalized.split() if word.strip("，。！？,.!? ")]
    for canonical, words in aliases.items():
        if any(word.lower() in normalized for word in words):
            keywords.append(canonical.lower())
            keywords.extend(word.lower() for word in words)
    return sorted(set(keyword for keyword in keywords if keyword))


def elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
