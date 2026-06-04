"""Tests for the Traveler autonomous tick loop."""

import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"

TEST_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "test_traveler_tick.db")
os.environ["AGENT_NPC_DB_PATH"] = TEST_DB_PATH

from src.agent.traveler_profile import load_profile  # noqa: E402
from src.agent.traveler_state import TravelerRelationshipManager, TravelerStateManager  # noqa: E402
from src.agent.traveler_tick import run_traveler_tick  # noqa: E402
from src.storage import database  # noqa: E402


class TravelerTickTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.profile = load_profile("truth_seeking_scholar")
        self.traveler_id = "test_traveler_tick"

        # Initialize traveler at tavern (Lina is there, tavern_back_alley is there)
        self.state_mgr = TravelerStateManager(self.traveler_id)
        self.state_mgr.initialize(
            self.profile.profile_id,
            starting_location="tavern",
            inventory=list(self.profile.starting_inventory),
            private_notes=list(self.profile.private_notes),
        )

        # Initialize relationships for all NPCs
        self.rel_mgr = TravelerRelationshipManager(self.traveler_id)
        for npc_id in ["lina", "ron", "mira", "sable"]:
            self.rel_mgr.initialize_for_npc(npc_id)

    def _world_state(self) -> dict[str, Any]:
        return {
            "round_number": 1,
            "npc_states": {npc["npc_id"]: npc for npc in database.list_npcs()},
            "scene_objects": database.list_scene_objects(),
            "arc_state": database.get_world_arc_state("ruins_chapter_1"),
            "world_events_since_last_round": [],
        }

    def test_tick_completes_with_deterministic_fallback(self) -> None:
        """A tick should complete using deterministic fallback (no LLM)."""
        result = run_traveler_tick(
            traveler_id=self.traveler_id,
            round_number=1,
            profile=self.profile,
            world_state=self._world_state(),
            use_llm=False,
        )

        self.assertEqual(result.traveler_id, self.traveler_id)
        self.assertEqual(result.round_number, 1)
        self.assertEqual(result.mode, "deterministic_fallback")
        self.assertIsNotNone(result.decision)
        self.assertIsNotNone(result.validation)
        self.assertIsNotNone(result.action_result)
        self.assertGreater(result.tick_log_id, 0)

    def test_tick_move_to_changes_location(self) -> None:
        """A tick that selects move_to should update traveler location."""
        move_decision = {
            "selected_action": {"action_type": "move_to", "args": {"location_id": "archive"}},
            "decision_reason": "Let's find Mira.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Move to archive.",
            "mode": "llm",
        }
        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=move_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertEqual(result.mode, "llm")
        self.assertTrue(result.action_result["accepted"])
        self.assertIn("archive", str(result.state_changes))

    def test_tick_talk_to_updates_relationships(self) -> None:
        """A talk_to tick should update relationship with the target NPC."""
        talk_decision = {
            "selected_action": {"action_type": "talk_to", "args": {
                "npc_id": "lina", "topic": "local ruins rumors",
                "tone": "friendly", "honesty_level": "full", "disclosure": "none",
            }},
            "decision_reason": "Lina is nearby and may know local rumors.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Learn more about ruins.",
            "mode": "llm",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=talk_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertTrue(result.action_result["accepted"])
        # Should create at least one event (talk)
        self.assertTrue(len(result.created_events) > 0)

    def test_tick_investigate_creates_world_event(self) -> None:
        """Investigating a scene object should create a world event."""
        inv_decision = {
            "selected_action": {"action_type": "investigate", "args": {
                "target_id": "tavern_back_alley", "method": "careful observation",
            }},
            "decision_reason": "Check the alley for clues.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Find evidence.",
            "mode": "llm",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=inv_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertTrue(result.action_result["accepted"])
        self.assertTrue(len(result.created_events) > 0)

    def test_tick_record_private_note(self) -> None:
        """Recording a private note should not create public events."""
        note_decision = {
            "selected_action": {"action_type": "record_private_note", "args": {
                "content": "Sable seems very interested in my questions about the ruins.",
            }},
            "decision_reason": "Important observation to remember.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Private note recorded.",
            "mode": "llm",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=note_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertTrue(result.action_result["accepted"])
        # Private notes should not generate world events
        self.assertEqual(len(result.created_events), 0)

    def test_tick_falls_back_when_llm_returns_invalid_action(self) -> None:
        """When LLM returns an invalid action, the fallback mechanism kicks in
        at the decision layer — the tick completes with a valid deterministic action."""
        bad_decision = {
            "selected_action": {"action_type": "nonexistent", "args": {}},
            "decision_reason": "Test.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Nothing.",
            "mode": "llm",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=bad_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        # Invalid LLM output triggers fallback → still accepted with deterministic action
        self.assertTrue(result.action_result["accepted"])
        self.assertEqual(result.mode, "deterministic_fallback")

    def test_tick_rejects_empty_required_action_args(self) -> None:
        """Required string args must be non-empty, not merely present."""
        bad_move_decision = {
            "selected_action": {"action_type": "move_to", "args": {"location_id": ""}},
            "decision_reason": "Invalid empty destination.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Should be rejected.",
            "mode": "llm",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=bad_move_decision):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertFalse(result.action_result["accepted"])
        self.assertEqual(result.validation["status"], "rejected")
        self.assertIn("empty", result.validation["reason"])
        self.assertEqual(result.created_events, [])

    def test_tick_for_each_profile_produces_result(self) -> None:
        """Each of the 3 built-in profiles should complete a tick."""
        for profile_id in ["truth_seeking_scholar", "suspicious_survivor", "opportunistic_relic_hunter"]:
            profile = load_profile(profile_id)
            traveler_id = f"tick_test_{profile_id}"
            state_mgr = TravelerStateManager(traveler_id)
            state_mgr.initialize(
                profile.profile_id,
                starting_location=profile.starting_location,
                inventory=list(profile.starting_inventory),
            )
            rel_mgr = TravelerRelationshipManager(traveler_id)
            for npc_id in ["lina", "ron", "mira", "sable"]:
                rel_mgr.initialize_for_npc(npc_id)

            world_state = {
                "round_number": 1,
                "npc_states": {npc["npc_id"]: npc for npc in database.list_npcs()},
                "scene_objects": database.list_scene_objects(),
                "arc_state": database.get_world_arc_state("ruins_chapter_1"),
                "world_events_since_last_round": [],
            }

            result = run_traveler_tick(
                traveler_id=traveler_id,
                round_number=1,
                profile=profile,
                world_state=world_state,
                use_llm=False,
            )
            self.assertIsNotNone(result)
            self.assertGreater(result.tick_log_id, 0)
