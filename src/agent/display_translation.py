from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from src.agent.llm_client import call_openai_compatible_json, get_llm_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSLATION_CACHE_PATH = PROJECT_ROOT / "data" / "translation_cache.json"
TARGET_LANGUAGE = "zh-CN"
MAX_TRANSLATION_CHARS = 1800

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

DEBUG_TRANSLATION_SYSTEM_PROMPT = """
You translate debug text for a memory-driven NPC agent UI.

Return one JSON object:
{
  "translation_zh": "faithful Simplified Chinese translation"
}

Rules:
- Translate faithfully into Simplified Chinese.
- Do not add facts, causes, emotions, or explanations that are not present.
- Keep names, NPC ids, tool names, enum values, JSON keys, database fields, file paths, and tags unchanged.
- Preserve numbers and quoted evidence.
- If the input is already Chinese or does not need translation, return it unchanged.
- Output only the JSON object.
"""


def translate_debug_text(
    text: Any,
    *,
    source: str = "debug",
    target_language: str = TARGET_LANGUAGE,
) -> dict[str, Any]:
    """Translate display-only debug text using the existing LLM provider and a local cache."""
    source_text = str(text or "").strip()
    if not source_text:
        return {"status": "skipped", "reason": "empty", "translated_text": ""}
    if not looks_like_translatable_english(source_text):
        return {"status": "skipped", "reason": "not_english", "translated_text": source_text}

    settings = get_llm_settings()
    if settings.provider != "openai_compatible" or not settings.api_key:
        return {
            "status": "disabled",
            "reason": "openai_compatible_llm_not_configured",
            "translated_text": "",
            "provider": settings.provider,
        }

    trimmed_text = source_text[:MAX_TRANSLATION_CHARS]
    cache_key = build_cache_key(
        text=trimmed_text,
        source=source,
        target_language=target_language,
        model=settings.model,
    )
    cache = load_translation_cache()
    cached = cache.get(cache_key)
    if cached:
        return {
            "status": "cached",
            "translated_text": cached["translated_text"],
            "provider": cached.get("provider", settings.provider),
            "model": cached.get("model", settings.model),
            "cache_key": cache_key,
            "truncated": len(source_text) > MAX_TRANSLATION_CHARS,
        }

    try:
        payload = call_openai_compatible_json(
            system_prompt=DEBUG_TRANSLATION_SYSTEM_PROMPT,
            user_payload={
                "source": source,
                "target_language": target_language,
                "text": trimmed_text,
            },
            settings=settings,
        )
        translated_text = str(payload.get("translation_zh", "")).strip()
        if not translated_text:
            raise ValueError("Translation response missing translation_zh.")
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "translated_text": "",
            "provider": settings.provider,
            "model": settings.model,
        }

    cache[cache_key] = {
        "source": source,
        "target_language": target_language,
        "source_hash": hash_text(trimmed_text),
        "translated_text": translated_text,
        "provider": settings.provider,
        "model": settings.model,
    }
    save_translation_cache(cache)
    return {
        "status": "translated",
        "translated_text": translated_text,
        "provider": settings.provider,
        "model": settings.model,
        "cache_key": cache_key,
        "truncated": len(source_text) > MAX_TRANSLATION_CHARS,
    }


def looks_like_translatable_english(text: str) -> bool:
    if _CJK_RE.search(text):
        return False
    return bool(_LATIN_RE.search(text)) and len(text.strip()) >= 3


def build_cache_key(
    *,
    text: str,
    source: str,
    target_language: str,
    model: str,
) -> str:
    return hash_text(json.dumps(
        {
            "text": text,
            "source": source,
            "target_language": target_language,
            "model": model,
        },
        ensure_ascii=False,
        sort_keys=True,
    ))


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_translation_cache(path: Path | None = None) -> dict[str, Any]:
    path = path or TRANSLATION_CACHE_PATH
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_translation_cache(cache: dict[str, Any], path: Path | None = None) -> None:
    path = path or TRANSLATION_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)
