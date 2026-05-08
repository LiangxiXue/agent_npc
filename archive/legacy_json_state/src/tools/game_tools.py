from __future__ import annotations

"""Legacy JSON-state tools from the first scaffold.

The current MVP path uses src.tools.sqlite_tools so tool calls persist to SQLite.
Keep this module in the archive as a small pure-Python reference/demo.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from src.game.state import GameState, change_npc_number, unlock_location as unlock_state_location


@dataclass(frozen=True)
class ToolResult:
    name: str
    message: str
    changes: dict[str, Any] = field(default_factory=dict)


def add_memory(
    state: GameState,
    npc_id: str,
    content: str,
    importance: int,
    tags: list[str] | None = None,
) -> tuple[GameState, ToolResult]:
    """Store a durable memory that can affect later decisions."""
    next_state = deepcopy(state)
    memory = {
        "npc_id": npc_id,
        "content": content,
        "importance": importance,
        "tags": tags or [],
    }
    next_state.setdefault("memories", []).append(memory)

    result = ToolResult(
        name="add_memory",
        message=f"Added memory for {npc_id}.",
        changes={"memory": memory},
    )
    return next_state, result


def update_trust(state: GameState, npc_id: str, delta: int) -> tuple[GameState, ToolResult]:
    """Change how much an NPC trusts the player."""
    before = state["npcs"][npc_id]["trust"]
    next_state = change_npc_number(state, npc_id, "trust", delta)
    after = next_state["npcs"][npc_id]["trust"]

    result = ToolResult(
        name="update_trust",
        message=f"Updated {npc_id} trust from {before} to {after}.",
        changes={"npc_id": npc_id, "field": "trust", "before": before, "after": after},
    )
    return next_state, result


def update_affection(state: GameState, npc_id: str, delta: int) -> tuple[GameState, ToolResult]:
    """Change how much an NPC likes the player."""
    before = state["npcs"][npc_id]["affection"]
    next_state = change_npc_number(state, npc_id, "affection", delta)
    after = next_state["npcs"][npc_id]["affection"]

    result = ToolResult(
        name="update_affection",
        message=f"Updated {npc_id} affection from {before} to {after}.",
        changes={"npc_id": npc_id, "field": "affection", "before": before, "after": after},
    )
    return next_state, result


def update_quest_status(
    state: GameState,
    npc_id: str,
    quest_status: str,
) -> tuple[GameState, ToolResult]:
    """Update the quest status tracked by one NPC."""
    next_state = deepcopy(state)
    before = next_state["npcs"][npc_id]["quest_status"]
    next_state["npcs"][npc_id]["quest_status"] = quest_status

    result = ToolResult(
        name="update_quest_status",
        message=f"Updated {npc_id} quest status from {before} to {quest_status}.",
        changes={
            "npc_id": npc_id,
            "field": "quest_status",
            "before": before,
            "after": quest_status,
        },
    )
    return next_state, result


def unlock_location(state: GameState, location: str) -> tuple[GameState, ToolResult]:
    """Unlock a location in the player's real state."""
    before = list(state["player"]["unlocked_locations"])
    next_state = unlock_state_location(state, location)
    after = next_state["player"]["unlocked_locations"]

    result = ToolResult(
        name="unlock_location",
        message=f"Unlocked location: {location}.",
        changes={"field": "unlocked_locations", "before": before, "after": after},
    )
    return next_state, result


def record_event(state: GameState, content: str) -> tuple[GameState, ToolResult]:
    """Record a world event for traceability."""
    next_state = deepcopy(state)
    next_state["world"].setdefault("events", []).append(content)

    result = ToolResult(
        name="record_event",
        message="Recorded world event.",
        changes={"event": content},
    )
    return next_state, result
