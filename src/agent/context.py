from __future__ import annotations

from typing import Any

from src.agent.lore_retrieval import retrieve_lore
from src.storage import database


def build_state_snapshot(
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "npc": {
            "npc_id": npc_state["npc_id"],
            "name": npc_state["name"],
            "role": npc_state["role"],
            "mood": npc_state["mood"],
            "trust": npc_state["trust"],
            "affection": npc_state["affection"],
        },
        "player": {
            "location": player_state["location"],
            "inventory": player_state["inventory"],
            "unlocked_locations": player_state["unlocked_locations"],
        },
        "quest": {
            "quest_id": quest_state["quest_id"],
            "title": quest_state["title"],
            "status": quest_state["status"],
        },
    }


def build_context_inputs(
    player_input: str,
    npc_id: str,
    memory_retrieval_mode: str,
    memory_limit: int = 5,
    lore_limit: int = 5,
) -> dict[str, Any]:
    """Build the explicit context layers used by decision, response, and trace output."""
    recent_context = database.get_recent_interactions(npc_id=npc_id, limit=5)
    retrieved_memories = database.search_memories(
        player_input,
        npc_id=npc_id,
        limit=memory_limit,
        mode=memory_retrieval_mode,
    )
    retrieved_lore = retrieve_lore(
        player_input,
        npc_id=npc_id,
        limit=lore_limit,
    )
    npc_state = database.get_npc(npc_id)
    player_state = database.get_player_state()
    quest_state = database.get_primary_quest_for_npc(npc_id)
    state_snapshot = build_state_snapshot(npc_state, player_state, quest_state)
    return {
        "retrieved_lore": retrieved_lore,
        "retrieved_memories": retrieved_memories,
        "state_snapshot": state_snapshot,
        "recent_context": recent_context,
    }
