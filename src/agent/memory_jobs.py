from __future__ import annotations

from typing import Any

from src.agent.memory_policy import MemoryPolicyInput, apply_memory_policy
from src.agent.semantic_retrieval import ensure_embeddings_for_memory_writes
from src.storage import database


def enqueue_memory_job(
    npc_id: str,
    player_input: str,
    npc_response: str,
    recent_context: list[dict[str, Any]],
    retrieved_lore: list[dict[str, Any]],
    retrieved_memories: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist a non-blocking long-term memory job for later processing."""
    return database.add_memory_job(
        npc_id=npc_id,
        player_input=player_input,
        npc_response=npc_response,
        recent_context=recent_context,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        state_before=state_before,
        state_after=state_after,
        tool_calls=tool_calls,
        state_changes=state_changes,
    )


def process_pending_memory_jobs(limit: int = 10) -> list[dict[str, Any]]:
    database.initialize_database()
    results = []
    for job in database.get_pending_memory_jobs(limit=limit):
        results.append(process_memory_job(job))
    return results


def process_memory_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        state_before = job["state_before"]
        state_after = job["state_after"]
        policy, memory_writes = apply_memory_policy(
            MemoryPolicyInput(
                npc_id=job["npc_id"],
                player_input=job["player_input"],
                npc_response=job["npc_response"],
                retrieved_lore=job["retrieved_lore"],
                retrieved_long_term_memories=job["retrieved_memories"],
                recent_short_term_context=job["recent_context"],
                npc_before=state_before["npc"],
                npc_after=state_after["npc"],
                player_before=state_before["player"],
                player_after=state_after["player"],
                quest_before=state_before["quest"],
                quest_after=state_after["quest"],
                tool_calls=job["tool_calls"],
                state_changes=job["state_changes"],
            )
        )
        embedding_updates = ensure_embeddings_for_memory_writes(memory_writes)
        policy["embedding_updates"] = embedding_updates
        status = "indexed" if memory_writes else "written"
        return database.update_memory_job_result(
            job["id"],
            status=status,
            memory_policy=policy,
            memory_writes=memory_writes,
            embedding_updates=embedding_updates,
        )
    except Exception as exc:
        return database.update_memory_job_result(
            job["id"],
            status="failed",
            error=str(exc),
        )
