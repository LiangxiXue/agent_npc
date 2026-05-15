from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import request

from src.agent.llm_client import load_local_env_file


DEFAULT_EMBEDDING_DIM = 64


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    dim: int
    timeout_seconds: float
    allow_fallback: bool
    retrieval_backend: str

    @property
    def is_configured(self) -> bool:
        return self.provider == "mock_hash" or bool(self.api_key)


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str
    requested_provider: str
    fallback_reason: str | None
    latency_ms: float


def get_embedding_settings() -> dict[str, Any]:
    settings = _load_embedding_settings()
    return {
        "provider": settings.provider,
        "model": settings.model,
        "base_url": settings.base_url,
        "configured": settings.is_configured,
        "uses_api_key": bool(settings.api_key),
        "embedding_dim": settings.dim,
        "timeout_seconds": settings.timeout_seconds,
        "allow_fallback": settings.allow_fallback,
        "retrieval_backend": settings.retrieval_backend,
        "faiss_available": is_faiss_available(),
    }


def embed_text(text: str) -> list[float]:
    return embed_text_with_metadata(text).vector


def embed_text_with_metadata(text: str) -> EmbeddingResult:
    settings = _load_embedding_settings()
    started = time.perf_counter()
    if settings.provider == "openai_compatible" and settings.api_key:
        try:
            vector = _embed_openai_compatible(text, settings)
            return EmbeddingResult(
                vector=vector,
                provider="openai_compatible",
                model=settings.model,
                requested_provider=settings.provider,
                fallback_reason=None,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        except Exception as exc:
            if not settings.allow_fallback:
                raise
            vector = _embed_mock_hash(text, settings.dim)
            return EmbeddingResult(
                vector=vector,
                provider="mock_hash",
                model="mock_hash_v1",
                requested_provider=settings.provider,
                fallback_reason=f"openai_compatible_failed: {exc}",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )

    fallback_reason = None
    if settings.provider == "openai_compatible" and not settings.api_key:
        fallback_reason = "openai_compatible_not_configured"
    elif settings.provider != "mock_hash":
        fallback_reason = f"unsupported_provider: {settings.provider}"
    vector = _embed_mock_hash(text, settings.dim)
    return EmbeddingResult(
        vector=vector,
        provider="mock_hash",
        model="mock_hash_v1",
        requested_provider=settings.provider,
        fallback_reason=fallback_reason,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )


def embedding_model_name() -> str:
    settings = _load_embedding_settings()
    return settings.model if settings.provider == "openai_compatible" and settings.api_key else "mock_hash_v1"


def get_retrieval_backend() -> str:
    return _load_embedding_settings().retrieval_backend


def expected_embedding_identity() -> dict[str, Any]:
    settings = _load_embedding_settings()
    if settings.provider == "openai_compatible" and settings.api_key:
        return {
            "provider": "openai_compatible",
            "model": settings.model,
            "dim": None,
        }
    return {
        "provider": "mock_hash",
        "model": "mock_hash_v1",
        "dim": settings.dim,
    }


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        return False
    return True


def _load_embedding_settings() -> EmbeddingSettings:
    load_local_env_file()
    provider = os.environ.get("AGENT_NPC_EMBEDDING_PROVIDER", "mock_hash").strip().lower()
    backend = os.environ.get("AGENT_NPC_RETRIEVAL_BACKEND", "sqlite_cosine").strip().lower()
    return EmbeddingSettings(
        provider=provider,
        model=os.environ.get("AGENT_NPC_EMBEDDING_MODEL", "text-embedding-3-small"),
        base_url=os.environ.get("AGENT_NPC_EMBEDDING_BASE_URL", os.environ.get("AGENT_NPC_LLM_BASE_URL", "https://api.openai.com/v1")),
        api_key=os.environ.get("AGENT_NPC_EMBEDDING_API_KEY")
        or os.environ.get("AGENT_NPC_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY"),
        dim=int(os.environ.get("AGENT_NPC_MOCK_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))),
        timeout_seconds=float(os.environ.get("AGENT_NPC_EMBEDDING_TIMEOUT", "30")),
        allow_fallback=os.environ.get("AGENT_NPC_EMBEDDING_ALLOW_FALLBACK", "1").strip() != "0",
        retrieval_backend=backend if backend in {"sqlite_cosine", "faiss"} else "sqlite_cosine",
    )


def _embed_openai_compatible(text: str, settings: EmbeddingSettings) -> list[float]:
    endpoint = settings.base_url.rstrip("/") + "/embeddings"
    body = {"model": settings.model, "input": text}
    http_request = request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(http_request, timeout=settings.timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [float(value) for value in payload["data"][0]["embedding"]]


def _embed_mock_hash(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token, weight in _semantic_features(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def _semantic_features(text: str) -> list[tuple[str, float]]:
    normalized = text.lower()
    features: list[tuple[str, float]] = []

    for token in _basic_tokens(normalized):
        features.append((f"token:{token}", 1.0))

    concepts = {
        "lost_key": ["lost key", "key", "钥匙", "小铜片", "小铜钥匙", "找回", "归还", "还给"],
        "helped_lina": ["help", "helped", "帮", "帮助", "解决", "处理", "麻烦", "returned"],
        "trust": ["trust", "相信", "信任", "愿意相信", "更信任"],
        "ruins": ["ruins", "underground", "entrance", "遗迹", "地下", "入口", "地点"],
        "sensitive_location": ["sensitive", "secret", "hidden", "隐秘", "敏感", "透露", "保密"],
        "tavern": ["tavern", "酒馆", "后巷", "back alley", "老板", "旅店"],
        "lina": ["lina", "tavern owner", "酒馆老板", "小铜钥匙", "后屋储藏室"],
        "ron": ["ron", "guard", "gate", "patrol", "badge", "守卫", "城门", "巡逻", "徽章"],
        "mira": ["mira", "scholar", "inscription", "field notes", "学者", "铭文", "笔记", "考古"],
        "grayhaven": ["grayhaven", "town", "market square", "镇", "镇广场", "城镇"],
        "preference_direct": ["direct", "直接", "直说", "绕弯", "神神秘秘", "线索"],
        "previous_event": ["previous", "before", "remember", "之前", "上次", "记得", "那件事"],
    }
    for concept, aliases in concepts.items():
        if any(alias in normalized for alias in aliases):
            features.append((f"concept:{concept}", 3.0))

    if any(alias in normalized for alias in ["解决", "处理", "麻烦", "帮过", "帮助"]) and any(
        alias in normalized for alias in ["之前", "上次", "那件事", "previous", "before"]
    ):
        features.append(("concept:helped_lina", 4.0))
        features.append(("concept:previous_event", 3.0))

    return features


def _basic_tokens(text: str) -> list[str]:
    separators = " \t\r\n,.;:!?，。！？、（）()[]{}\"'"
    tokens: list[str] = []
    current = []
    for char in text:
        if char in separators:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return [token for token in tokens if token]
