from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.llm_client import get_provider_status  # noqa: E402
from src.agent.workflow import run_agent_turn  # noqa: E402
from src.storage import database  # noqa: E402


DEMO_TURNS = [
    ("lina", "我想打听一下地下遗迹的入口。"),
    ("lina", "我把你丢失的钥匙找回来了。"),
    ("ron", "我想进入遗迹，守卫这边能放行吗？"),
    ("ron", "我找到守卫徽章了，登记册签名也能对上。"),
    ("mira", "我想问问遗迹铭文和田野笔记该怎么记录。"),
    ("mira", "我看到遗迹门边有三角符号和封闭石门，这是我的一手观察。"),
    ("sable", "Sable，你知道遗迹入口或者古物线索吗？"),
    ("sable", "我听说入口在酒馆后巷，我接受你说的先查换岗记录。"),
]


def require_llm_runtime() -> None:
    status = get_provider_status()
    if status["provider"] != "openai_compatible" or not status["uses_api_key"]:
        raise SystemExit(
            "OpenAI-compatible LLM runtime is required. Set "
            "AGENT_NPC_LLM_PROVIDER=openai_compatible and "
            "AGENT_NPC_LLM_API_KEY or OPENAI_API_KEY before running this demo."
        )


def main() -> None:
    require_llm_runtime()
    database.reset_database()

    for index, (npc_id, player_input) in enumerate(DEMO_TURNS, start=1):
        run = run_agent_turn(player_input, npc_id=npc_id, memory_retrieval_mode="hybrid")
        print(f"Turn {index}")
        print(f"Player -> {run.npc_id}: {run.player_input}")
        print(f"{run.npc_state['name']}: {run.npc_response}")
        print(f"Intent: {run.decision['intent']}")
        print(f"Social: {run.decision.get('social_intent')} / {run.decision.get('social_stance')}")
        mind = run.decision.get("mind", {})
        if mind:
            print("Character Mind:")
            print(f"- Belief stance: {mind.get('belief', {}).get('stance')}")
            print(f"- Active goal: {mind.get('active_goal', {}).get('goal_id')}")
            print(f"- Plan step: {mind.get('active_plan', {}).get('current_step')}")
            print(f"- Mind social strategy: {mind.get('social_strategy')}")
        reflection = run.decision.get("reflection", {})
        if reflection:
            print("Reflection:")
            print(f"- {reflection.get('content')}")
            for plan_update in reflection.get("plan_updates", []):
                print(f"- Plan update: {plan_update}")
        print("Workflow:")
        for step in run.workflow_steps:
            print(f"- {step['stage']}: {step['result']}")
        print("Tool Calls:")
        for tool in run.tool_calls:
            print(f"- {tool['name']}: {tool['arguments']}")
        print("Memory Policy:")
        print(f"- {run.memory_policy['summary']}")
        print("Memory Writes:")
        for memory_write in run.memory_writes:
            print(f"- {memory_write['arguments']}")
        print("State Changes:")
        for change in run.state_changes:
            print(f"- {change}")
        print()

    print("Final State")
    for npc in database.list_npcs():
        print(f"NPC: {database.get_npc(npc['npc_id'])}")
        print(f"Quest: {database.get_primary_quest_for_npc(npc['npc_id'])}")
    print(f"Player: {database.get_player_state()}")
    print(f"World Events: {database.get_world_events()}")
    print(f"Interaction Logs: {len(database.get_interaction_logs())}")


if __name__ == "__main__":
    main()
