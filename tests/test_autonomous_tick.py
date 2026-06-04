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
        self.assertEqual(database.get_quest("lost_key")["status"], "in_progress")
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

    def test_empty_autonomous_llm_decision_falls_back_to_valid_available_action(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        event = database.create_world_event(
            event_type="traveler_talked_to_npc",
            content="Traveler asked Mira about ruins research in the archive.",
            source_type="traveler",
            source_id="traveler_main",
            location_id="archive",
            visibility="npc_only",
            payload={"arc_id": "ruins_chapter_1", "arc_signal": "research"},
        )
        database.add_npc_event_inbox_item(
            "mira",
            int(event["id"]),
            relevance_score=1.0,
            reason="explicit_target",
        )

        with patch("src.agent.autonomous_tick.call_openai_compatible_json", return_value={}):
            result = run_autonomous_tick("mira", mode="llm_constrained", run_director=False)

        self.assertTrue(result.proposed_action.get("action_type"))
        self.assertNotEqual(result.validation["status"], "rejected_by_available_actions")
        self.assertEqual(result.llm_decision["fallback_reason"], "LLM returned no valid selected_action.")

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

    def test_plan_blocker_cooldown_budget_and_runtime_lifecycle(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick

        create_and_dispatch_event("player_claimed_badge", "Player claims badge access without evidence.", "ron")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "grant_gate_access",
                "plan_step": "verify_badge",
                "selected_action": {
                    "action_type": "grant_conditional_access",
                    "args": {"quest_id": "gate_badge", "message_intent": "grant access"},
                },
                "proactive_message": "You can pass now.",
                "memory_candidate": "",
                "reflection_summary": "Ron needs verified badge evidence.",
            },
        ):
            blocked = run_autonomous_tick("ron", mode="llm_constrained")

        self.assertEqual(blocked.validation["status"], "rejected_by_available_actions")
        self.assertEqual(database.get_npc_plan("ron")["status"], "blocked")
        self.assertIn("badge evidence", database.get_npc_plan("ron")["blocker"])

        first_event = create_and_dispatch_event("player_asked_ruins_too_early", "Player asked Lina again.", "lina")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "test_player_trust",
                "plan_step": "offer_minor_task",
                "selected_action": {
                    "action_type": "offer_minor_task",
                    "args": {"quest_id": "trust_test_lina", "message_intent": "prove intent"},
                },
                "proactive_message": "先帮我确认钥匙线索。",
                "memory_candidate": "",
                "reflection_summary": "Lina should test trust.",
            },
        ):
            first = run_autonomous_tick("lina", mode="llm_constrained", trigger_event_id=int(first_event["id"]))
        second_event = create_and_dispatch_event("player_asked_ruins_too_early", "Player repeated the ruins request.", "lina")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "test_player_trust",
                "plan_step": "offer_minor_task",
                "selected_action": {
                    "action_type": "offer_minor_task",
                    "args": {"quest_id": "trust_test_lina", "message_intent": "prove intent"},
                },
                "proactive_message": "再说一次，先帮我确认钥匙线索。",
                "memory_candidate": "",
                "reflection_summary": "Lina should test trust.",
            },
        ):
            second = run_autonomous_tick("lina", mode="llm_constrained", trigger_event_id=int(second_event["id"]))

        self.assertEqual(first.outcome, "proactive_message")
        self.assertEqual(second.validation["status"], "skipped_by_cooldown")
        self.assertEqual(len(database.get_proactive_messages("lina", delivered=False)), 1)
        self.assertIsNotNone(database.get_npc_cooldown("lina", "lina:player_asked_ruins_too_early:offer_minor_task"))

        database.upsert_npc_runtime_state("mira", lifecycle_status="paused", tick_enabled=True)
        create_and_dispatch_event("new_ruins_clue", "A clue reaches paused Mira.", "mira")
        with patch(
            "src.agent.autonomous_tick.call_openai_compatible_json",
            return_value={
                "goal": "archive_research_signal",
                "plan_step": "archive_memory",
                "selected_action": {
                    "action_type": "archive_memory",
                    "args": {"memory_candidate": "Mira noticed a clue while paused."},
                },
                "proactive_message": "I should speak now.",
                "memory_candidate": "Mira noticed a clue while paused.",
                "reflection_summary": "Paused Mira should only remember this.",
            },
        ):
            paused = run_autonomous_tick("mira", mode="llm_constrained")
        self.assertEqual(paused.outcome, "memory_only")
        self.assertIsNone(paused.proactive_message)
        self.assertEqual(paused.action_result["executed_tools"], [])

        database.upsert_npc_runtime_state("sable", lifecycle_status="disabled", tick_enabled=False)
        create_and_dispatch_event("player_interested_in_ruins", "Sable is disabled and should not consume this.", "sable")
        disabled = run_autonomous_tick("sable", mode="llm_constrained")
        self.assertEqual(disabled.outcome, "no_op")
        self.assertEqual(disabled.validation["reason"], "npc_disabled")
        self.assertFalse(database.get_npc_event_inbox("sable")[0]["seen"])


if __name__ == "__main__":
    unittest.main()
