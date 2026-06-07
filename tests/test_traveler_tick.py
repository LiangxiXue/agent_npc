"""Tests for the Traveler autonomous tick loop."""

import os
import unittest
from contextlib import contextmanager
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

    @contextmanager
    def _patched_npc_dialogue(self):
        npc_decision = {
            "intent": "general_conversation",
            "reasoning": "NPC gives a cautious in-character reply.",
            "memory_policy": "Store the exchange as low-importance context.",
            "response_style": "natural_in_character_chat",
            "response_keywords": ["cautious reply"],
            "tools": [],
            "social_intent": "cooperate",
            "social_stance": {
                "target": "player",
                "attitude": "cautious",
                "intensity": 0.3,
                "reason": "Direct Traveler dialogue test.",
            },
        }
        with (
            patch("src.agent.decision.decide_next_action", return_value=npc_decision),
            patch(
                "src.agent.response.generate_npc_response",
                return_value=("The NPC answers cautiously.", {"mode": "llm_polish"}),
            ),
        ):
            yield

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

    def test_traveler_tick_records_internal_timings(self) -> None:
        result = run_traveler_tick(
            traveler_id=self.traveler_id,
            round_number=1,
            profile=self.profile,
            world_state=self._world_state(),
            use_llm=False,
        )

        expected_keys = {
            "observe_ms",
            "retrieve_memory_ms",
            "build_action_surface_ms",
            "decide_ms",
            "validate_ms",
            "act_ms",
            "reflect_ms",
            "trace_log_ms",
            "total_ms",
        }
        self.assertTrue(expected_keys.issubset(result.timings))
        self.assertGreaterEqual(result.timings["total_ms"], 0.0)

        tick_log = database.get_traveler_tick_log(result.tick_log_id)
        self.assertEqual(tick_log["timings"], result.timings)

    def test_tick_exposes_exploration_context_in_observation_and_reflection(self) -> None:
        result = run_traveler_tick(
            traveler_id=self.traveler_id,
            round_number=1,
            profile=self.profile,
            world_state=self._world_state(),
            use_llm=False,
        )

        self.assertIn("exploration_context", result.observation)
        self.assertIn("action_scores", result.observation["exploration_context"])
        self.assertEqual(
            result.reflection["exploration_context"],
            result.observation["exploration_context"],
        )

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

        with (
            patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=talk_decision),
            self._patched_npc_dialogue(),
        ):
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
        self.assertTrue(result.relationship_changes)
        changed_fields = {change["field"] for change in result.relationship_changes}
        self.assertIn("trust", changed_fields)
        self.assertIn("affinity", changed_fields)

    def test_tick_talk_to_records_traveler_utterance(self) -> None:
        """A talk_to tick should preserve the exact Traveler utterance."""
        talk_decision = {
            "selected_action": {"action_type": "talk_to", "args": {
                "npc_id": "lina", "topic": "local ruins rumors",
                "tone": "friendly", "honesty_level": "full", "disclosure": "none",
            }},
            "traveler_utterance": "Lina, I am mapping old foundations. Have you heard anything reliable about the ruins?",
            "decision_reason": "Ask the nearby tavern keeper for local context.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Lina may share a cautious local lead.",
            "mode": "llm",
        }

        with (
            patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=talk_decision),
            self._patched_npc_dialogue(),
        ):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        talk_events = [
            event for event in result.created_events
            if event.get("event_type") == "traveler_talked_to_npc"
        ]
        self.assertTrue(talk_events)
        self.assertEqual(
            talk_events[0]["payload"]["traveler_utterance"],
            talk_decision["traveler_utterance"],
        )

    def test_tick_talk_to_records_npc_dialogue_response(self) -> None:
        """A talk_to tick should record the direct NPC LLM decision and reply."""
        talk_decision = {
            "selected_action": {"action_type": "talk_to", "args": {
                "npc_id": "lina", "topic": "local ruins rumors",
                "tone": "friendly", "honesty_level": "full", "disclosure": "none",
            }},
            "traveler_utterance": "Lina, I am mapping old foundations. What should I know before I approach the ruins?",
            "decision_reason": "Ask the nearby tavern keeper for local context.",
            "profile_alignment": {},
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Lina may share a cautious local lead.",
            "mode": "llm",
        }
        npc_decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Lina is cautious around ruins inquiries.",
            "memory_policy": "Remember that the traveler asked cautiously about ruins access.",
            "response_style": "cautious",
            "response_keywords": ["ruins", "caution"],
            "tools": [],
            "social_intent": "probe",
            "social_stance": {
                "target": "player",
                "attitude": "cautious",
                "intensity": 0.4,
                "reason": "The traveler is asking about dangerous ruins.",
            },
        }

        with (
            patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=talk_decision),
            patch("src.agent.decision.decide_next_action", return_value=npc_decision),
            patch(
                "src.agent.response.generate_npc_response",
                return_value=("Lina lowers her voice: stay on the main road and do not trust market rumors.", {"mode": "llm_polish"}),
            ),
        ):
            result = run_traveler_tick(
                traveler_id=self.traveler_id,
                round_number=1,
                profile=self.profile,
                world_state=self._world_state(),
                use_llm=True,
            )

        self.assertEqual(result.dialogue_exchange["npc_id"], "lina")
        self.assertEqual(result.dialogue_exchange["traveler_utterance"], talk_decision["traveler_utterance"])
        self.assertIn("stay on the main road", result.dialogue_exchange["npc_response"])
        self.assertEqual(result.dialogue_exchange["npc_decision"]["intent"], "withhold_ruins_entrance")
        self.assertEqual(result.dialogue_exchange["response_generation"]["mode"], "llm_polish")

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

    def test_tick_created_events_use_domain_arc_signal(self) -> None:
        """Traveler events should contribute to the matching arc route."""
        cases = [
            (
                "move_guard",
                "town_square",
                {"action_type": "move_to", "args": {"location_id": "guard_post"}},
                "guardian",
            ),
            (
                "talk_mira",
                "archive",
                {"action_type": "talk_to", "args": {
                    "npc_id": "mira", "topic": "field notes",
                    "tone": "friendly", "honesty_level": "full", "disclosure": "none",
                }},
                "research",
            ),
            (
                "inspect_sable",
                "market",
                {"action_type": "investigate", "args": {
                    "target_id": "sable_rumor_stall", "method": "compare rumors",
                }},
                "sable",
            ),
        ]

        for label, starting_location, selected_action, expected_signal in cases:
            with self.subTest(label=label):
                database.reset_database()
                traveler_id = f"signal_{label}"
                state_mgr = TravelerStateManager(traveler_id)
                state_mgr.initialize(
                    self.profile.profile_id,
                    starting_location=starting_location,
                    inventory=list(self.profile.starting_inventory),
                )
                rel_mgr = TravelerRelationshipManager(traveler_id)
                for npc_id in ["lina", "ron", "mira", "sable"]:
                    rel_mgr.initialize_for_npc(npc_id)

                decision = {
                    "selected_action": selected_action,
                    "decision_reason": "Exercise arc signal routing.",
                    "profile_alignment": {},
                    "profile_tension": {},
                    "deception_choice": None,
                    "disclosure_choice": None,
                    "expected_consequence": "Create a scored event.",
                    "mode": "llm",
                }

                with (
                    patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=decision),
                    self._patched_npc_dialogue(),
                ):
                    result = run_traveler_tick(
                        traveler_id=traveler_id,
                        round_number=1,
                        profile=self.profile,
                        world_state=self._world_state(),
                        use_llm=True,
                    )

                signals = [
                    event.get("payload", {}).get("arc_signal")
                    for event in result.created_events
                ]
                self.assertIn(expected_signal, signals)

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
