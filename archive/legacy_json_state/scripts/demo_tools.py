from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.game.state import get_npc, get_player, load_state  # noqa: E402
from src.tools.game_tools import (  # noqa: E402
    add_memory,
    record_event,
    unlock_location,
    update_affection,
    update_quest_status,
    update_trust,
)


def main() -> None:
    state = load_state()
    lina_before = get_npc(state, "lina")
    player_before = get_player(state)

    print("Before tools")
    print(f"- Lina trust: {lina_before['trust']}")
    print(f"- Lina affection: {lina_before['affection']}")
    print(f"- Lina quest_status: {lina_before['quest_status']}")
    print(f"- unlocked_locations: {player_before['unlocked_locations']}")
    print()

    tool_results = []
    state, result = add_memory(
        state,
        npc_id="lina",
        content="Player returned Lina's lost key.",
        importance=8,
        tags=["help", "trust", "lost_key"],
    )
    tool_results.append(result)

    state, result = update_trust(state, npc_id="lina", delta=10)
    tool_results.append(result)

    state, result = update_affection(state, npc_id="lina", delta=8)
    tool_results.append(result)

    state, result = update_quest_status(state, npc_id="lina", quest_status="completed")
    tool_results.append(result)

    state, result = unlock_location(state, location="underground_ruins_entrance")
    tool_results.append(result)

    state, result = record_event(state, "Lina revealed the entrance to the underground ruins.")
    tool_results.append(result)

    lina_after = get_npc(state, "lina")
    player_after = get_player(state)

    print("Tool calls")
    for result in tool_results:
        print(f"- {result.name}: {result.message}")
    print()

    print("After tools")
    print(f"- Lina trust: {lina_after['trust']}")
    print(f"- Lina affection: {lina_after['affection']}")
    print(f"- Lina quest_status: {lina_after['quest_status']}")
    print(f"- unlocked_locations: {player_after['unlocked_locations']}")
    print(f"- memories: {state['memories']}")
    print(f"- world_events: {state['world']['events']}")


if __name__ == "__main__":
    main()
