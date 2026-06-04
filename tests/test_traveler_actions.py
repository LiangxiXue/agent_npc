"""Tests for traveler action catalog, available actions, and decision."""

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

TEST_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "test_traveler_actions.db")
os.environ["AGENT_NPC_DB_PATH"] = TEST_DB_PATH

from src.agent.traveler_actions import (  # noqa: E402
    ActionBias,
    compute_action_biases,
    get_traveler_available_actions,
    get_unavailable_actions_with_reasons,
    serialize_actions_for_llm_prompt,
)
from src.agent.traveler_decision import (  # noqa: E402
    decide_traveler_action,
    deterministic_fallback_decision,
)
from src.agent.traveler_profile import TravelerProfile, load_profile  # noqa: E402
from src.agent.traveler_state import TravelerStateManager  # noqa: E402
from src.storage import database  # noqa: E402


class TravelerActionCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.traveler_mgr = TravelerStateManager("test_traveler")
        self.traveler_mgr.initialize("truth_seeking_scholar", "town_square")

    def test_available_actions_with_basic_state(self) -> None:
        state = self.traveler_mgr.get_state()
        actions = get_traveler_available_actions(state)
        # With no NPCs at location, some actions are filtered out
        action_types = {a["action_type"] for a in actions}
        self.assertIn("move_to", action_types)
        self.assertIn("wait_and_observe", action_types)
        self.assertIn("record_private_note", action_types)
        # talk_to requires NPC at same location
        self.assertNotIn("talk_to", action_types)

    def test_unavailable_actions_include_reasons(self) -> None:
        state = self.traveler_mgr.get_state()
        unavailable = get_unavailable_actions_with_reasons(state)
        self.assertTrue(len(unavailable) > 0)
        for action in unavailable:
            self.assertIn("failed_preconditions", action)
            self.assertIn("reason", action)

    def test_talk_to_available_when_npc_at_same_location(self) -> None:
        self.traveler_mgr.move_to("tavern")  # Lina is at tavern
        state = self.traveler_mgr.get_state()
        npc_ids = ["lina", "ron", "mira", "sable"]
        actions = get_traveler_available_actions(state, npc_ids=npc_ids)
        action_types = {a["action_type"] for a in actions}
        self.assertIn("talk_to", action_types)

    def test_investigate_available_when_scene_object_at_location(self) -> None:
        self.traveler_mgr.move_to("tavern")
        state = self.traveler_mgr.get_state()
        scene_objects = database.list_scene_objects()
        actions = get_traveler_available_actions(state, scene_objects=scene_objects)
        action_types = {a["action_type"] for a in actions}
        self.assertIn("investigate", action_types)

    def test_serialize_actions_for_llm_prompt_includes_biases(self) -> None:
        state = self.traveler_mgr.get_state()
        actions = get_traveler_available_actions(state)
        profile = load_profile("truth_seeking_scholar")
        biases = compute_action_biases(actions, profile)
        serialized = serialize_actions_for_llm_prompt(actions, biases)
        self.assertEqual(len(serialized), len(actions))
        # At least one action should have profile_alignment
        aligned = [a for a in serialized if "profile_alignment" in a]
        self.assertTrue(len(aligned) > 0)


class TravelerActionBiasTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.profile_scholar = load_profile("truth_seeking_scholar")
        self.profile_survivor = load_profile("suspicious_survivor")
        self.profile_hunter = load_profile("opportunistic_relic_hunter")

    def _make_state(self, location: str = "town_square", inventory: list[str] | None = None) -> dict[str, Any]:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("test", location, inventory=inventory or [])
        return mgr.get_state()

    def _make_npc_ids(self) -> list[str]:
        return ["lina", "ron", "mira", "sable"]

    def _make_scene_objects(self) -> list[dict[str, Any]]:
        return database.list_scene_objects()

    def test_investigate_aligns_high_with_curious_scholar(self) -> None:
        state = self._make_state(location="tavern")
        actions = get_traveler_available_actions(state, scene_objects=self._make_scene_objects())
        biases = compute_action_biases(actions, self.profile_scholar)
        investigate_bias = next(b for b in biases if b.action_type == "investigate")
        self.assertGreater(investigate_bias.profile_alignment_score, 0.0)

    def test_trade_with_aligns_high_with_relic_hunter(self) -> None:
        state = self._make_state(location="tavern", inventory=["coin_pouch"])
        actions = get_traveler_available_actions(state, npc_ids=self._make_npc_ids(), scene_objects=self._make_scene_objects())
        biases = compute_action_biases(actions, self.profile_hunter)
        trade_bias = next(b for b in biases if b.action_type == "trade_with")
        hunter_trade_score = trade_bias.profile_alignment_score

        biases_scholar = compute_action_biases(actions, self.profile_scholar)
        trade_bias_scholar = next(b for b in biases_scholar if b.action_type == "trade_with")
        # Hunter should have higher trade alignment than scholar
        self.assertGreater(hunter_trade_score, trade_bias_scholar.profile_alignment_score)

    def test_ask_for_help_tension_with_suspicious_survivor(self) -> None:
        state = self._make_state(location="tavern")
        actions = get_traveler_available_actions(state, npc_ids=self._make_npc_ids())
        biases = compute_action_biases(actions, self.profile_survivor)
        help_bias = next(b for b in biases if b.action_type == "ask_for_help")
        # Suspicious survivor should have low score for asking help
        self.assertLess(help_bias.profile_alignment_score, 0.5)

    def test_different_profiles_produce_different_biases(self) -> None:
        state = self._make_state(location="tavern")
        actions = get_traveler_available_actions(state, npc_ids=self._make_npc_ids(), scene_objects=self._make_scene_objects())

        biases_scholar = {b.action_type: b for b in compute_action_biases(actions, self.profile_scholar)}
        biases_hunter = {b.action_type: b for b in compute_action_biases(actions, self.profile_hunter)}
        biases_survivor = {b.action_type: b for b in compute_action_biases(actions, self.profile_survivor)}

        # At least one action should differ meaningfully between profiles
        diff_count = 0
        for action_type in biases_scholar:
            s_s = biases_scholar[action_type].profile_alignment_score
            s_h = biases_hunter[action_type].profile_alignment_score
            s_v = biases_survivor[action_type].profile_alignment_score
            if abs(s_s - s_h) > 0.1 or abs(s_s - s_v) > 0.1:
                diff_count += 1
        self.assertGreater(diff_count, 0, "Profiles should produce different action biases")


class TravelerDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.profile = load_profile("truth_seeking_scholar")
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "tavern")  # Lina is at tavern
        self.state = mgr.get_state()

    def _observation(self) -> dict[str, Any]:
        return {
            "traveler_state": self.state,
            "round_number": 1,
            "arc_phase": "rumor",
            "npc_ids": ["lina", "ron", "mira", "sable"],
            "scene_objects": database.list_scene_objects(),
        }

    def test_deterministic_fallback_selects_highest_alignment_action(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])
        biases = compute_action_biases(actions, self.profile)

        decision = deterministic_fallback_decision(actions, biases, self.profile)
        self.assertIn("selected_action", decision)
        self.assertEqual(decision["mode"], "deterministic_fallback")
        # The selected action should be one of the available ones
        available_types = {a["action_type"] for a in actions}
        self.assertIn(decision["selected_action"]["action_type"], available_types)

    def test_deterministic_fallback_fills_real_move_target(self) -> None:
        mgr = TravelerStateManager("move_target_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square")
        state = mgr.get_state()
        actions = get_traveler_available_actions(state)
        move_actions = [a for a in actions if a["action_type"] == "move_to"]
        self.assertEqual(len(move_actions), 1)

        decision = deterministic_fallback_decision(
            move_actions,
            [ActionBias("move_to", ("curiosity",), (), "low", 1.0)],
            self.profile,
        )

        args = decision["selected_action"]["args"]
        self.assertIn("location_id", args)
        self.assertNotEqual(args["location_id"], "")
        self.assertNotEqual(args["location_id"], state["current_location"])

    def test_decision_includes_required_fields(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])
        biases = compute_action_biases(actions, self.profile)

        decision = deterministic_fallback_decision(actions, biases, self.profile)
        required = ["selected_action", "decision_reason", "profile_alignment",
                     "profile_tension", "deception_choice", "disclosure_choice",
                     "expected_consequence", "mode"]
        for key in required:
            self.assertIn(key, decision, f"Decision missing required field: {key}")

    def test_fallback_handles_empty_actions(self) -> None:
        decision = deterministic_fallback_decision([], [], self.profile)
        self.assertEqual(decision["selected_action"]["action_type"], "wait_and_observe")

    def test_llm_decision_falls_back_on_error(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])

        # LLM throws → should fall back to deterministic
        with patch("src.agent.traveler_decision.call_openai_compatible_json", side_effect=RuntimeError("LLM down")):
            decision = decide_traveler_action(self.profile, obs, actions, use_llm=True)
        self.assertEqual(decision["mode"], "deterministic_fallback")

    def test_llm_decision_strict_mode_raises_on_error(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])

        with patch("src.agent.traveler_decision.call_openai_compatible_json", side_effect=RuntimeError("LLM down")):
            with self.assertRaises(RuntimeError):
                decide_traveler_action(
                    self.profile,
                    obs,
                    actions,
                    use_llm=True,
                    allow_llm_fallback=False,
                )

    def test_llm_decision_normalizes_invalid_selection(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])

        # LLM returns invalid action → should fall back
        bad_llm = {
            "selected_action": {"action_type": "nonexistent_action", "args": {}},
            "decision_reason": "test",
        }
        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=bad_llm):
            decision = decide_traveler_action(self.profile, obs, actions, use_llm=True)
        self.assertEqual(decision["mode"], "deterministic_fallback")

    def test_llm_decision_strict_mode_rejects_invalid_selection(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])
        bad_llm = {
            "selected_action": {"action_type": "nonexistent_action", "args": {}},
            "decision_reason": "test",
        }

        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=bad_llm):
            with self.assertRaises(ValueError):
                decide_traveler_action(
                    self.profile,
                    obs,
                    actions,
                    use_llm=True,
                    allow_llm_fallback=False,
                )

    def test_llm_decision_accepts_valid_selection(self) -> None:
        obs = self._observation()
        actions = get_traveler_available_actions(self.state, npc_ids=obs["npc_ids"], scene_objects=obs["scene_objects"])
        # Use a valid action type from available
        valid_type = actions[0]["action_type"]
        good_llm = {
            "selected_action": {"action_type": valid_type, "args": {}},
            "decision_reason": "This is the best choice.",
            "profile_alignment": {"curiosity": "high"},
            "profile_tension": {"cautious": "moderate"},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": "Information gathering.",
        }
        with patch("src.agent.traveler_decision.call_openai_compatible_json", return_value=good_llm):
            decision = decide_traveler_action(self.profile, obs, actions, use_llm=True)
        self.assertEqual(decision["mode"], "llm")
        self.assertEqual(decision["selected_action"]["action_type"], valid_type)
