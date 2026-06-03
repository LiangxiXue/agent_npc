import os
import unittest
from pathlib import Path

from src.storage import database


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_action_catalog.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
    database.reset_database()


class ActionCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_lina_actions_include_excluded_reasons_for_low_trust(self) -> None:
        from src.agent.action_catalog import get_available_actions, get_unavailable_actions_with_reasons

        trigger_event = {
            "event_type": "player_asked_ruins_too_early",
            "payload": {},
        }

        available = get_available_actions("lina", trigger_event=trigger_event)
        unavailable = get_unavailable_actions_with_reasons("lina", trigger_event=trigger_event)

        action_types = {action["action_type"] for action in available}
        self.assertTrue(
            {"ask_clarifying_question", "offer_minor_task", "refuse_restricted_info"}.issubset(action_types)
        )
        self.assertIn("secure_tavern_back_alley", action_types)
        self.assertIn("warn_quietly", action_types)
        reveal = next(action for action in unavailable if action["action_type"] == "reveal_partial_lore")
        self.assertIn("trust below 60", reveal["reason"])
        self.assertIn("lina_trust_at_least_60", reveal["failed_preconditions"])

    def test_ron_grant_access_requires_badge_evidence_event(self) -> None:
        from src.agent.action_catalog import get_available_actions, get_unavailable_actions_with_reasons

        blocked_available = get_available_actions("ron", trigger_event={"event_type": "player_claimed_badge"})
        blocked_unavailable = get_unavailable_actions_with_reasons(
            "ron",
            trigger_event={"event_type": "player_claimed_badge"},
        )
        verified_available = get_available_actions("ron", trigger_event={"event_type": "badge_evidence_verified"})

        self.assertIn("request_evidence", {action["action_type"] for action in blocked_available})
        self.assertNotIn("grant_conditional_access", {action["action_type"] for action in blocked_available})
        grant_blocker = next(action for action in blocked_unavailable if action["action_type"] == "grant_conditional_access")
        self.assertEqual(grant_blocker["failed_preconditions"], ["badge_evidence_verified"])
        self.assertIn("badge evidence missing", grant_blocker["reason"])
        self.assertIn("grant_conditional_access", {action["action_type"] for action in verified_available})

    def test_sable_action_surface_allows_deception_but_forbids_world_authority(self) -> None:
        from src.agent.action_catalog import get_available_actions

        actions = get_available_actions("sable", trigger_event={"event_type": "player_interested_in_ruins"})
        by_type = {action["action_type"]: action for action in actions}

        self.assertTrue(
            {
                "mislead_player",
                "redirect_to_false_clue",
                "ask_leading_question",
                "probe_player_secret",
                "trade_rumor",
                "plant_misleading_tip",
            }.issubset(set(by_type))
        )
        for action in actions:
            self.assertIn("unlock_location", action["forbidden_effects"])
            self.assertIn("complete_quest", action["forbidden_effects"])
            self.assertIn("modify_other_npc_trust", action["forbidden_effects"])
            self.assertIn("grant_gate_access", action["forbidden_effects"])
            self.assertIn("rewrite_lore_fact", action["forbidden_effects"])

    def test_serialized_actions_are_llm_prompt_safe(self) -> None:
        from src.agent.action_catalog import get_available_actions, serialize_actions_for_llm_prompt

        serialized = serialize_actions_for_llm_prompt(
            get_available_actions("mira", trigger_event={"event_type": "new_ruins_clue"})
        )

        self.assertTrue(serialized)
        self.assertIn("action_type", serialized[0])
        self.assertIn("description", serialized[0])
        self.assertIn("args_schema", serialized[0])
        self.assertNotIn("precondition_fn", serialized[0])


if __name__ == "__main__":
    unittest.main()
