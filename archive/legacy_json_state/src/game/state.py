from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "data" / "initial_state.json"


GameState = dict[str, Any]


def load_state(path: str | Path = DEFAULT_STATE_PATH) -> GameState:
    """Load the persisted game/agent state from JSON."""
    state_path = Path(path)
    with state_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state: GameState, path: str | Path = DEFAULT_STATE_PATH) -> None:
    """Persist the game/agent state to JSON."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_npc(state: GameState, npc_id: str) -> dict[str, Any]:
    """Return one NPC state by id."""
    try:
        return state["npcs"][npc_id]
    except KeyError as exc:
        raise KeyError(f"NPC not found: {npc_id}") from exc


def get_player(state: GameState) -> dict[str, Any]:
    """Return the player state."""
    return state["player"]


def update_npc_value(state: GameState, npc_id: str, field: str, value: Any) -> GameState:
    """Return a new state with one NPC field updated."""
    next_state = deepcopy(state)
    next_state["npcs"][npc_id][field] = value
    return next_state


def change_npc_number(state: GameState, npc_id: str, field: str, delta: int) -> GameState:
    """Return a new state after changing a numeric NPC field."""
    next_state = deepcopy(state)
    current_value = next_state["npcs"][npc_id].get(field)
    if not isinstance(current_value, int):
        raise TypeError(f"NPC field must be an integer: {field}")
    next_state["npcs"][npc_id][field] = current_value + delta
    return next_state


def add_player_item(state: GameState, item: str) -> GameState:
    """Return a new state with an item added to the player inventory."""
    next_state = deepcopy(state)
    inventory = next_state["player"]["inventory"]
    if item not in inventory:
        inventory.append(item)
    return next_state


def unlock_location(state: GameState, location: str) -> GameState:
    """Return a new state with a location unlocked for the player."""
    next_state = deepcopy(state)
    unlocked_locations = next_state["player"]["unlocked_locations"]
    if location not in unlocked_locations:
        unlocked_locations.append(location)
    return next_state
