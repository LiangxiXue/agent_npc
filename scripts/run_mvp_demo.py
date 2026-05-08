from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.workflow import run_agent_turn  # noqa: E402
from src.storage import database  # noqa: E402


DEMO_INPUTS = [
    "我想打听一下地下遗迹的入口。",
    "我把你丢失的钥匙找回来了。",
    "上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？",
]


def main() -> None:
    database.reset_database()

    for index, player_input in enumerate(DEMO_INPUTS, start=1):
        run = run_agent_turn(player_input)
        print(f"Turn {index}")
        print(f"Player: {run.player_input}")
        print(f"Lina: {run.npc_response}")
        print(f"Intent: {run.decision['intent']}")
        print("Workflow:")
        for step in run.workflow_steps:
            print(f"- {step['stage']}: {step['result']}")
        print("Tool Calls:")
        for tool in run.tool_calls:
            print(f"- {tool['name']}: {tool['arguments']}")
        print("State Changes:")
        for change in run.state_changes:
            print(f"- {change}")
        print()

    print("Final State")
    print(f"NPC: {database.get_npc('lina')}")
    print(f"Quest: {database.get_quest('lost_key')}")
    print(f"Player: {database.get_player_state()}")
    print(f"World Events: {database.get_world_events()}")
    print(f"Interaction Logs: {len(database.get_interaction_logs())}")


if __name__ == "__main__":
    main()
