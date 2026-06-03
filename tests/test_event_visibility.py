import os
import unittest
from pathlib import Path

from src.agent.environment import NarrativeEnvironment
from src.storage import database


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_event_visibility.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
    database.reset_database()


class EventVisibilityResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_dispatches_public_location_private_and_npc_only_events(self) -> None:
        from src.agent.event_visibility import dispatch_world_event_to_inbox

        public_event = database.create_world_event(
            event_type="market_alarm",
            content="A bell rings across Grayhaven.",
            source_type="system",
            visibility="public",
            payload={},
        )
        location_event = database.create_world_event(
            event_type="tavern_rumor",
            content="Someone whispers about the ruins in the tavern.",
            source_type="player",
            location_id="tavern",
            visibility="location",
            payload={},
        )
        private_event = database.create_world_event(
            event_type="mira_private_note",
            content="Mira records a private note about a sealed inscription.",
            source_type="npc",
            source_id="mira",
            location_id="archive",
            visibility="private",
            payload={"target_npc_ids": ["mira"], "witnessed_by": ["sable"]},
        )
        npc_only_event = database.create_world_event(
            event_type="badge_evidence_verified",
            content="Ron can now verify the badge evidence.",
            source_type="system",
            visibility="npc_only",
            payload={"target_npc_ids": ["ron"]},
        )

        public_items = dispatch_world_event_to_inbox(public_event)
        location_items = dispatch_world_event_to_inbox(location_event)
        private_items = dispatch_world_event_to_inbox(private_event)
        npc_only_items = dispatch_world_event_to_inbox(npc_only_event)

        self.assertEqual({item["npc_id"] for item in public_items}, {"lina", "ron", "mira", "sable"})
        self.assertEqual({item["npc_id"] for item in location_items}, {"lina"})
        self.assertEqual({item["npc_id"] for item in private_items}, {"mira", "sable"})
        self.assertEqual({item["npc_id"] for item in npc_only_items}, {"ron"})
        self.assertTrue(any(item["reason"] == "public" for item in database.get_npc_event_inbox("lina")))
        self.assertTrue(any(item["reason"] == "same_location" for item in location_items))
        self.assertTrue(any(item["reason"] == "explicit_target" for item in private_items))
        self.assertTrue(any(item["reason"] == "witnessed_by" for item in private_items))

    def test_observation_uses_visibility_filtered_events_and_seen_can_hide_inbox(self) -> None:
        from src.agent.event_visibility import dispatch_world_event_to_inbox

        private_event = database.create_world_event(
            event_type="mira_private_note",
            content="Mira privately notices a sealed inscription.",
            source_type="npc",
            source_id="mira",
            location_id="archive",
            visibility="private",
            payload={"target_npc_ids": ["mira"]},
        )
        public_event = database.create_world_event(
            event_type="town_square_rumor",
            content="A public rumor spreads through Grayhaven.",
            source_type="system",
            visibility="public",
            payload={},
        )
        dispatch_world_event_to_inbox(private_event)
        public_items = dispatch_world_event_to_inbox(public_event)

        lina_observation = NarrativeEnvironment().observe("入口在哪里？", "lina", "hybrid")
        mira_observation = NarrativeEnvironment().observe("入口在哪里？", "mira", "hybrid")
        lina_inbox_id = next(item["id"] for item in public_items if item["npc_id"] == "lina")
        database.mark_npc_event_seen(lina_inbox_id)

        self.assertIn("A public rumor", str(lina_observation.visible_world_events))
        self.assertNotIn("sealed inscription", str(lina_observation.visible_world_events))
        self.assertIn("sealed inscription", str(mira_observation.visible_world_events))
        self.assertEqual(
            [item["event"]["id"] for item in database.get_npc_event_inbox("lina")],
            [],
        )
        self.assertTrue(database.get_npc_event_inbox("lina", include_seen=True))


if __name__ == "__main__":
    unittest.main()
