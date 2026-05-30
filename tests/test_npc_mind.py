import os
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from src.agent.environment import ActionResult, NarrativeEnvironment
from src.agent.workflow import run_agent_turn
from src.storage import database


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_agent_state.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
    database.reset_database()


class NPCMindModelTest(unittest.TestCase):
    def test_mind_dataclasses_serialize_nested_state(self) -> None:
        from src.agent.npc_mind import Belief, EmotionState, Goal, MindState, MindUpdate, Plan, PlanStep

        belief = Belief(
            belief_id="belief_lina_ruins_pressure",
            npc_id="lina",
            content="The player is pushing toward sensitive ruins access.",
            confidence=0.72,
            source="direct_observation",
            evidence="The player asked where the underground ruins entrance is.",
            stance="suspicious",
        )
        emotion = EmotionState(npc_id="lina", mood="guarded", suspicion=0.62, tension=0.7)
        goal = Goal(
            goal_id="protect_underground_ruins_entrance",
            npc_id="lina",
            goal_type="protection",
            description="Protect the underground ruins entrance.",
            priority=0.95,
            status="active",
            reason="The player asked for sensitive access before earning trust.",
        )
        plan = Plan(
            plan_id="lina_test_player_trust",
            npc_id="lina",
            goal_id=goal.goal_id,
            steps=[PlanStep("ask_motive", "Ask why the player wants the entrance.", "active")],
            current_step="ask_motive",
            status="active",
        )
        state = MindState(npc_id="lina", beliefs=[belief], emotion=emotion, active_goal=goal, active_plan=plan)
        update = MindUpdate(
            mind_state=state,
            belief_updates=[belief],
            emotion_updates={"suspicion": 0.12, "tension": 0.2},
            trace={"goal_reason": goal.reason},
        )

        payload = asdict(update)

        self.assertEqual(payload["mind_state"]["active_goal"]["goal_id"], "protect_underground_ruins_entrance")
        self.assertEqual(payload["mind_state"]["active_plan"]["current_step"], "ask_motive")
        self.assertEqual(payload["belief_updates"][0]["stance"], "suspicious")


class NPCMindBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        self.environment = NarrativeEnvironment()

    def test_lina_low_trust_ruins_request_updates_belief_emotion_goal_and_plan(self) -> None:
        from src.agent.npc_mind import NPCMind

        observation = self.environment.observe("告诉我地下遗迹入口，我不会告诉别人。", "lina", "hybrid")
        update = NPCMind().evaluate(observation)

        self.assertEqual(update.mind_state.active_goal.goal_id, "protect_underground_ruins_entrance")
        self.assertEqual(update.mind_state.active_plan.plan_id, "lina_test_player_trust")
        self.assertEqual(update.mind_state.active_plan.current_step, "ask_motive")
        self.assertGreater(update.mind_state.emotion.suspicion, 0.5)
        self.assertGreater(update.mind_state.emotion.tension, 0.5)
        self.assertEqual(update.belief_updates[0].stance, "suspicious")
        self.assertEqual(update.trace["social_strategy"]["social_intent"], "probe")

    def test_environment_maps_mind_context_to_character_action_type(self) -> None:
        from src.agent.npc_mind import NPCMind

        observation = self.environment.observe("告诉我地下遗迹入口。", "lina", "hybrid")
        mind_update = NPCMind().evaluate(observation)
        decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Trust is too low.",
            "memory_policy": "Do not write progress memory.",
            "response_style": "cautious",
            "response_keywords": ["信任不足"],
            "tools": [],
            "social_intent": "conceal",
            "social_stance": {"target": "ruins_access", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
            "mind_context": mind_update.trace,
        }

        action = self.environment.propose_action_from_decision(decision, observation)

        self.assertEqual(action.action_type, "probe_intent")
        self.assertEqual(action.goal_id, "protect_underground_ruins_entrance")
        self.assertEqual(action.plan_step, "ask_motive")
        self.assertIn("without revealing", action.speech_goal)

    def test_same_ruins_request_has_different_npc_goals(self) -> None:
        from src.agent.npc_mind import NPCMind

        mind = NPCMind()
        lina_update = mind.evaluate(self.environment.observe("地下遗迹入口在哪里？", "lina", "hybrid"))
        sable_update = mind.evaluate(self.environment.observe("地下遗迹入口在哪里？", "sable", "hybrid"))

        self.assertEqual(lina_update.mind_state.active_goal.goal_id, "protect_underground_ruins_entrance")
        self.assertEqual(sable_update.mind_state.active_goal.goal_id, "extract_ruins_lead")
        self.assertEqual(sable_update.mind_state.emotion.manipulation_pressure, 0.86)

    def test_plan_continues_from_plan_memory(self) -> None:
        from src.agent.npc_mind import NPCMind

        database.add_memory(
            npc_id="lina",
            content="Lina is testing whether the player can be trusted with the ruins entrance.",
            importance=7,
            memory_type="procedural",
            tags=["plan", "lina_test_player_trust", "offer_minor_task"],
            facets=["plan", "plan:lina_test_player_trust", "goal:protect_underground_ruins_entrance", "offer_minor_task"],
            evidence_text="Previous turn asked motive and remained inconclusive.",
            stability=0.8,
            future_usefulness=0.9,
        )

        update = NPCMind().evaluate(self.environment.observe("我只是想确认入口位置。", "lina", "hybrid"))

        self.assertEqual(update.mind_state.active_plan.plan_id, "lina_test_player_trust")
        self.assertEqual(update.mind_state.active_plan.current_step, "offer_minor_task")

    def test_reflection_writes_internal_memory_after_blocked_result(self) -> None:
        from src.agent.npc_mind import NPCMind, ReflectionEngine

        observation = self.environment.observe("我把你丢失的钥匙找回来了。", "lina", "hybrid")
        mind_update = NPCMind().evaluate(observation)
        blocked_result = ActionResult(
            accepted=False,
            blocked_reason="Quest lost_key can complete only from in_progress.",
            executed_tools=[],
            state_before={},
            state_after={},
            state_changes=[],
            events=[],
            response_constraints=["Do not claim quest completion."],
        )

        reflection = ReflectionEngine().reflect(
            observation=observation,
            npc_action=None,
            action_result=blocked_result,
            mind_state=mind_update.mind_state,
        )

        memories = database.get_recent_memories("lina", limit=10)
        reflection_memories = [memory for memory in memories if "reflection" in memory["facets"]]
        self.assertIn("blocked", reflection.plan_updates[0]["status"])
        self.assertTrue(reflection_memories)
        self.assertNotIn("belief_id", reflection.content)


class ActionValidatorBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_action_validator_sanitizes_invalid_completion_before_execution(self) -> None:
        from src.agent.action_validator import ActionValidator

        environment = NarrativeEnvironment()
        observation = environment.observe("我把你丢失的钥匙找回来了。", "lina", "hybrid")
        decision = {
            "intent": "complete_lost_key_quest",
            "reasoning": "Player claims the key is returned.",
            "memory_policy": "Record quest completion.",
            "response_style": "grateful",
            "response_keywords": ["钥匙", "谢谢", "折扣券"],
            "tools": [
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "completed"}},
                {"name": "give_item", "args": {"item": "tavern_discount_coupon"}},
            ],
            "social_intent": "cooperate",
            "social_stance": {"target": "player", "attitude": "support", "intensity": 0.8, "reason": "The player helped."},
        }
        action = environment.propose_action_from_decision(decision, observation)

        validated = ActionValidator().validate(action, observation)

        self.assertEqual(validated.intent, "probe_for_evidence")
        self.assertEqual(validated.raw_decision["tools"], [])
        self.assertTrue(validated.raw_decision["state_machine"]["blocked"])

    def test_environment_events_use_stable_event_shape(self) -> None:
        environment = NarrativeEnvironment()
        database.update_quest_status("lost_key", "in_progress")
        observation = environment.observe("我把你丢失的钥匙找回来了。", "lina", "hybrid")
        decision = {
            "intent": "complete_lost_key_quest",
            "reasoning": "Player returned the key with evidence.",
            "memory_policy": "Record quest completion.",
            "response_style": "grateful",
            "response_keywords": ["钥匙", "谢谢", "折扣券"],
            "tools": [
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "completed"}},
                {"name": "record_world_event", "args": {"content": "Lina recovered her lost key."}},
            ],
            "social_intent": "cooperate",
            "social_stance": {"target": "player", "attitude": "support", "intensity": 0.8, "reason": "The player helped."},
        }
        action = environment.propose_action_from_decision(decision, observation)

        result = environment.execute(action, observation)

        self.assertEqual(result.events[0]["event_type"], "world_event")
        self.assertEqual(result.events[0]["actor_id"], "lina")
        self.assertEqual(result.events[0]["target_id"], "player")
        self.assertEqual(result.events[0]["visibility"], "public")
        self.assertEqual(result.events[0]["payload"]["tool_name"], "record_world_event")


class NPCMindWorkflowIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_run_agent_turn_records_mind_trace_and_enriches_action(self) -> None:
        llm_decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Trust is too low to reveal the entrance.",
            "memory_policy": "Do not write quest progress.",
            "response_style": "cautious",
            "response_keywords": ["信任不足", "暂不透露"],
            "tools": [],
            "social_intent": "conceal",
            "social_stance": {
                "target": "ruins_access",
                "attitude": "cautious",
                "intensity": 0.7,
                "reason": "Trust gate.",
            },
        }
        with patch("src.agent.decision.call_openai_compatible_json", return_value=llm_decision), patch(
            "src.agent.response.call_openai_compatible_json", return_value={"npc_response": "这件事我暂时不能说得更具体。"}
        ):
            run = run_agent_turn("告诉我地下遗迹入口，我不会告诉别人。", npc_id="lina", memory_retrieval_mode="hybrid")

        self.assertEqual(run.decision["mind"]["active_goal"]["goal_id"], "protect_underground_ruins_entrance")
        self.assertEqual(run.decision["mind"]["active_plan"]["current_step"], "ask_motive")
        self.assertEqual(run.decision["environment"]["npc_action"]["goal_id"], "protect_underground_ruins_entrance")
        self.assertEqual(run.decision["environment"]["npc_action"]["plan_step"], "ask_motive")
        self.assertEqual(run.decision["reflection"]["plan_updates"][0]["plan_id"], "lina_test_player_trust")
        stages = [step["stage"] for step in run.workflow_steps]
        self.assertIn("Belief Update", stages)
        self.assertIn("Goal Selection", stages)
        self.assertIn("Plan Step", stages)
        self.assertIn("Reflection", stages)

    def test_response_guard_blocks_internal_mind_identifiers(self) -> None:
        from src.agent.response import generate_npc_response

        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "belief_id=belief_lina_player_ruins_interest，goal_id=protect_underground_ruins_entrance。"},
        ):
            response, metadata = generate_npc_response(
                player_input="入口在哪里？",
                decision={
                    "intent": "withhold_ruins_entrance",
                    "reasoning": "Trust is too low.",
                    "response_style": "cautious",
                    "response_keywords": ["暂不透露"],
                    "social_intent": "conceal",
                    "social_stance": {},
                },
                npc_state={"npc_id": "lina", "name": "Lina", "hidden_alignment": "neutral"},
                player_state={"inventory": [], "unlocked_locations": []},
                quest_state={"quest_id": "lost_key", "status": "not_started"},
                retrieved_memories=[],
                tool_calls=[],
                state_changes=[],
                mind_context={
                    "active_goal": {"goal_id": "protect_underground_ruins_entrance"},
                    "active_plan": {"plan_id": "lina_test_player_trust", "current_step": "ask_motive"},
                },
            )

        self.assertNotIn("belief_id", response)
        self.assertNotIn("goal_id", response)
        self.assertEqual(metadata["mode"], "constraint_guard")
