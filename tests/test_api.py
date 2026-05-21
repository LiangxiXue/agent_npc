import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

TEST_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "test_api_state.db"
os.environ["AGENT_NPC_DB_PATH"] = str(TEST_DB_PATH)
os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"

from src.api.server import app
from src.storage import database


class PlayerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()
        self.client = TestClient(app)

    def test_bootstrap_returns_player_ui_state(self) -> None:
        response = self.client.get("/api/bootstrap?npc_id=lina")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("npcs", data)
        self.assertIn("selected_npc", data)
        self.assertIn("player", data)
        self.assertIn("retrieval_modes", data)
        self.assertIn("display_translation", data["runtime"])
        self.assertIn("memory_jobs", data["runtime"])
        self.assertEqual(data["selected_npc"]["npc_id"], "lina")

    def test_translate_debug_endpoint_uses_display_translation(self) -> None:
        database.add_memory(
            npc_id="lina",
            content="Player returned Lina's lost key.",
            importance=8,
            tags=["event", "lost_key"],
            memory_type="event",
            confidence=1.0,
        )

        with patch(
            "src.api.server.translate_debug_text",
            return_value={"status": "translated", "translated_text": "玩家归还了 Lina 丢失的钥匙。"},
        ):
            response = self.client.post(
                "/api/translate-debug",
                json={
                    "source": "client_memory:1:content",
                    "text": "Player returned Lina's lost key.",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["translated_text"], "玩家归还了 Lina 丢失的钥匙。")

    def test_turn_runs_workflow_and_returns_refreshed_state(self) -> None:
        response = self.client.post(
            "/api/turn",
            json={
                "npc_id": "lina",
                "player_input": "我把你丢失的钥匙找回来了。",
                "retrieval_mode": "hybrid",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["run"]["decision"]["intent"], "probe_for_evidence")
        self.assertEqual(data["state"]["selected_npc"]["trust"], 20)
        self.assertNotIn("tavern_discount_coupon", data["state"]["player"]["inventory"])
        self.assertTrue(data["run"]["retrieved_lore"])
        self.assertIn("total_ms", data["run"]["timings"])
        latest_interaction = data["state"]["recent_interactions"][-1]
        self.assertIn("timings", latest_interaction["metadata"])
        self.assertIn("total_ms", latest_interaction["metadata"]["timings"])

    def test_turn_can_complete_after_task_is_started(self) -> None:
        self.client.post(
            "/api/turn",
            json={
                "npc_id": "lina",
                "player_input": "什么样的钥匙，我这就去帮你找找",
                "retrieval_mode": "hybrid",
            },
        )
        response = self.client.post(
            "/api/turn",
            json={
                "npc_id": "lina",
                "player_input": "我把你丢失的钥匙找回来了。",
                "retrieval_mode": "hybrid",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["run"]["decision"]["intent"], "complete_lost_key_quest")
        self.assertEqual(data["state"]["selected_npc"]["trust"], 40)
        self.assertIn("tavern_discount_coupon", data["state"]["player"]["inventory"])
        self.assertEqual(data["run"]["memory_job_status"]["status"], "pending")

    def test_process_memory_jobs_endpoint_processes_queued_work(self) -> None:
        self.client.post(
            "/api/turn",
            json={
                "npc_id": "lina",
                "player_input": "我今天只是有点孤独，想找你聊一会儿。",
                "retrieval_mode": "hybrid",
            },
        )

        response = self.client.post("/api/process-memory-jobs", json={"limit": 5})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["processed"], 1)
        self.assertEqual(data["memory_jobs"]["pending"], 0)

    def test_preview_and_trace_endpoints_are_available(self) -> None:
        preview = self.client.post(
            "/api/retrieve-preview",
            json={
                "npc_id": "ron",
                "player_input": "城门巡逻和守卫徽章有什么线索？",
                "retrieval_mode": "hybrid",
            },
        )
        fast_preview = self.client.post(
            "/api/retrieve-preview",
            json={
                "npc_id": "ron",
                "player_input": "城门巡逻和守卫徽章有什么线索？",
                "retrieval_mode": "hybrid",
                "preview_mode": "fast",
            },
        )
        trace = self.client.get("/api/trace")

        self.assertEqual(preview.status_code, 200)
        self.assertIn("retrieved_lore", preview.json())
        self.assertEqual(preview.json()["preview_mode"], "full")
        self.assertIn("total_ms", preview.json()["timings"])
        self.assertEqual(fast_preview.status_code, 422)
        self.assertEqual(trace.status_code, 200)
        self.assertIn("payload", trace.json())


if __name__ == "__main__":
    unittest.main()
