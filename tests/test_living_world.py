import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


TEST_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "test_living_world.db"
os.environ["AGENT_NPC_DB_PATH"] = str(TEST_DB_PATH)
os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"

from src.api.server import app  # noqa: E402
from src.storage import database  # noqa: E402


class LivingWorldStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_reset_seeds_arc_scene_objects_locations_and_routines(self) -> None:
        arc = database.get_world_arc_state("ruins_chapter_1")
        objects = {item["object_id"]: item for item in database.list_scene_objects()}
        locations = {item["npc_id"]: item for item in database.list_npc_locations()}
        routines = {item["npc_id"]: item for item in database.list_npc_routines()}

        self.assertEqual(arc["arc_id"], "ruins_chapter_1")
        self.assertEqual(arc["phase"], "rumor")
        self.assertEqual(arc["tension"], 0)
        self.assertEqual(arc["advantage"], "none")
        self.assertEqual(arc["outcome"], "")
        self.assertEqual(
            set(objects),
            {"tavern_back_alley", "guard_ledger", "mira_field_notes", "sable_rumor_stall"},
        )
        self.assertEqual(objects["tavern_back_alley"]["location_id"], "tavern")
        self.assertEqual(objects["tavern_back_alley"]["state"]["observed"], False)
        self.assertEqual(locations["lina"]["location_id"], "tavern")
        self.assertEqual(locations["ron"]["location_id"], "guard_post")
        self.assertEqual(routines["mira"]["routine_type"], "research")
        self.assertTrue(routines["sable"]["enabled"])


class PlayerActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.client = TestClient(app)

    def test_investigate_scene_updates_object_and_dispatches_event(self) -> None:
        response = self.client.post(
            "/api/player/actions",
            json={
                "action_type": "investigate_scene",
                "target_id": "tavern_back_alley",
                "content": "我查看酒馆后巷有没有异常痕迹。",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        event = payload["created_events"][0]
        scene_object = database.get_scene_object("tavern_back_alley")
        inbox = database.get_npc_event_inbox("lina")

        self.assertEqual(payload["action_result"]["status"], "accepted")
        self.assertEqual(event["event_type"], "player_investigated_scene")
        self.assertEqual(event["payload"]["target_id"], "tavern_back_alley")
        self.assertTrue(scene_object["state"]["observed"])
        self.assertEqual(scene_object["state"]["last_player_action"], "investigate_scene")
        self.assertTrue(inbox)
        self.assertEqual(inbox[0]["event"]["id"], event["id"])
        self.assertIn("arc_state", payload)

    def test_wait_creates_routine_events_without_completing_quests(self) -> None:
        response = self.client.post(
            "/api/player/actions",
            json={"action_type": "wait", "content": "我在镇上等一会儿。"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        event_types = {event["event_type"] for event in payload["created_events"]}

        self.assertIn("npc_routine_activity", event_types)
        self.assertEqual(database.get_quest("lost_key")["status"], "not_started")
        self.assertEqual(database.get_quest("gate_badge")["status"], "not_started")

    def test_invalid_player_action_target_is_rejected(self) -> None:
        response = self.client.post(
            "/api/player/actions",
            json={"action_type": "investigate_scene", "target_id": "missing_place"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown scene object", response.json()["detail"])


class WorldArcResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_resolver_can_produce_all_demo_outcomes(self) -> None:
        from src.agent.world_arc import resolve_arc_outcome

        cases = {
            "guardian_advantage": {"guardian": 3, "research": 0, "sable": 0, "chaos": 0},
            "research_advantage": {"guardian": 0, "research": 3, "sable": 0, "chaos": 0},
            "sable_advantage": {"guardian": 0, "research": 0, "sable": 3, "chaos": 0},
            "chaotic_lockdown": {"guardian": 0, "research": 0, "sable": 0, "chaos": 3},
        }

        for expected, scores in cases.items():
            with self.subTest(expected=expected):
                result = resolve_arc_outcome(scores=scores)
                self.assertEqual(result["arc_outcome"], expected)

    def test_director_rejects_illegal_state_change_requests(self) -> None:
        from src.agent.arc_director import run_arc_director

        llm_payload = {
            "arc_outcome": "sable_advantage",
            "confidence": 0.9,
            "reason": "Sable has leverage.",
            "recommended_events": [
                {
                    "event_type": "sable_pressed_lead",
                    "content": "Sable pushes an unreliable lead.",
                    "visibility": "npc_only",
                    "target_npc_ids": ["sable"],
                }
            ],
            "state_change_requests": [
                {"field": "outcome", "value": "sable_advantage"},
                {"field": "unlock_location", "value": "underground_ruins_entrance"},
            ],
            "npc_reaction_hints": [{"npc_id": "sable", "hint": "press advantage"}],
        }

        with patch("src.agent.arc_director.call_openai_compatible_json", return_value=llm_payload):
            result = run_arc_director(use_llm=True)

        self.assertEqual(result["arc_outcome"], "sable_advantage")
        self.assertEqual(database.get_world_arc_state("ruins_chapter_1")["outcome"], "sable_advantage")
        self.assertEqual(result["rejected_state_change_requests"][0]["field"], "unlock_location")
        self.assertNotIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])


class LivingWorldAutonomousTickTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_same_ruins_event_has_distinct_npc_action_surfaces(self) -> None:
        from src.agent.action_catalog import get_available_actions

        event = {
            "event_type": "player_investigated_scene",
            "payload": {"target_id": "tavern_back_alley"},
        }

        by_npc = {
            npc_id: {action["action_type"] for action in get_available_actions(npc_id, trigger_event=event)}
            for npc_id in ["lina", "ron", "mira", "sable"]
        }

        self.assertIn("secure_tavern_back_alley", by_npc["lina"])
        self.assertIn("patrol_sensitive_route", by_npc["ron"])
        self.assertIn("request_field_notes", by_npc["mira"])
        self.assertIn("plant_misleading_tip", by_npc["sable"])
        self.assertNotIn("unlock_location", by_npc["sable"])

    def test_autonomous_tick_trace_includes_arc_context_and_director(self) -> None:
        from src.agent.autonomous_tick import run_autonomous_tick
        from src.agent.event_visibility import dispatch_world_event_to_inbox

        event = database.create_world_event(
            event_type="player_shared_rumor",
            content="Player repeated Sable's rumor about the ruins.",
            source_type="player_action",
            source_id="test",
            location_id="market",
            visibility="npc_only",
            payload={"target_npc_ids": ["sable"], "arc_signal": "sable"},
        )
        dispatch_world_event_to_inbox(event)
        llm_decision = {
            "goal": "exploit_ruins_lead",
            "plan_step": "plant_misleading_tip",
            "selected_action": {
                "action_type": "plant_misleading_tip",
                "args": {"rumor_theme": "guard_shift", "message_intent": "redirect"},
            },
            "proactive_message": "你可以先去看看换岗记录，那里的人嘴更松。",
            "memory_candidate": "Player echoed a ruins rumor near Sable.",
            "reflection_summary": "Sable can press the rumor advantage.",
        }

        with patch("src.agent.autonomous_tick.call_openai_compatible_json", return_value=llm_decision):
            result = run_autonomous_tick("sable", trigger_event_id=int(event["id"]))

        self.assertIn("arc_state", result.observation)
        self.assertIn("scene_objects", result.observation)
        self.assertIn("npc_location", result.observation)
        self.assertIn("arc_director", result.observation)
        self.assertEqual(result.proposed_action["action_type"], "plant_misleading_tip")
        self.assertNotIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])


if __name__ == "__main__":
    unittest.main()
