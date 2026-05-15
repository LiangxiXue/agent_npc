from __future__ import annotations

import math
import time
from typing import Any

from src.agent.embedding_client import (
    embed_text_with_metadata,
    expected_embedding_identity,
    get_retrieval_backend,
    text_hash,
)
from src.storage import database


def semantic_search_memories(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return memory candidates ranked by embedding cosine similarity."""
    ensure_embeddings_for_memories(npc_id=npc_id)
    query_result = embed_text_with_metadata(player_input)
    rows = database.get_memory_embeddings(npc_id=npc_id)
    requested_backend = get_retrieval_backend()
    if requested_backend == "faiss":
        candidates, fallback_reason = _rank_with_faiss(query_result.vector, rows, limit=limit)
        if candidates is None:
            candidates = _rank_with_sqlite_cosine(query_result.vector, rows, limit=limit)
            backend = "sqlite_cosine"
        else:
            backend = "faiss"
    else:
        fallback_reason = None
        backend = "sqlite_cosine"
        candidates = _rank_with_sqlite_cosine(query_result.vector, rows, limit=limit)

    for candidate in candidates:
        candidate.update(
            {
                "semantic_reason": (
                    "Embedding similarity between the player input and this NPC long-term memory."
                ),
                "embedding_model": candidate["embedding_model"],
                "embedding_provider": candidate.get("embedding_provider", "unknown"),
                "query_embedding_provider": query_result.provider,
                "query_embedding_model": query_result.model,
                "query_embedding_fallback_reason": query_result.fallback_reason,
                "retrieval_backend": backend,
                "requested_retrieval_backend": requested_backend,
                "backend_fallback_reason": fallback_reason,
                "query_embedding_latency_ms": query_result.latency_ms,
            }
        )
    candidates.sort(key=lambda item: (item["semantic_score"], item["memory_id"]), reverse=True)
    return candidates[:limit]


def ensure_embeddings_for_memories(npc_id: str = "lina") -> list[dict[str, Any]]:
    """Build or refresh embeddings when provider, model, or memory text changes."""
    writes = []
    expected_identity = expected_embedding_identity()
    metadata_by_id = database.get_memory_embedding_metadata(npc_id=npc_id)
    for memory in database.get_recent_memories(npc_id=npc_id, limit=1000):
        source_text = _memory_embedding_text(memory)
        source_hash = text_hash(source_text)
        metadata = metadata_by_id.get(memory["id"])
        if metadata and not _embedding_needs_refresh(metadata, source_hash, expected_identity):
            continue
        status = "created" if metadata is None else "refreshed"
        embedding_result = embed_text_with_metadata(source_text)
        database.upsert_memory_embedding(
            memory["id"],
            embedding_result.vector,
            embedding_result.model,
            provider=embedding_result.provider,
            source_text_hash=source_hash,
        )
        writes.append(
            {
                "memory_id": memory["id"],
                "cache_status": status,
                "embedding_provider": embedding_result.provider,
                "requested_embedding_provider": embedding_result.requested_provider,
                "embedding_model": embedding_result.model,
                "embedding_dim": len(embedding_result.vector),
                "source_text_hash": source_hash,
                "fallback_reason": embedding_result.fallback_reason,
                "latency_ms": embedding_result.latency_ms,
            }
        )
    return writes


def ensure_embeddings_for_memory_writes(memory_writes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Index memory records created by Memory Policy without changing policy ownership."""
    indexed = []
    for write in memory_writes:
        result = write.get("result", {})
        memory_id = result.get("id")
        if not memory_id:
            continue
        source_text = _memory_embedding_text(result)
        source_hash = text_hash(source_text)
        embedding_result = embed_text_with_metadata(source_text)
        database.upsert_memory_embedding(
            memory_id,
            embedding_result.vector,
            embedding_result.model,
            provider=embedding_result.provider,
            source_text_hash=source_hash,
        )
        indexed.append(
            {
                "memory_id": memory_id,
                "cache_status": "created",
                "embedding_provider": embedding_result.provider,
                "requested_embedding_provider": embedding_result.requested_provider,
                "embedding_model": embedding_result.model,
                "embedding_dim": len(embedding_result.vector),
                "source_text_hash": source_hash,
                "fallback_reason": embedding_result.fallback_reason,
                "latency_ms": embedding_result.latency_ms,
            }
        )
    return indexed


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _embedding_needs_refresh(
    metadata: dict[str, Any],
    source_hash: str,
    expected_identity: dict[str, Any],
) -> bool:
    if metadata.get("source_text_hash") != source_hash:
        return True
    if metadata.get("embedding_provider") != expected_identity["provider"]:
        return True
    if metadata.get("embedding_model") != expected_identity["model"]:
        return True
    expected_dim = expected_identity.get("dim")
    return expected_dim is not None and int(metadata.get("embedding_dim", 0)) != expected_dim


def _rank_with_sqlite_cosine(
    query_embedding: list[float],
    rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        similarity = cosine_similarity(query_embedding, row["embedding"])
        semantic_score = round(max(similarity, 0.0) * 10.0, 3)
        if semantic_score <= 0:
            continue
        candidates.append(
            {
                "memory_id": row["memory_id"],
                "semantic_score": semantic_score,
                "semantic_similarity": round(similarity, 4),
                "embedding_model": row["embedding_model"],
                "embedding_provider": row.get("embedding_provider", "unknown"),
            }
        )
    candidates.sort(key=lambda item: (item["semantic_score"], item["memory_id"]), reverse=True)
    return candidates[:limit]


def _rank_with_faiss(
    query_embedding: list[float],
    rows: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    started = time.perf_counter()
    if not rows:
        return [], None
    try:
        import faiss
        import numpy as np
    except Exception as exc:
        return None, f"faiss_unavailable: {exc}"

    usable_rows = [row for row in rows if len(row["embedding"]) == len(query_embedding)]
    if not usable_rows:
        return [], None
    vectors = np.array([row["embedding"] for row in usable_rows], dtype="float32")
    query = np.array([query_embedding], dtype="float32")
    faiss.normalize_L2(vectors)
    faiss.normalize_L2(query)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    scores, indices = index.search(query, min(limit, len(usable_rows)))

    candidates = []
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    for score, row_index in zip(scores[0], indices[0]):
        if row_index < 0:
            continue
        semantic_score = round(max(float(score), 0.0) * 10.0, 3)
        if semantic_score <= 0:
            continue
        row = usable_rows[int(row_index)]
        candidates.append(
            {
                "memory_id": row["memory_id"],
                "semantic_score": semantic_score,
                "semantic_similarity": round(float(score), 4),
                "embedding_model": row["embedding_model"],
                "embedding_provider": row.get("embedding_provider", "unknown"),
                "backend_latency_ms": latency_ms,
            }
        )
    return candidates, None


def _memory_embedding_text(memory: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in memory.get("tags", []))
    return f"{memory.get('memory_type', 'event')} {memory.get('content', '')} {tags}"
