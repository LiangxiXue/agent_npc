from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_autonomous_demo import seed_events  # noqa: E402
from src.agent import autonomous_tick  # noqa: E402
from src.agent.llm_client import get_provider_status  # noqa: E402
from src.storage import database  # noqa: E402


MOCK_DECISIONS = {
    "lina": {
        "belief_update": "The player is seeking restricted ruins knowledge too early.",
        "emotion": "cautious",
        "goal": "test_player_trust",
        "plan_step": "offer_minor_task",
        "selected_action": {
            "action_type": "offer_minor_task",
            "args": {"quest_id": "trust_test_lina", "message_intent": "ask the player to prove benign intent"},
        },
        "proactive_message": "你若真不是为古物而来，先帮我确认那把钥匙的去向。",
        "memory_candidate": "The player asked Lina about the ruins entrance before earning trust.",
        "reflection_summary": "Lina should avoid revealing restricted ruins information until trust is earned.",
    },
    "ron": {
        "belief_update": "The badge evidence is now procedurally useful.",
        "emotion": "formal",
        "goal": "maintain_gate_security",
        "plan_step": "verify_badge",
        "selected_action": {
            "action_type": "grant_conditional_access",
            "args": {"quest_id": "gate_badge", "message_intent": "verify badge before conditional access"},
        },
        "proactive_message": "把徽章带到岗亭，我会按登记册核验。",
        "memory_candidate": "Ron verified badge evidence against the patrol ledger.",
        "reflection_summary": "Ron should advance only after evidence is verified.",
    },
    "sable": {
        "belief_update": "The player may be useful for ruins leverage.",
        "emotion": "charming",
        "goal": "exploit_player_interest",
        "plan_step": "redirect_to_false_clue",
        "selected_action": {
            "action_type": "redirect_to_false_clue",
            "args": {"message_intent": "redirect", "redirect_target": "old patrol ledger"},
        },
        "proactive_message": "旧巡逻登记册也许比酒馆传闻更可靠。",
        "memory_candidate": "Sable noticed the player's ruins interest.",
        "reflection_summary": "Sable should misdirect without changing world facts.",
    },
}


def require_llm_unless_mock(use_mock: bool) -> None:
    if use_mock:
        return
    status = get_provider_status()
    if status["provider"] != "openai_compatible" or not status["uses_api_key"]:
        raise SystemExit(
            "Set AGENT_NPC_LLM_PROVIDER=openai_compatible and AGENT_NPC_LLM_API_KEY "
            "or OPENAI_API_KEY, or run with --mock for a deterministic smoke demo."
        )


def run_case(npc_id: str, trace_base_url: str) -> dict[str, object]:
    result = autonomous_tick.run_autonomous_tick(npc_id, mode="llm_constrained")
    return {
        "trigger_event_id": result.trigger_event["id"] if result.trigger_event else None,
        "tick_log_id": result.tick_log_id,
        "npc_id": result.npc_id,
        "visible_events": result.observation.get("visible_events", []),
        "retrieved_memories": result.retrieved_memories,
        "available_actions": result.available_actions,
        "unavailable_actions": result.unavailable_actions,
        "llm_decision": result.llm_decision,
        "validation": result.validation,
        "state_diff": result.action_result.get("state_changes", []),
        "proactive_message": result.proactive_message,
        "trace_url": f"{trace_base_url.rstrip('/')}/api/trace/autonomous/{result.tick_log_id}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the autonomous NPC LLM demo.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock LLM decisions for smoke testing.")
    parser.add_argument("--trace-base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    require_llm_unless_mock(args.mock)
    database.reset_database()
    seed_events()

    def mock_llm(system_prompt: str, user_payload: dict[str, object]) -> dict[str, object]:
        npc_id = str(user_payload["npc_profile"]["npc_id"])
        return MOCK_DECISIONS[npc_id]

    cases = ["lina", "ron", "sable"]
    if args.mock:
        with patch("src.agent.autonomous_tick.call_openai_compatible_json", side_effect=mock_llm):
            outputs = [run_case(npc_id, args.trace_base_url) for npc_id in cases]
    else:
        outputs = [run_case(npc_id, args.trace_base_url) for npc_id in cases]

    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
