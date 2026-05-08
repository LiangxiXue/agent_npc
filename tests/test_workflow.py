import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.decision import decide_next_action, validate_decision
from src.agent.llm_client import get_provider_status
from src.agent.response import generate_npc_response
from src.agent.workflow import run_agent_turn
from src.storage import database


class AgentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_agent_state.db"
        os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"
        os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"

    def setUp(self) -> None:
        database.reset_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"

    def test_low_trust_ruins_question_is_withheld(self) -> None:
        run = run_agent_turn("我想打听一下地下遗迹的入口。")

        self.assertEqual(run.decision["intent"], "withhold_ruins_entrance")
        self.assertNotIn("underground_ruins_entrance", run.player_state["unlocked_locations"])
        self.assertEqual(database.get_npc("lina")["trust"], 20)

    def test_returning_key_updates_state_and_logs_tools(self) -> None:
        run = run_agent_turn("我把你丢失的钥匙找回来了。")
        tool_names = [tool["name"] for tool in run.tool_calls]

        self.assertEqual(run.decision["intent"], "complete_lost_key_quest")
        self.assertEqual(database.get_npc("lina")["trust"], 30)
        self.assertEqual(database.get_npc("lina")["affection"], 38)
        self.assertEqual(database.get_quest("lost_key")["status"], "completed")
        self.assertIn("tavern_discount_coupon", database.get_player_state()["inventory"])
        self.assertIn("add_memory", tool_names)
        self.assertIn("update_trust", tool_names)
        self.assertIn("update_affection", tool_names)
        self.assertIn("give_item", tool_names)
        self.assertGreaterEqual(len(run.workflow_steps), 8)

    def test_asking_key_details_starts_lost_key_quest(self) -> None:
        run = run_agent_turn("什么样的钥匙，我这就去帮你找找")
        tool_names = [tool["name"] for tool in run.tool_calls]

        self.assertEqual(run.decision["intent"], "start_lost_key_quest")
        self.assertEqual(database.get_quest("lost_key")["status"], "in_progress")
        self.assertEqual(database.get_npc("lina")["trust"], 30)
        self.assertIn("update_quest_status", tool_names)
        self.assertNotIn("unlock_location", tool_names)

    def test_completed_quest_allows_ruins_unlock(self) -> None:
        run_agent_turn("我把你丢失的钥匙找回来了。")
        run = run_agent_turn("上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？")

        self.assertEqual(run.decision["intent"], "reveal_ruins_entrance")
        self.assertTrue(any("lost_key" in memory["tags"] for memory in run.retrieved_memories))
        self.assertIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])
        self.assertEqual(len(database.get_interaction_logs()), 2)
        self.assertEqual(database.get_world_events(limit=1)[0]["content"], "Lina revealed the underground ruins entrance.")

    def test_logs_store_trace_artifacts(self) -> None:
        run = run_agent_turn("我把你丢失的钥匙找回来了。")
        logs = database.get_interaction_logs()

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["decision"]["intent"], run.decision["intent"])
        self.assertEqual(logs[0]["workflow_steps"][0]["stage"], "Player Input")
        self.assertEqual(logs[0]["tool_calls"][0]["name"], "add_memory")
        self.assertTrue(logs[0]["state_changes"])

    def test_default_decision_has_llm_ready_shape(self) -> None:
        run = run_agent_turn("你好，Lina。")

        self.assertNotIn("state_summary", run.decision)
        self.assertIn("state_before", run.decision)
        self.assertIn("state_after", run.decision)
        self.assertEqual(run.decision["state_before"]["npc"]["trust"], 20)
        self.assertEqual(run.decision["state_after"]["npc"]["trust"], 20)
        self.assertIn("memory_policy", run.decision)
        self.assertIn("response_style", run.decision)
        self.assertIn("response_keywords", run.decision)
        self.assertIn("response_generation", run.decision)
        self.assertIsInstance(run.decision["tools"], list)
        self.assertEqual(run.decision["response_generation"]["mode"], "fallback_template")

    def test_response_generation_can_use_llm_polish(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        decision = {
            "intent": "general_conversation",
            "reasoning": "test",
            "response_style": "attentive_neutral",
            "response_keywords": ["记住", "谨慎"],
        }

        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "Lina 点点头：“这件事我会记住，但我还要再观察一下。”"},
        ):
            response, metadata = generate_npc_response(
                player_input="你好",
                decision=decision,
                npc_state=database.get_npc("lina"),
                player_state=database.get_player_state(),
                quest_state=database.get_quest("lost_key"),
                retrieved_memories=[],
                tool_calls=[],
                state_changes=[],
            )

        self.assertIn("我会记住", response)
        self.assertEqual(metadata["mode"], "llm_polish")

    def test_response_generation_rejects_major_fact_conflict(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        decision = {
            "intent": "reveal_ruins_entrance",
            "reasoning": "test",
            "response_style": "secretive_but_helpful",
            "response_keywords": ["地下遗迹", "酒馆后巷"],
        }

        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "入口就在镇子北边的枯井里。"},
        ):
            response, metadata = generate_npc_response(
                player_input="入口在哪",
                decision=decision,
                npc_state=database.get_npc("lina"),
                player_state=database.get_player_state(),
                quest_state=database.get_quest("lost_key"),
                retrieved_memories=[],
                tool_calls=[],
                state_changes=[],
            )

        self.assertIn("酒馆后巷", response)
        self.assertEqual(metadata["mode"], "fallback_template")

    def test_openai_compatible_without_key_stays_runnable(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        npc_state = database.get_npc("lina")
        player_state = database.get_player_state()
        quest_state = database.get_quest("lost_key")
        decision = decide_next_action(
            player_input="我想打听一下地下遗迹的入口。",
            npc_state=npc_state,
            player_state=player_state,
            quest_state=quest_state,
            memories=[],
        )

        self.assertFalse(get_provider_status()["configured"])
        self.assertEqual(decision["intent"], "withhold_ruins_entrance")

    def test_decision_rejects_unsupported_tools(self) -> None:
        with self.assertRaises(ValueError):
            validate_decision(
                {
                    "intent": "bad_tool",
                    "reasoning": "test",
                    "memory_policy": "none",
                    "response_style": "none",
                    "response_keywords": [],
                    "tools": [{"name": "delete_database", "args": {}}],
                }
            )

    def test_decision_normalizes_llm_intent_aliases(self) -> None:
        decision = validate_decision(
            {
                "intent": "complete_quest_return_key",
                "reasoning": "test",
                "memory_policy": "test",
                "response_style": "grateful",
                "response_keywords": ["thanks"],
                "tools": [
                    {
                        "name": "update_quest_status",
                        "args": {"quest_id": "lost_key", "status": "completed"},
                    }
                ],
            }
        )

        self.assertEqual(decision["intent"], "complete_lost_key_quest")

    def test_decision_rejects_invalid_tool_args(self) -> None:
        invalid_decisions = [
            {
                "intent": "bad_args",
                "reasoning": "test",
                "memory_policy": "none",
                "response_style": "none",
                "response_keywords": [],
                "tools": [{"name": "add_memory", "args": {"type": "memory"}}],
            },
            {
                "intent": "missing_args",
                "reasoning": "test",
                "memory_policy": "none",
                "response_style": "none",
                "response_keywords": [],
                "tools": [{"name": "update_trust", "args": {"delta": 10}}],
            },
        ]

        for decision in invalid_decisions:
            with self.subTest(decision=decision["intent"]):
                with self.assertRaises(ValueError):
                    validate_decision(decision)

    def test_decision_rejects_business_rule_conflicts(self) -> None:
        invalid_decisions = [
            {
                "intent": "withhold_ruins_entrance",
                "reasoning": "test",
                "memory_policy": "none",
                "response_style": "none",
                "response_keywords": [],
                "tools": [{"name": "unlock_location", "args": {"location": "underground_ruins_entrance"}}],
            },
            {
                "intent": "start_lost_key_quest",
                "reasoning": "test",
                "memory_policy": "none",
                "response_style": "none",
                "response_keywords": [],
                "tools": [
                    {
                        "name": "update_quest_status",
                        "args": {"quest_id": "lost_key", "status": "completed"},
                    }
                ],
            },
        ]

        for decision in invalid_decisions:
            with self.subTest(decision=decision["intent"]):
                with self.assertRaises(ValueError):
                    validate_decision(decision)

    def test_reveal_memory_is_normalized_to_lina_as_actor(self) -> None:
        decision = validate_decision(
            {
                "intent": "reveal_ruins_entrance",
                "reasoning": "test",
                "memory_policy": "test",
                "response_style": "warm",
                "response_keywords": ["ruins"],
                "tools": [
                    {"name": "unlock_location", "args": {"location": "underground_ruins_entrance"}},
                    {
                        "name": "add_memory",
                        "args": {
                            "npc_id": "lina",
                            "content": "Player revealed the ruins entrance after returning the lost key.",
                            "importance": 7,
                            "tags": ["ruins"],
                        },
                    },
                ],
            }
        )

        memory_tool = next(tool for tool in decision["tools"] if tool["name"] == "add_memory")
        self.assertTrue(memory_tool["args"]["content"].startswith("Lina revealed"))
        self.assertIn("location", memory_tool["args"]["tags"])


if __name__ == "__main__":
    unittest.main()
