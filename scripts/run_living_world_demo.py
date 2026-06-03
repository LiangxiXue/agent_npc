from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import autonomous_tick  # noqa: E402
from src.agent.arc_director import run_arc_director  # noqa: E402
from src.agent.llm_client import get_provider_status  # noqa: E402
from src.agent.player_actions import run_player_action  # noqa: E402
from src.storage import database  # noqa: E402


MOCK_DECISIONS = {
    "lina": {
        "goal": "protect_tavern_back_alley",
        "plan_step": "secure_tavern_back_alley",
        "selected_action": {
            "action_type": "secure_tavern_back_alley",
            "args": {"message_intent": "warn without revealing the entrance"},
        },
        "proactive_message": "后巷的事别在大厅里问。先证明你不是替古物贩子探路。",
        "memory_candidate": "Player investigated the tavern back alley during ruins rumors.",
        "reflection_summary": "Lina should secure the alley and test trust.",
    },
    "ron": {
        "goal": "contain_ruins_risk",
        "plan_step": "patrol_sensitive_route",
        "selected_action": {
            "action_type": "patrol_sensitive_route",
            "args": {"route_id": "tavern_to_guard_post", "message_intent": "verify movement"},
        },
        "proactive_message": "我会核对岗亭和酒馆之间的路线。没有证据前，不要再扩散入口传闻。",
        "memory_candidate": "Ron linked ruins rumors to route security.",
        "reflection_summary": "Ron should patrol without granting access.",
    },
    "mira": {
        "goal": "ground_ruins_research",
        "plan_step": "request_field_notes",
        "selected_action": {
            "action_type": "request_field_notes",
            "args": {"note_focus": "symbols and door condition", "message_intent": "ask for grounded notes"},
        },
        "proactive_message": "如果你确实看见了石门和符号，把位置、形状和是否一手观察写清楚。",
        "memory_candidate": "Mira asked for grounded field notes before drawing conclusions.",
        "reflection_summary": "Mira should preserve evidence without treating rumor as fact.",
    },
    "sable": {
        "goal": "exploit_ruins_rumor",
        "plan_step": "plant_misleading_tip",
        "selected_action": {
            "action_type": "plant_misleading_tip",
            "args": {"rumor_theme": "guard_shift", "message_intent": "redirect toward patrol records"},
        },
        "proactive_message": "想找入口，不如先看换岗记录。守卫嘴上严，纸面上可不一定。",
        "memory_candidate": "Sable used the rumor to redirect the player toward exploitable records.",
        "reflection_summary": "Sable can gain leverage through rumor without changing world facts.",
    },
}


def require_llm_unless_mock(use_mock: bool) -> None:
    if use_mock:
        return
    status = get_provider_status()
    if status["provider"] != "openai_compatible" or not status["uses_api_key"]:
        raise SystemExit(
            "Set AGENT_NPC_LLM_PROVIDER=openai_compatible and AGENT_NPC_LLM_API_KEY "
            "or run with --mock for deterministic output."
        )


def run_player_sequence() -> list[dict[str, object]]:
    actions = [
        ("investigate_scene", "tavern_back_alley", "玩家查看酒馆后巷的旧墙缝和脚印。"),
        ("submit_evidence", "guard_ledger", "玩家提交换岗记录里缺失的一页作为证据。"),
        ("submit_evidence", "mira_field_notes", "玩家记录石门旁的三角符号和封闭状态。"),
        ("share_rumor", "sable_rumor_stall", "玩家在黑市摊位重复了后巷入口的传闻。"),
        ("wait", "", "玩家等待 NPC 自主反应。"),
    ]
    outputs = []
    for action_type, target_id, content in actions:
        result = run_player_action(action_type=action_type, target_id=target_id, content=content)
        action_result = result["action_result"]
        outputs.append(
            {
                "action_type": action_type,
                "target_id": target_id,
                "status": action_result.status,
                "created_event_ids": [event["id"] for event in result["created_events"]],
                "created_event_types": [event["event_type"] for event in result["created_events"]],
            }
        )
    return outputs


def run_tick(npc_id: str, trace_base_url: str) -> dict[str, object]:
    result = autonomous_tick.run_autonomous_tick(npc_id, mode="llm_constrained")
    return {
        "npc_id": npc_id,
        "outcome": result.outcome,
        "trigger_event_id": result.trigger_event["id"] if result.trigger_event else None,
        "selected_action": result.proposed_action.get("action_type"),
        "validation": result.validation,
        "proactive_message": result.proactive_message,
        "arc_outcome": result.observation.get("arc_director", {}).get("arc_outcome"),
        "trace_url": f"{trace_base_url.rstrip('/')}/api/trace/autonomous/{result.tick_log_id}?format=html",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the living world ruins chapter demo.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock autonomous NPC decisions.")
    parser.add_argument("--trace-base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    require_llm_unless_mock(args.mock)
    database.reset_database()
    player_actions = run_player_sequence()

    def mock_llm(system_prompt: str, user_payload: dict[str, object]) -> dict[str, object]:
        npc_id = str(user_payload["npc_profile"]["npc_id"])
        return MOCK_DECISIONS[npc_id]

    if args.mock:
        with patch("src.agent.autonomous_tick.call_openai_compatible_json", side_effect=mock_llm):
            tick_results = [run_tick(npc_id, args.trace_base_url) for npc_id in ["lina", "ron", "mira", "sable"]]
    else:
        tick_results = [run_tick(npc_id, args.trace_base_url) for npc_id in ["lina", "ron", "mira", "sable"]]

    final_arc = run_arc_director(use_llm=False)
    output = {
        "player_actions": player_actions,
        "npc_ticks": tick_results,
        "final_arc": final_arc,
        "proactive_messages": database.get_proactive_messages(delivered=False, limit=20),
        "player_state": database.get_player_state(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
