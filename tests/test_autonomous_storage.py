import os
import sqlite3
import unittest
from pathlib import Path

from src.storage import database


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_autonomous_storage.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
    database.reset_database()


class AutonomousStorageMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_structured_world_event_save_load_and_legacy_fallback(self) -> None:
        structured = database.create_world_event(
            event_type="player_asked_ruins_too_early",
            content="Player asked Lina about the ruins entrance before earning trust.",
            source_type="player",
            source_id="player",
            location_id="tavern",
            visibility="location",
            payload={"target_npc_ids": ["lina"], "trust": 20},
        )
        legacy = database.record_world_event("A quiet rumor moves through Grayhaven.")

        loaded = database.get_world_event(structured["id"])
        events = database.get_world_events(limit=10)
        legacy_loaded = database.get_world_event(legacy["id"])

        self.assertEqual(loaded["event_type"], "player_asked_ruins_too_early")
        self.assertEqual(loaded["visibility"], "location")
        self.assertEqual(loaded["payload"], {"target_npc_ids": ["lina"], "trust": 20})
        self.assertIn("payload", events[0])
        self.assertEqual(legacy_loaded["event_type"], "legacy")
        self.assertEqual(legacy_loaded["visibility"], "public")
        self.assertEqual(legacy_loaded["payload"], {})

    def test_additive_migration_upgrades_legacy_world_events_table(self) -> None:
        db_path = Path(os.environ["AGENT_NPC_DB_PATH"])
        with sqlite3.connect(db_path) as connection:
            connection.execute("DROP TABLE world_events")
            connection.execute(
                """
                CREATE TABLE world_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute("INSERT INTO world_events (content) VALUES (?)", ("Legacy event",))

        database.initialize_database()
        event = database.get_world_events(limit=1)[0]

        self.assertEqual(event["content"], "Legacy event")
        self.assertEqual(event["event_type"], "legacy")
        self.assertEqual(event["visibility"], "public")
        self.assertEqual(event["payload"], {})

    def test_inbox_tick_log_mailbox_plan_cooldown_and_runtime_state(self) -> None:
        event = database.create_world_event(
            event_type="badge_evidence_verified",
            content="Ron verified the guard badge evidence.",
            source_type="system",
            source_id="demo",
            location_id="guard_post",
            visibility="npc_only",
            payload={"target_npc_ids": ["ron"]},
        )
        inbox_item = database.add_npc_event_inbox_item(
            npc_id="ron",
            event_id=event["id"],
            relevance_score=0.95,
            reason="explicit_target",
        )
        inbox = database.get_npc_event_inbox("ron", include_seen=True)
        database.mark_npc_event_seen(inbox_item["id"])

        message = database.create_proactive_message(
            npc_id="ron",
            content="Bring that badge to the guard post. I can verify it now.",
            trigger_event_id=event["id"],
            tick_log_id=None,
            priority=8,
        )
        pending_messages = database.get_proactive_messages(npc_id="ron", delivered=False)
        database.mark_proactive_message_delivered(message["id"])

        plan = database.upsert_npc_plan(
            npc_id="ron",
            goal="maintain_gate_security",
            steps=[{"step": "verify_badge", "status": "active"}],
            current_step="verify_badge",
            status="blocked",
            blocker="badge evidence missing",
            source_event_id=event["id"],
        )
        cooldown = database.set_npc_cooldown(
            npc_id="ron",
            cooldown_key="ron:badge_evidence_verified:verify_badge",
            until_turn_or_timestamp="2099-01-01T00:00:00+00:00",
            reason="prevent repeated gate prompt",
        )
        runtime = database.upsert_npc_runtime_state(
            npc_id="ron",
            lifecycle_status="paused",
            tick_enabled=False,
        )
        tick_log = database.log_autonomous_tick(
            npc_id="ron",
            trigger_event_id=event["id"],
            mode="llm_constrained",
            observation={"trigger_event": event},
            retrieved_memories=[],
            available_actions=[{"action_type": "verify_badge"}],
            unavailable_actions=[{"action_type": "grant_conditional_access", "reason": "badge evidence missing"}],
            llm_decision={"goal": "maintain_gate_security"},
            proposed_action={"action_type": "verify_badge"},
            validation={"status": "allowed"},
            action_result={"accepted": True},
            plan_update=plan,
            memory_candidate={"content": "Ron verified badge evidence."},
            reflection={"summary": "Ron should stay procedural."},
            proactive_message_id=message["id"],
        )

        self.assertEqual(inbox[0]["event"]["event_type"], "badge_evidence_verified")
        self.assertTrue(database.get_npc_event_inbox("ron", include_seen=True)[0]["seen"])
        self.assertEqual(pending_messages[0]["content"], message["content"])
        self.assertEqual(database.get_proactive_messages(npc_id="ron", delivered=False), [])
        self.assertEqual(database.get_npc_plan("ron")["blocker"], "badge evidence missing")
        self.assertEqual(cooldown["cooldown_key"], "ron:badge_evidence_verified:verify_badge")
        self.assertEqual(database.get_npc_runtime_state("ron")["lifecycle_status"], "paused")
        self.assertFalse(runtime["tick_enabled"])
        self.assertEqual(database.get_autonomous_tick_log(tick_log["id"])["llm_decision"]["goal"], "maintain_gate_security")


if __name__ == "__main__":
    unittest.main()
