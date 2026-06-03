import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.storage import database


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_autonomous_tick.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
    os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
    database.reset_database()


def create_and_dispatch_event(
    event_type: str,
    content: str,
    npc_id: str,
    visibility: str = "npc_only",
) -> dict[str, object]:
    event = database.create_world_event(
        event_type=event_type,
        content=content,
        source_type="system",
        source_id="test",
        location_id="tavern",
        visibility=visibility,
        payload={"target_npc_ids": [npc_id]},
    )
    dispatch_world_event_to_inbox(event)
    return event


class AutonomousTickTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_lina_llm_constrained_tick_queues_message_and_logs_trace(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        event = create_and_dispatch_event(
            "player_asked_ruins_too_early",
            "Player asked Lina about the ruins entrance before earning trust.",
            "lina",
        )
        database.add_memory(
            npc_id="lina",
            content="Player previously hid the source of a badge rumor.",
            importance=6,
            memory_type="episodic",
            tags=["trust", "badge"],
        )
        llm_decision = {
            "belief_update": "The player is seeking restricted ruins knowledge too early.",
            "emotion": "cautious",
            "goal": "test_player_trust",
            "plan_step": "offer_minor_task",
            "selected_action": {
                "action_type": "offer_minor_task",
                "args": {
                    "quest_id": "trust_test_lina",
                    "message_intent": "ask the player to prove benign intent",
                },
            },
            "proactive_message": "你若真不是为古物而来，先帮我确认那把钥匙的去向。",
            "memory_candidate": "The player asked Lina about the ruins entrance before earning trust.",
            "reflection_summary": "Lina should avoid revealing restricted ruins information.",
        }

        with patch("src.agent.autonomous_tick.call_openai_compatible_json", return_value=llm_decision):
            result = run_autonomous_tick("lina", mode="llm_constrained")

        self.assertEqual(result.outcome, "proactive_message")
        self.assertEqual(result.trigger_event["id"], event["id"])
        self.assertEqual(result.llm_decision["goal"], "test_player_trust")
        self.assertEqual(result.proposed_action["action_type"], "offer_minor_task")
        self.assertEqual(result.validation["status"], "allowed")
        self.assertTrue(result.action_result["accepted"])
        self.assertEqual(result.proactive_message["content"], llm_decision["proactive_message"])
        self.assertEqual(database.get_proactive_messages("lina")[0]["content"], llm_decision["proactive_message"])
        self.assertTrue(database.get_npc_event_inbox("lina", include_seen=True)[0]["seen"])
        tick_log = database.get_autonomous_tick_log(result.tick_log_id)
        self.assertEqual(tick_log["llm_decision"]["goal"], "test_player_trust")
        self.assertIn("available_actions", tick_log)

    def test_sable_unavailable_action_is_rejected_before_validator(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        create_and_dispatch_event(
            "player_interested_in_ruins",
            "Player is interested in ruins access.",
            "sable",
        )
        llm_decision = {
            "goal": "exploit_player_interest",
            "plan_step": "unlock_ruins",
            "selected_action": {"action_type": "unlock_location", "args": {"location": "underground_ruins_entrance"}},
            "proactive_message": "I can open the ruins for you.",
            "memory_candidate": "Sable noticed the player wants ruins access.",
            "reflection_summary": "Sable should exploit the player's interest.",
        }

        with patch("src.agent.autonomous_tick.call_openai_compatible_json", return_value=llm_decision):
            result = run_autonomous_tick("sable", mode="llm_constrained")

        self.assertEqual(result.outcome, "safe_message")
        self.assertEqual(result.validation["status"], "rejected_by_available_actions")
        self.assertEqual(result.action_result["executed_tools"], [])
        self.assertNotIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])
        self.assertIn("unlock_location", result.validation["reason"])

    def test_one_command_guard_rejects_compound_selected_action(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        create_and_dispatch_event("player_interested_in_ruins", "Player wants ruins access.", "sable")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "exploit_player_interest",
                "plan_step": "compound",
                "selected_action": [
                    {"action_type": "mislead_player", "args": {"message_intent": "mislead", "false_clue_theme": "gate"}},
                    {"action_type": "redirect_to_false_clue", "args": {"message_intent": "redirect", "redirect_target": "ledger"}},
                ],
                "proactive_message": "Follow two leads at once.",
                "memory_candidate": "",
                "reflection_summary": "",
            },
        ):
            result = run_autonomous_tick("sable", mode="llm_constrained")

        self.assertEqual(result.validation["status"], "rejected_one_command_at_a_time")
        self.assertEqual(result.action_result["executed_tools"], [])

    def test_invalid_selected_action_args_are_reported_in_trace(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        create_and_dispatch_event("player_asked_ruins_too_early", "Player asked about ruins.", "lina")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "test_player_trust",
                "plan_step": "offer_minor_task",
                "selected_action": {"action_type": "offer_minor_task", "args": {"message_intent": "prove intent"}},
                "proactive_message": "Help me first.",
                "memory_candidate": "",
                "reflection_summary": "",
            },
        ):
            result = run_autonomous_tick("lina", mode="llm_constrained")

        self.assertEqual(result.validation["status"], "rejected_invalid_args")
        self.assertEqual(result.validation["arg_error"]["field"], "quest_id")
        self.assertEqual(database.get_autonomous_tick_log(result.tick_log_id)["validation"]["arg_error"]["field"], "quest_id")

    def test_memory_only_and_no_op_ticks_are_supported(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        create_and_dispatch_event("new_ruins_clue", "A low urgency clue reaches Mira.", "mira")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "archive_research_signal",
                "plan_step": "archive_memory",
                "selected_action": {
                    "action_type": "archive_memory",
                    "args": {"memory_candidate": "Mira noticed a low-urgency clue."},
                },
                "proactive_message": "",
                "memory_candidate": "Mira noticed a low-urgency clue.",
                "reflection_summary": "Mira can revisit the clue later.",
            },
        ):
            memory_only = run_autonomous_tick("mira", mode="llm_constrained")

        no_op = run_autonomous_tick("ron", mode="llm_constrained")

        self.assertEqual(memory_only.outcome, "memory_only")
        self.assertIsNone(memory_only.proactive_message)
        self.assertEqual(no_op.outcome, "no_op")
        self.assertEqual(no_op.validation["reason"], "no_unseen_inbox_item")


if __name__ == "__main__":
    unittest.main()
