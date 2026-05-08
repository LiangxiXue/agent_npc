from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.game.state import get_npc, get_player, load_state  # noqa: E402


def main() -> None:
    state = load_state()
    lina = get_npc(state, "lina")
    player = get_player(state)

    print("NPC State")
    print(f"- name: {lina['name']}")
    print(f"- role: {lina['role']}")
    print(f"- mood: {lina['mood']}")
    print(f"- trust: {lina['trust']}")
    print(f"- affection: {lina['affection']}")
    print(f"- active_quest: {lina['active_quest']}")
    print(f"- quest_status: {lina['quest_status']}")
    print()
    print("Player State")
    print(f"- location: {player['location']}")
    print(f"- inventory: {player['inventory']}")
    print(f"- unlocked_locations: {player['unlocked_locations']}")


if __name__ == "__main__":
    main()
