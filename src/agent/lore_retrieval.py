from __future__ import annotations

from typing import Any

from src.agent.embedding_client import (
    embed_text_with_metadata,
    expected_embedding_identity,
    get_retrieval_backend,
    text_hash,
)
from src.agent.semantic_retrieval import cosine_similarity
from src.storage import database


def retrieve_lore(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve shared world lore plus NPC-specific lore for the current turn."""
    ensure_lore_embeddings(npc_id=npc_id)
    query_result = embed_text_with_metadata(player_input)
    rows = database.get_lore_embeddings(npc_id=npc_id)
    documents_by_id = {
        document["lore_id"]: document
        for document in database.get_lore_documents(npc_id=npc_id, limit=100)
    }
    requested_backend = get_retrieval_backend()

    candidates = []
    for row in rows:
        similarity = cosine_similarity(query_result.vector, row["embedding"])
        semantic_score = round(max(similarity, 0.0) * 10.0, 3)
        if semantic_score <= 0:
            continue
        document = documents_by_id.get(row["lore_id"])
        if not document:
            continue
        excerpt = build_lore_excerpt(document["content"])
        npc_specific_bonus = 1.0 if document.get("npc_id") == npc_id else 0.0
        retrieval_score = round(
            semantic_score + document["importance"] * 0.15 + npc_specific_bonus,
            3,
        )
        candidates.append(
            {
                "lore_id": row["lore_id"],
                "title": document["title"],
                "scope": document["scope"],
                "npc_id": document.get("npc_id"),
                "content": document["content"],
                "excerpt": excerpt,
                "importance": document["importance"],
                "tags": document["tags"],
                "source_path": document["source_path"],
                "retrieval_score": retrieval_score,
                "semantic_score": semantic_score,
                "semantic_similarity": round(similarity, 4),
                "retrieval_reason": "Embedding similarity between the player input and a shared or NPC-specific lore document.",
                "embedding_model": row["embedding_model"],
                "embedding_provider": row.get("embedding_provider", "unknown"),
                "query_embedding_provider": query_result.provider,
                "query_embedding_model": query_result.model,
                "query_embedding_fallback_reason": query_result.fallback_reason,
                "retrieval_backend": "sqlite_cosine",
                "requested_retrieval_backend": requested_backend,
                "backend_fallback_reason": (
                    "lore_retrieval_uses_sqlite_cosine"
                    if requested_backend == "faiss"
                    else None
                ),
                "query_embedding_latency_ms": query_result.latency_ms,
                "score_breakdown": {
                    "semantic_score": semantic_score,
                    "importance_bonus": round(document["importance"] * 0.15, 3),
                    "npc_specific_bonus": npc_specific_bonus,
                    "final_retrieval_score": retrieval_score,
                    "retrieval_backend": "sqlite_cosine",
                },
            }
        )

    candidates.sort(
        key=lambda item: (
            item["retrieval_score"],
            item["importance"],
            item["lore_id"],
        ),
        reverse=True,
    )
    return candidates[:limit]


def ensure_lore_embeddings(npc_id: str | None = None) -> list[dict[str, Any]]:
    """Build or refresh lore embeddings when provider, model, or document text changes."""
    writes = []
    expected_identity = expected_embedding_identity()
    metadata_by_id = database.get_lore_embedding_metadata(npc_id=npc_id)
    for document in database.get_lore_documents(npc_id=npc_id, limit=1000):
        source_text = lore_embedding_text(document)
        source_hash = text_hash(source_text)
        metadata = metadata_by_id.get(document["lore_id"])
        if metadata and not embedding_needs_refresh(metadata, source_hash, expected_identity):
            continue
        status = "created" if metadata is None else "refreshed"
        embedding_result = embed_text_with_metadata(source_text)
        database.upsert_lore_embedding(
            document["lore_id"],
            embedding_result.vector,
            embedding_result.model,
            provider=embedding_result.provider,
            source_text_hash=source_hash,
        )
        writes.append(
            {
                "lore_id": document["lore_id"],
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


def lore_embedding_text(document: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in document.get("tags", []))
    return (
        f"{document.get('scope', 'global')} "
        f"{document.get('npc_id') or 'shared'} "
        f"{document.get('title', '')} "
        f"{document.get('content', '')} "
        f"{tags}"
    )


def embedding_needs_refresh(
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


def build_lore_excerpt(content: str, max_chars: int = 360) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
