"""Tests for traveler state, relationships, and secret tracking."""

import os
import unittest
from pathlib import Path

os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"

TEST_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "test_traveler_state.db")
os.environ["AGENT_NPC_DB_PATH"] = TEST_DB_PATH

from src.agent.traveler_state import (  # noqa: E402
    SecretTracker,
    TravelerRelationshipManager,
    TravelerStateManager,
)
from src.storage import database  # noqa: E402


class TravelerStateManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_initialize_creates_state(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        state = mgr.initialize(
            profile_id="truth_seeking_scholar",
            starting_location="town_square",
            inventory=["field_journal"],
            private_notes=["Find Mira first."],
        )
        self.assertEqual(state["traveler_id"], "test_traveler")
        self.assertEqual(state["profile_id"], "truth_seeking_scholar")
        self.assertEqual(state["current_location"], "town_square")
        self.assertIn("field_journal", state["inventory"])
        self.assertIn("Find Mira first.", state["private_notes"])

    def test_move_to_updates_location(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square")
        state = mgr.move_to("archive")
        self.assertEqual(state["current_location"], "archive")

    def test_add_inventory_item(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square", inventory=["map"])
        state = mgr.add_inventory_item("compass")
        self.assertIn("map", state["inventory"])
        self.assertIn("compass", state["inventory"])

    def test_add_inventory_no_duplicate(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square", inventory=["map"])
        state = mgr.add_inventory_item("map")
        self.assertEqual(state["inventory"].count("map"), 1)

    def test_remove_inventory_item(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square", inventory=["map", "coin"])
        state = mgr.remove_inventory_item("coin")
        self.assertNotIn("coin", state["inventory"])
        self.assertIn("map", state["inventory"])

    def test_add_private_note(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square", private_notes=["Initial."])
        state = mgr.add_private_note("Sable seems suspicious.")
        self.assertIn("Sable seems suspicious.", state["private_notes"])

    def test_set_active_goal(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "town_square")
        state = mgr.set_active_goal({"goal_id": "find_entrance", "priority": 0.9})
        self.assertEqual(state["active_goal"]["goal_id"], "find_entrance")

    def test_properties_return_current_values(self) -> None:
        mgr = TravelerStateManager("test_traveler")
        mgr.initialize("truth_seeking_scholar", "archive", inventory=["lens"])
        self.assertEqual(mgr.current_location, "archive")
        self.assertIn("lens", mgr.inventory)


class TravelerRelationshipManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        # traveler_state must exist before relationships can be created (FK constraint)
        TravelerStateManager("test_traveler").initialize("test_profile", "town_square")
        self.mgr = TravelerRelationshipManager("test_traveler")

    def test_initialize_for_npc_creates_default_relationship(self) -> None:
        rel = self.mgr.initialize_for_npc("lina")
        self.assertAlmostEqual(rel["trust"], 0.0)
        self.assertAlmostEqual(rel["suspicion"], 0.0)
        self.assertAlmostEqual(rel["affinity"], 0.0)
        self.assertEqual(rel["last_tone"], "neutral")

    def test_get_returns_existing_or_creates_default(self) -> None:
        rel = self.mgr.get("lina")
        self.assertEqual(rel["npc_id"], "lina")
        self.assertEqual(rel["traveler_id"], "test_traveler")

    def test_update_trust_clamps_range(self) -> None:
        rel = self.mgr.update_trust("lina", 0.6)
        self.assertAlmostEqual(rel["trust"], 0.6)
        rel = self.mgr.update_trust("lina", 1.0)
        self.assertAlmostEqual(rel["trust"], 1.0)  # clamped at 1.0

    def test_update_suspicion(self) -> None:
        rel = self.mgr.update_suspicion("lina", 0.5)
        self.assertAlmostEqual(rel["suspicion"], 0.5)

    def test_update_affinity_supports_negative(self) -> None:
        rel = self.mgr.update_affinity("lina", -0.3)
        self.assertAlmostEqual(rel["affinity"], -0.3)

    def test_set_tone(self) -> None:
        self.mgr.set_tone("lina", "guarded")
        rel = self.mgr.get("lina")
        self.assertEqual(rel["last_tone"], "guarded")

    def test_add_known_secret(self) -> None:
        self.mgr.add_known_secret("lina", "secret_001")
        rel = self.mgr.get("lina")
        self.assertIn("secret_001", rel["known_secret_ids"])

    def test_add_known_secret_no_duplicate(self) -> None:
        self.mgr.add_known_secret("lina", "secret_001")
        self.mgr.add_known_secret("lina", "secret_001")
        rel = self.mgr.get("lina")
        self.assertEqual(rel["known_secret_ids"].count("secret_001"), 1)

    def test_get_all_returns_all_relationships(self) -> None:
        self.mgr.initialize_for_npc("lina")
        self.mgr.initialize_for_npc("mira")
        all_rels = self.mgr.get_all()
        self.assertIn("lina", all_rels)
        self.assertIn("mira", all_rels)

    def test_snapshot_changes_detects_field_changes(self) -> None:
        self.mgr.initialize_for_npc("lina")
        after = {"trust": 0.5, "suspicion": 0.0, "affinity": 0.0, "leverage": 0.0, "exposure": 0.0, "debt": 0.0, "last_tone": "neutral"}
        changes = self.mgr.snapshot_changes("lina", after)
        # trust changed from 0.0 to 0.5
        trust_changes = [c for c in changes if c["field"] == "trust"]
        self.assertEqual(len(trust_changes), 1)
        self.assertAlmostEqual(trust_changes[0]["after"], 0.5)


class SecretTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.tracker = SecretTracker()

    def test_register_and_get_secret(self) -> None:
        self.tracker.register_secret(
            secret_id="sec_001", owner_id="test_traveler", owner_type="traveler",
            label="Hidden Past", content="Something hidden.", risk_level="high",
        )
        secret = self.tracker.get("sec_001")
        self.assertIsNotNone(secret)
        self.assertEqual(secret["label"], "Hidden Past")
        self.assertEqual(secret["risk_level"], "high")

    def test_record_disclosure(self) -> None:
        self.tracker.register_secret(
            secret_id="sec_002", owner_id="test_traveler", owner_type="traveler",
            label="Test", content="Test", risk_level="medium",
        )
        self.tracker.record_disclosure("sec_002", "mira", "npc", 3, method="partial")
        secret = self.tracker.get("sec_002")
        self.assertEqual(secret["exposure_count"], 1)
        self.assertEqual(len(secret["disclosed_to"]), 1)
        self.assertEqual(secret["disclosed_to"][0]["actor_id"], "mira")

    def test_disclosure_count(self) -> None:
        self.tracker.register_secret(
            secret_id="sec_003", owner_id="test_traveler", owner_type="traveler",
            label="Test", content="Test",
        )
        self.tracker.record_disclosure("sec_003", "mira", "npc", 1)
        self.tracker.record_disclosure("sec_003", "lina", "npc", 2)
        self.assertEqual(self.tracker.get_disclosure_count("sec_003"), 2)
