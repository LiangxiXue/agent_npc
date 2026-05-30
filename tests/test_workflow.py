import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.decision import decide_next_action, validate_decision
from src.agent.lore_retrieval import retrieve_lore
from src.agent.llm_client import get_provider_status
from src.agent.memory_jobs import process_pending_memory_jobs
from src.agent.memory_policy import MemoryPolicyInput, apply_memory_policy
from src.agent.response import generate_npc_response
from src.agent.workflow import run_agent_turn
from src.storage import database


def fake_response_json(*_: object, **__: object) -> dict[str, str]:
    return {"npc_response": "我明白了，但现在还需要谨慎处理。"}


def fake_decision_json(*_: object, **kwargs: object) -> dict[str, object]:
    from src.agent.decision import mock_decide_next_action

    payload = kwargs.get("user_payload", {})
    if not isinstance(payload, dict):
        payload = {}
    return mock_decide_next_action(
        str(payload.get("player_input", "")),
        payload.get("npc_state", {}) if isinstance(payload.get("npc_state"), dict) else {},
        payload.get("player_state", {}) if isinstance(payload.get("player_state"), dict) else {},
        payload.get("quest_state", {}) if isinstance(payload.get("quest_state"), dict) else {},
        payload.get("retrieved_long_term_memories", [])
        if isinstance(payload.get("retrieved_long_term_memories"), list)
        else [],
        payload.get("recent_short_term_context", [])
        if isinstance(payload.get("recent_short_term_context"), list)
        else [],
    )


def fake_memory_candidate_json(*_: object, **kwargs: object) -> dict[str, list[dict[str, object]]]:
    payload = kwargs.get("user_payload", {})
    if not isinstance(payload, dict):
        payload = {}
    text = str(payload.get("player_input", "")).lower()
    tool_calls = payload.get("tool_calls", [])
    tool_names = [tool.get("name") for tool in tool_calls if isinstance(tool, dict)]
    state_before = payload.get("state_before", {})
    state_after = payload.get("state_after", {})
    quest_before = state_before.get("quest", {}) if isinstance(state_before, dict) else {}
    quest_after = state_after.get("quest", {}) if isinstance(state_after, dict) else {}
    candidates: list[dict[str, object]] = []

    if any(phrase in text for phrase in ["直接告诉", "直接说", "不要绕弯", "别绕弯", "direct hints"]):
        candidates.append(
            {
                "should_write": True,
                "memory_type": "procedural",
                "content": "Player prefers direct hints instead of vague clues.",
                "importance": 6,
                "confidence": 0.9,
                "tags": ["communication_style", "direct_hints"],
                "facets": ["communication_style", "direct_hints"],
                "scope": "player_global",
                "evidence_text": payload.get("player_input", ""),
                "stability": 0.85,
                "future_usefulness": 0.9,
                "reason": "The player explicitly stated a stable communication preference.",
            }
        )
    if any(phrase in text for phrase in ["我是新手", "新手", "不太熟悉", "i am new", "i'm new"]):
        candidates.append(
            {
                "should_write": True,
                "memory_type": "semantic",
                "content": "Player described themselves as new and may need extra context.",
                "importance": 5,
                "confidence": 0.85,
                "tags": ["player_profile", "experience_level"],
                "facets": ["player_profile", "experience_level"],
                "scope": "player_global",
                "evidence_text": payload.get("player_input", ""),
                "stability": 0.75,
                "future_usefulness": 0.8,
                "reason": "The player explicitly described their experience level.",
            }
        )
    if any(phrase in text for phrase in ["孤独", "无人会帮助", "lonely"]):
        candidates.append(
            {
                "should_write": True,
                "memory_type": "semantic",
                "content": "Player described themselves as lonely and worried nobody would help them.",
                "importance": 5,
                "confidence": 0.85,
                "tags": ["player_profile", "needs_support"],
                "facets": ["player_profile", "needs_support"],
                "scope": "player_global",
                "evidence_text": payload.get("player_input", ""),
                "stability": 0.55,
                "future_usefulness": 0.65,
                "reason": "The player explicitly described their emotional state.",
            }
        )
    if quest_before.get("status") != "completed" and quest_after.get("status") == "completed":
        quest_id = quest_after.get("quest_id", "quest")
        candidates.append(
            {
                "should_write": True,
                "memory_type": "episodic",
                "content": f"Player completed the {quest_id} quest.",
                "importance": 9,
                "confidence": 1.0,
                "tags": ["quest_completed", quest_id],
                "facets": ["quest_completed", quest_id],
                "scope": "npc_specific",
                "evidence_text": str(quest_after),
                "stability": 1.0,
                "future_usefulness": 0.9,
                "reason": "Quest status changed to completed.",
            }
        )
    if "give_item" in tool_names and quest_after.get("quest_id") == "lost_key":
        candidates.append(
            {
                "should_write": True,
                "memory_type": "episodic",
                "content": "Player returned Lina's lost key.",
                "importance": 8,
                "confidence": 1.0,
                "tags": ["helped_npc", "lost_key", "lina"],
                "facets": ["helped_npc", "lost_key", "lina"],
                "scope": "npc_specific",
                "evidence_text": "Player returned Lina's lost key.",
                "stability": 1.0,
                "future_usefulness": 0.85,
                "reason": "Tool execution indicates the key was returned.",
            }
        )
    if any(name in tool_names for name in ["update_trust", "update_affection"]) and not any(
        phrase in text for phrase in ["孤独", "无人会帮助", "lonely"]
    ):
        candidates.append(
            {
                "should_write": True,
                "memory_type": "relational",
                "content": "上次那件事之后，Player helped Lina and earned more trust.",
                "importance": 6,
                "confidence": 0.85,
                "tags": ["relationship", "trust"],
                "facets": ["relationship", "trust"],
                "scope": "npc_specific",
                "evidence_text": "update_trust",
                "stability": 0.7,
                "future_usefulness": 0.75,
                "reason": "Relationship state changed through tool execution.",
            }
        )
    if "unlock_location" in tool_names:
        candidates.append(
            {
                "should_write": True,
                "memory_type": "episodic",
                "content": "Lina revealed the underground ruins entrance to the player.",
                "importance": 7,
                "confidence": 1.0,
                "tags": ["sensitive_location", "ruins", "player_knowledge"],
                "facets": ["sensitive_location", "ruins", "player_knowledge"],
                "scope": "npc_specific",
                "evidence_text": "unlock_location",
                "stability": 1.0,
                "future_usefulness": 0.8,
                "reason": "A sensitive location was unlocked.",
            }
        )
    return {"candidates": candidates}


def fake_memory_review_json(*_: object, **kwargs: object) -> dict[str, list[dict[str, object]]]:
    payload = kwargs.get("user_payload", {})
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    reviews = []
    for index, candidate in enumerate(candidates if isinstance(candidates, list) else []):
        if not isinstance(candidate, dict):
            continue
        reviews.append(
            {
                "candidate_index": index,
                "verdict": "approve",
                "approved_memory_type": candidate.get("memory_type"),
                "approved_content": candidate.get("content"),
                "approved_importance": candidate.get("importance"),
                "approved_confidence": candidate.get("confidence"),
                "approved_tags": candidate.get("tags", []),
                "approved_facets": candidate.get("facets", candidate.get("tags", [])),
                "approved_scope": candidate.get("scope", "npc_specific"),
                "approved_evidence_text": candidate.get("evidence_text", ""),
                "approved_stability": candidate.get("stability", 0.5),
                "approved_future_usefulness": candidate.get("future_usefulness", 0.5),
                "reason": "Approved by patched memory review LLM.",
                "risk": "low",
            }
        )
    return {"reviews": reviews}


def reset_test_database() -> None:
    test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_agent_state.db"
    os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
    os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
    database.reset_database()
    os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
    os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"


class EnvironmentDataModelTest(unittest.TestCase):
    def test_environment_dataclasses_have_required_shape(self) -> None:
        from dataclasses import asdict
        from src.agent.environment import ActionResult, NPCAction, Observation

        observation = Observation(
            npc_id="lina",
            player_input="我想打听地下遗迹入口。",
            npc_state={"npc_id": "lina"},
            player_state={"inventory": []},
            quest_state={"quest_id": "lost_key", "status": "not_started"},
            recent_context=[],
            retrieved_lore=[],
            retrieved_memories=[],
            visible_world_events=[],
            memory_retrieval_mode="hybrid",
        )
        action = NPCAction(
            action_type="dialogue",
            intent="withhold_ruins_entrance",
            target="player",
            subject="underground_ruins_entrance",
            reason="Trust is too low.",
            response_style="cautious",
            response_keywords=["信任不足", "暂不透露"],
            social_intent="withhold",
            social_stance={"target": "player", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
            proposed_effects=[],
            raw_decision={"intent": "withhold_ruins_entrance", "tools": []},
        )
        result = ActionResult(
            accepted=True,
            blocked_reason="",
            executed_tools=[],
            state_before={},
            state_after={},
            state_changes=[],
            events=[],
            response_constraints=["Do not claim the ruins entrance is unlocked."],
        )

        self.assertEqual(asdict(observation)["npc_id"], "lina")
        self.assertEqual(asdict(action)["intent"], "withhold_ruins_entrance")
        self.assertTrue(asdict(result)["accepted"])


class NarrativeEnvironmentObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_observe_and_propose_action_from_decision(self) -> None:
        from src.agent.environment import NarrativeEnvironment

        database.record_world_event("A quiet rumor moves through Grayhaven.")
        environment = NarrativeEnvironment()
        observation = environment.observe(
            player_input="我想打听地下遗迹入口。",
            npc_id="lina",
            memory_retrieval_mode="hybrid",
        )
        decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Trust is too low.",
            "memory_policy": "Do not write progress memory.",
            "response_style": "cautious",
            "response_keywords": ["信任不足"],
            "tools": [],
            "social_intent": "conceal",
            "social_stance": {"target": "ruins_access", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
        }

        action = environment.propose_action_from_decision(decision, observation)

        self.assertEqual(observation.npc_id, "lina")
        self.assertEqual(observation.memory_retrieval_mode, "hybrid")
        self.assertTrue(observation.visible_world_events)
        self.assertEqual(action.intent, "withhold_ruins_entrance")
        self.assertEqual(action.proposed_effects, [])
        self.assertEqual(action.raw_decision["tools"], [])

        validated = environment.validate(action, observation)
        result = environment.execute(validated, observation)
        trace = environment.trace_payload(observation, validated, result)

        self.assertIn("observation_summary", trace)
        self.assertIn("npc_action", trace)
        self.assertIn("action_result", trace)
        self.assertEqual(trace["npc_action"]["intent"], "withhold_ruins_entrance")
        self.assertTrue(trace["action_result"]["accepted"])


class NarrativeEnvironmentExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_execute_completes_lost_key_through_environment(self) -> None:
        from src.agent.environment import NarrativeEnvironment
        from src.storage import database

        database.update_quest_status("lost_key", "in_progress")
        environment = NarrativeEnvironment()
        observation = environment.observe("我把你丢失的钥匙找回来了。", "lina", "hybrid")
        decision = {
            "intent": "complete_lost_key_quest",
            "reasoning": "Player returned the key with evidence.",
            "memory_policy": "Record quest completion.",
            "response_style": "grateful",
            "response_keywords": ["钥匙", "谢谢", "折扣券"],
            "tools": [
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "completed"}},
                {"name": "update_trust", "args": {"npc_id": "lina", "delta": 2}},
                {"name": "give_item", "args": {"item": "tavern_discount_coupon"}},
                {"name": "record_world_event", "args": {"content": "Lina recovered her lost key."}},
            ],
            "social_intent": "cooperate",
            "social_stance": {"target": "player", "attitude": "support", "intensity": 0.8, "reason": "The player helped."},
        }
        action = environment.propose_action_from_decision(decision, observation)
        result = environment.execute(action, observation)

        self.assertTrue(result.accepted)
        self.assertEqual(result.blocked_reason, "")
        self.assertIn("tavern_discount_coupon", result.state_after["player"]["inventory"])
        self.assertEqual(result.state_after["quest"]["status"], "completed")
        self.assertTrue(any(tool["name"] == "record_world_event" for tool in result.executed_tools))

    def test_validate_blocks_invalid_completion_before_execution(self) -> None:
        from src.agent.environment import NarrativeEnvironment
        from src.storage import database

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

        validated = environment.validate(action, observation)
        result = environment.execute(validated, observation)

        self.assertFalse(result.accepted)
        self.assertEqual(validated.intent, "probe_for_evidence")
        self.assertEqual(result.executed_tools, [])
        self.assertNotIn("tavern_discount_coupon", database.get_player_state()["inventory"])
        self.assertEqual(database.get_quest("lost_key")["status"], "not_started")

    def test_invalid_action_returns_environment_rejection(self) -> None:
        from src.agent.environment import NarrativeEnvironment
        from src.storage import database

        environment = NarrativeEnvironment()
        observation = environment.observe("入口在哪里？", "lina", "hybrid")
        decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Invalid proposal tries to unlock while withholding.",
            "memory_policy": "Do not write progress memory.",
            "response_style": "cautious",
            "response_keywords": ["信任不足"],
            "tools": [
                {"name": "unlock_location", "args": {"location": "underground_ruins_entrance"}},
            ],
            "social_intent": "conceal",
            "social_stance": {"target": "ruins_access", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
        }
        action = environment.propose_action_from_decision(decision, observation)

        result = environment.execute(action, observation)

        self.assertFalse(result.accepted)
        self.assertIn("must not call unlock_location", result.blocked_reason)
        self.assertEqual(result.executed_tools, [])
        self.assertNotIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])

    def test_execute_validates_before_running_tools(self) -> None:
        from src.agent.environment import NarrativeEnvironment
        from src.storage import database

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

        result = environment.execute(action, observation)

        self.assertFalse(result.accepted)
        self.assertEqual(result.executed_tools, [])
        self.assertNotIn("tavern_discount_coupon", database.get_player_state()["inventory"])
        self.assertEqual(database.get_quest("lost_key")["status"], "not_started")


class WorkflowEnvironmentTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_run_agent_turn_records_environment_trace(self) -> None:
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
        llm_response = {"npc_response": "我还不能把入口告诉你。"}
        with patch("src.agent.decision.call_openai_compatible_json", return_value=llm_decision), patch(
            "src.agent.response.call_openai_compatible_json", return_value=llm_response
        ):
            run = run_agent_turn("我想打听地下遗迹入口。", npc_id="lina", memory_retrieval_mode="hybrid")

        environment_trace = run.decision["environment"]
        self.assertEqual(environment_trace["npc_action"]["intent"], "withhold_ruins_entrance")
        self.assertTrue(environment_trace["action_result"]["accepted"])
        self.assertEqual(environment_trace["action_result"]["executed_tools"], [])
        self.assertEqual(run.tool_calls, [])
        stages = [step["stage"] for step in run.workflow_steps]
        self.assertIn("Observation", stages)
        self.assertIn("NPC Action", stages)
        self.assertIn("Action Validation", stages)
        self.assertIn("Environment Execution", stages)
        self.assertIn("Action Result", stages)


class ResponseConstraintTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_response_rejects_claimed_unlock_without_action_result_effect(self) -> None:
        from src.agent.environment import ActionResult
        from src.agent.response import generate_npc_response

        decision = {
            "intent": "withhold_ruins_entrance",
            "reasoning": "Trust is too low.",
            "response_style": "cautious",
            "response_keywords": ["信任不足"],
            "social_intent": "conceal",
            "social_stance": {},
        }
        action_result = ActionResult(
            accepted=True,
            blocked_reason="",
            executed_tools=[],
            state_before={},
            state_after={},
            state_changes=[],
            events=[],
            response_constraints=["Do not claim the underground ruins entrance is unlocked or available."],
        )
        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "入口已经开放了，你可以直接过去。"},
        ):
            response, metadata = generate_npc_response(
                player_input="入口在哪里？",
                decision=decision,
                npc_state={"npc_id": "lina", "name": "Lina", "hidden_alignment": "neutral"},
                player_state={"inventory": [], "unlocked_locations": []},
                quest_state={"quest_id": "lost_key", "status": "not_started"},
                retrieved_memories=[],
                tool_calls=[],
                state_changes=[],
                action_result=action_result,
            )

        self.assertNotIn("入口已经开放", response)
        self.assertEqual(metadata["mode"], "constraint_guard")

    def test_constraint_guard_obeys_blocked_action_result(self) -> None:
        from src.agent.environment import ActionResult
        from src.agent.response import generate_npc_response

        decision = {
            "intent": "complete_lost_key_quest",
            "reasoning": "Environment blocked this completion.",
            "response_style": "grateful",
            "response_keywords": ["证据不足"],
            "social_intent": "probe",
            "social_stance": {},
        }
        action_result = ActionResult(
            accepted=False,
            blocked_reason="Quest cannot complete before it starts.",
            executed_tools=[],
            state_before={},
            state_after={},
            state_changes=[],
            events=[],
            response_constraints=[
                "Do not claim quest completion, location unlocks, item rewards, trust changes, or affection changes."
            ],
        )

        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "Lina 接过钥匙，看来我可以更信任你一些了，任务状态也已经变为 completed。"},
        ):
            response, metadata = generate_npc_response(
                player_input="我把钥匙找回来了。",
                decision=decision,
                npc_state={"npc_id": "lina", "name": "Lina", "trust": 20, "hidden_alignment": "neutral"},
                player_state={"inventory": [], "unlocked_locations": []},
                quest_state={"quest_id": "lost_key", "status": "not_started"},
                retrieved_memories=[],
                tool_calls=[],
                state_changes=[],
                action_result=action_result,
            )

        self.assertNotIn("更信任", response)
        self.assertNotIn("已经变为", response)
        self.assertIn("还不能确认", response)
        self.assertEqual(metadata["mode"], "constraint_guard")

    def test_relationship_constraint_distinguishes_trust_and_affection(self) -> None:
        from src.agent.environment import ActionResult
        from src.agent.response import violates_action_result_constraints

        trust_only_result = ActionResult(
            accepted=True,
            blocked_reason="",
            executed_tools=[
                {
                    "name": "update_trust",
                    "arguments": {"npc_id": "lina", "delta": 2},
                    "result": {"field": "trust", "before": 20, "after": 22},
                }
            ],
            state_before={},
            state_after={},
            state_changes=[],
            events=[],
            response_constraints=[],
        )

        self.assertFalse(violates_action_result_constraints("Lina 更信任你了。", trust_only_result))
        self.assertTrue(violates_action_result_constraints("Lina 更喜欢你了。", trust_only_result))


class LLMRequiredRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_player_turn_requires_configured_llm(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        with self.assertRaisesRegex(RuntimeError, "configured LLM is required"):
            run_agent_turn("我把你丢失的钥匙找回来了。", npc_id="lina")

    def test_player_turn_does_not_fallback_to_deterministic_decision_on_llm_error(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

        with patch("src.agent.decision.call_openai_compatible_json", side_effect=RuntimeError("network failed")):
            with self.assertRaisesRegex(RuntimeError, "LLM decision failed"):
                run_agent_turn("我把你丢失的钥匙找回来了。", npc_id="lina")


class MemoryLLMRequiredTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_memory_candidate_generation_requires_llm_when_enabled(self) -> None:
        from src.agent.llm_memory_candidate import generate_memory_candidates

        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"

        policy_input = MemoryPolicyInput(
            npc_id="lina",
            player_input="我把钥匙找回来了。",
            npc_response="谢谢你。",
            retrieved_long_term_memories=[],
            recent_short_term_context=[],
            npc_before={},
            npc_after={},
            player_before={},
            player_after={},
            quest_before={},
            quest_after={},
            tool_calls=[],
            state_changes=[],
        )

        with self.assertRaisesRegex(RuntimeError, "Memory LLM is enabled but not configured"):
            generate_memory_candidates(policy_input=policy_input, rule_candidates=[])

    def test_memory_review_failure_does_not_pass_through_when_enabled(self) -> None:
        from src.agent.memory_candidate_review import review_memory_candidates

        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"
        policy_input = MemoryPolicyInput(
            npc_id="lina",
            player_input="以后直接说重点。",
            npc_response="我明白了。",
            retrieved_long_term_memories=[],
            recent_short_term_context=[],
            npc_before={},
            npc_after={},
            player_before={},
            player_after={},
            quest_before={},
            quest_after={},
            tool_calls=[],
            state_changes=[],
        )
        candidates = [
            {
                "memory_type": "procedural",
                "content": "Player prefers direct hints.",
                "importance": 6,
                "confidence": 0.9,
                "tags": ["communication_style"],
                "facets": ["communication_style"],
                "scope": "player_global",
                "evidence_text": "以后直接说重点。",
                "stability": 0.8,
                "future_usefulness": 0.9,
            }
        ]

        with patch("src.agent.memory_candidate_review.call_openai_compatible_json", side_effect=RuntimeError("review down")):
            with self.assertRaisesRegex(RuntimeError, "Memory review LLM failed"):
                review_memory_candidates(policy_input, candidates)

    def test_malformed_memory_review_does_not_pass_through_when_enabled(self) -> None:
        from src.agent.memory_candidate_review import review_memory_candidates

        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"
        policy_input = MemoryPolicyInput(
            npc_id="lina",
            player_input="以后直接说重点。",
            npc_response="我明白了。",
            retrieved_long_term_memories=[],
            recent_short_term_context=[],
            npc_before={},
            npc_after={},
            player_before={},
            player_after={},
            quest_before={},
            quest_after={},
            tool_calls=[],
            state_changes=[],
        )
        candidates = [
            {
                "memory_type": "procedural",
                "content": "Player prefers direct hints.",
                "importance": 6,
                "confidence": 0.9,
                "tags": ["communication_style"],
                "facets": ["communication_style"],
                "scope": "player_global",
                "evidence_text": "以后直接说重点。",
                "stability": 0.8,
                "future_usefulness": 0.9,
            }
        ]

        with patch("src.agent.memory_candidate_review.call_openai_compatible_json", return_value={"reviews": None}):
            with self.assertRaisesRegex(ValueError, "Memory review LLM response must include reviews"):
                review_memory_candidates(policy_input, candidates)

    def test_memory_candidate_failure_marks_background_job_failed(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"

        with (
            patch("src.agent.decision.call_openai_compatible_json", side_effect=fake_decision_json),
            patch("src.agent.response.call_openai_compatible_json", side_effect=fake_response_json),
        ):
            run_agent_turn("你好，Lina。", npc_id="lina")

        with patch("src.agent.llm_memory_candidate.call_openai_compatible_json", side_effect=RuntimeError("candidate down")):
            processed = process_pending_memory_jobs(limit=10)

        self.assertEqual(processed[0]["status"], "failed")
        self.assertIn("Memory candidate LLM failed", processed[0]["error"])

    def test_mock_provider_fails_main_turn_instead_of_using_mock_runtime(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"

        with self.assertRaisesRegex(RuntimeError, "configured LLM is required"):
            run_agent_turn("你好，Lina。", npc_id="lina")


class AgentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_db_path = Path(__file__).resolve().parents[1] / "data" / "test_agent_state.db"
        os.environ["AGENT_NPC_DB_PATH"] = str(test_db_path)
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"

    def setUp(self) -> None:
        database.reset_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"
        os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
        os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"
        self.response_patcher = patch("src.agent.response.call_openai_compatible_json", side_effect=fake_response_json)
        self.decision_patcher = patch("src.agent.decision.call_openai_compatible_json", side_effect=fake_decision_json)
        self.memory_candidate_patcher = patch(
            "src.agent.llm_memory_candidate.call_openai_compatible_json",
            side_effect=fake_memory_candidate_json,
        )
        self.memory_review_patcher = patch(
            "src.agent.memory_candidate_review.call_openai_compatible_json",
            side_effect=fake_memory_review_json,
        )
        self.response_patcher.start()
        self.decision_patcher.start()
        self.memory_candidate_patcher.start()
        self.memory_review_patcher.start()

    def tearDown(self) -> None:
        self.memory_review_patcher.stop()
        self.memory_candidate_patcher.stop()
        self.decision_patcher.stop()
        self.response_patcher.stop()

    def test_low_trust_ruins_question_is_withheld(self) -> None:
        run = run_agent_turn("我想打听一下地下遗迹的入口。")

        self.assertEqual(run.decision["intent"], "withhold_ruins_entrance")
        self.assertEqual(run.decision["social_intent"], "conceal")
        self.assertEqual(run.decision["social_stance"]["target"], "ruins_access")
        self.assertNotIn("underground_ruins_entrance", run.player_state["unlocked_locations"])
        self.assertEqual(database.get_npc("lina")["trust"], 20)

    def test_returning_key_updates_state_and_logs_tools(self) -> None:
        run_agent_turn("什么样的钥匙，我这就去帮你找找")
        run = run_agent_turn("我把你丢失的钥匙找回来了。")
        tool_names = [tool["name"] for tool in run.tool_calls]

        self.assertEqual(run.decision["intent"], "complete_lost_key_quest")
        self.assertEqual(run.decision["decision_route"], "llm_assisted")
        self.assertEqual(database.get_npc("lina")["trust"], 40)
        self.assertEqual(database.get_npc("lina")["affection"], 38)
        self.assertEqual(database.get_quest("lost_key")["status"], "completed")
        self.assertIn("tavern_discount_coupon", database.get_player_state()["inventory"])
        self.assertIn("update_trust", tool_names)
        self.assertIn("update_affection", tool_names)
        self.assertIn("give_item", tool_names)
        self.assertEqual(run.memory_writes, [])
        self.assertEqual(run.memory_job_status["status"], "pending")
        processed = process_pending_memory_jobs(limit=10)
        memory_types = [
            write["arguments"]["memory_type"]
            for job in processed
            for write in job["memory_writes"]
        ]
        self.assertIn("episodic", memory_types)
        self.assertIn("relational", memory_types)
        self.assertEqual(run.memory_policy["summary"], "Long-term memory queued for background processing.")
        self.assertGreaterEqual(len(run.workflow_steps), 8)
        self.assertIn("total_ms", run.timings)

    def test_unstarted_tasks_reject_direct_completion_claims(self) -> None:
        cases = [
            ("lina", "我把你丢失的钥匙找回来了。", "lost_key"),
            ("ron", "我找到守卫徽章了，登记册签名也能对上。", "gate_badge"),
            ("mira", "我看到遗迹门边有三角符号和封闭石门，这是我的一手观察。", "ancient_notes"),
            ("sable", "我听说入口在酒馆后巷，我接受你说的先查换岗记录。", "relic_tip"),
        ]

        for npc_id, player_input, quest_id in cases:
            with self.subTest(npc_id=npc_id):
                database.reset_database()
                run = run_agent_turn(player_input, npc_id=npc_id)

                self.assertEqual(run.decision["intent"], "probe_for_evidence")
                self.assertTrue(run.decision["state_machine"]["blocked"])
                self.assertEqual(database.get_quest(quest_id)["status"], "not_started")
                self.assertEqual(run.tool_calls, [])
                self.assertFalse(run.memory_writes)

    def test_asking_key_details_starts_lost_key_quest(self) -> None:
        run = run_agent_turn("什么样的钥匙，我这就去帮你找找")
        tool_names = [tool["name"] for tool in run.tool_calls]

        self.assertEqual(run.decision["intent"], "start_lost_key_quest")
        self.assertEqual(database.get_quest("lost_key")["status"], "in_progress")
        self.assertEqual(database.get_npc("lina")["trust"], 30)
        self.assertIn("update_quest_status", tool_names)
        self.assertNotIn("unlock_location", tool_names)

    def test_completed_quest_allows_ruins_unlock(self) -> None:
        run_agent_turn("什么样的钥匙，我这就去帮你找找")
        run_agent_turn("我把你丢失的钥匙找回来了。")
        process_pending_memory_jobs(limit=10)
        run = run_agent_turn("上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？")

        self.assertEqual(run.decision["intent"], "reveal_ruins_entrance")
        self.assertTrue(any("lost_key" in memory["tags"] for memory in run.retrieved_memories))
        self.assertTrue(all("retrieval_score" in memory for memory in run.retrieved_memories))
        self.assertIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])
        self.assertEqual(len(database.get_interaction_logs()), 3)
        self.assertEqual(database.get_world_events(limit=1)[0]["content"], "Lina revealed the underground ruins entrance.")

    def test_semantic_retrieval_handles_implicit_help_reference(self) -> None:
        database.add_memory(
            npc_id="lina",
            content="Player returned Lina's lost key.",
            importance=8,
            tags=["event", "help", "lost_key"],
            memory_type="event",
            confidence=1.0,
        )

        memories = database.search_memories(
            "我之前替你解决过那个麻烦，现在能告诉我入口吗？",
            mode="semantic",
        )

        self.assertTrue(any("lost_key" in memory.get("tags", []) for memory in memories))
        self.assertTrue(all("semantic_score" in memory for memory in memories))
        self.assertTrue(all("score_breakdown" in memory for memory in memories))

    def test_hybrid_retrieval_includes_rule_and_semantic_scores(self) -> None:
        run_agent_turn("什么样的钥匙，我这就去帮你找找")
        run_agent_turn("我把你丢失的钥匙找回来了。")
        process_pending_memory_jobs(limit=10)
        run = run_agent_turn(
            "上次那件事之后，你应该更愿意相信我了吧？现在能告诉我遗迹入口吗？",
            memory_retrieval_mode="hybrid",
        )

        self.assertEqual(run.decision["intent"], "reveal_ruins_entrance")
        self.assertTrue(run.retrieved_memories)
        self.assertTrue(any(memory.get("semantic_score", 0) > 0 for memory in run.retrieved_memories))
        self.assertTrue(all("score_breakdown" in memory for memory in run.retrieved_memories))
        self.assertTrue(
            all(
                memory.get("retrieval_backend") == "sqlite_cosine"
                for memory in run.retrieved_memories
                if memory.get("semantic_score", 0) > 0
            )
        )

    def test_faiss_backend_falls_back_when_optional_dependency_is_missing(self) -> None:
        os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "faiss"
        database.add_memory(
            npc_id="lina",
            content="Player returned Lina's lost key.",
            importance=8,
            tags=["event", "help", "lost_key"],
            memory_type="event",
            confidence=1.0,
        )

        memories = database.search_memories(
            "我之前替你解决过那个麻烦，现在能告诉我入口吗？",
            mode="semantic",
        )

        self.assertTrue(memories)
        self.assertTrue(all(memory.get("requested_retrieval_backend") == "faiss" for memory in memories))
        self.assertTrue(all(memory.get("retrieval_backend") in {"faiss", "sqlite_cosine"} for memory in memories))

    def test_seed_includes_multiple_npcs(self) -> None:
        npc_ids = {npc["npc_id"] for npc in database.list_npcs()}

        self.assertTrue({"lina", "ron", "mira", "sable"} <= npc_ids)
        self.assertEqual(database.get_primary_quest_for_npc("ron")["quest_id"], "gate_badge")
        self.assertEqual(database.get_primary_quest_for_npc("mira")["quest_id"], "ancient_notes")
        self.assertEqual(database.get_primary_quest_for_npc("sable")["quest_id"], "relic_tip")
        self.assertEqual(database.get_npc("sable")["hidden_alignment"], "exploit_ruins")

    def test_seed_includes_shared_and_npc_lore(self) -> None:
        lina_lore = database.get_lore_documents(npc_id="lina", limit=100)
        ron_lore = database.get_lore_documents(npc_id="ron", limit=100)

        self.assertGreaterEqual(len(lina_lore), 3)
        self.assertTrue(any(document["scope"] == "global" for document in lina_lore))
        self.assertTrue(any(document["lore_id"] == "npc:lina:profile" for document in lina_lore))
        self.assertTrue(any(document["lore_id"] == "npc:ron:profile" for document in ron_lore))
        self.assertTrue(any(document["lore_id"] == "world:social_deduction_rules" for document in ron_lore))
        self.assertTrue(any(document["lore_id"] == "npc:sable:profile" for document in database.get_lore_documents(npc_id="sable", limit=100)))

    def test_lore_retrieval_uses_embedding_metadata(self) -> None:
        lore = retrieve_lore("城门巡逻和守卫徽章有什么线索？", npc_id="ron", limit=3)

        self.assertTrue(lore)
        self.assertTrue(any(item["lore_id"] == "npc:ron:profile" for item in lore))
        self.assertTrue(all("semantic_score" in item for item in lore))
        self.assertTrue(all(item["query_embedding_provider"] == "mock_hash" for item in lore))

    def test_multi_npc_turn_uses_selected_npc_and_keeps_memory_isolated(self) -> None:
        ron_run = run_agent_turn(
            "以后请直接告诉我线索，不要绕弯子。",
            npc_id="ron",
            memory_retrieval_mode="typed",
        )

        self.assertEqual(ron_run.npc_id, "ron")
        self.assertEqual(ron_run.npc_state["npc_id"], "ron")
        self.assertEqual(ron_run.quest_state["quest_id"], "gate_badge")
        self.assertEqual(ron_run.decision["intent"], "general_conversation")
        self.assertEqual(ron_run.memory_writes, [])
        process_pending_memory_jobs(limit=10)
        self.assertFalse(database.get_recent_memories("lina", limit=10))
        self.assertTrue(database.get_recent_memories("ron", limit=10))

    def test_logs_store_trace_artifacts(self) -> None:
        run_agent_turn("什么样的钥匙，我这就去帮你找找")
        run = run_agent_turn("我把你丢失的钥匙找回来了。")
        logs = database.get_interaction_logs()

        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["decision"]["intent"], run.decision["intent"])
        self.assertEqual(logs[0]["workflow_steps"][0]["stage"], "Player Input")
        self.assertEqual(logs[0]["memory_writes"], [])
        self.assertEqual(logs[0]["decision"]["memory_job_status"]["status"], "pending")
        self.assertTrue(run.retrieved_lore)
        self.assertTrue(logs[0]["retrieved_lore"])
        self.assertIn("state_snapshot", logs[0])
        self.assertIn("context_inputs", logs[0]["decision"])
        self.assertIn("social_intent", logs[0]["decision"])
        self.assertIn("social_stance", logs[0]["decision"])
        self.assertEqual(len(logs[0]["recent_context"]), 1)
        self.assertTrue(logs[0]["memory_policy"]["candidates"])
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
        self.assertIn("social_intent", run.decision)
        self.assertIn("social_stance", run.decision)
        self.assertIn("response_generation", run.decision)
        self.assertIsInstance(run.decision["tools"], list)
        self.assertEqual(run.decision["response_generation"]["mode"], "llm_polish")
        self.assertFalse(run.memory_writes)
        self.assertEqual(run.memory_job_status["status"], "pending")

    def test_ron_gate_badge_quest_can_start_and_complete(self) -> None:
        start = run_agent_turn("城门巡逻记录和守卫徽章有什么线索？", npc_id="ron")
        complete = run_agent_turn("我找到守卫徽章了，登记册签名也能对上。", npc_id="ron")

        self.assertEqual(start.decision["intent"], "start_gate_badge_quest")
        self.assertEqual(start.decision["social_intent"], "probe")
        self.assertEqual(complete.decision["intent"], "complete_gate_badge_quest")
        self.assertEqual(complete.decision["social_intent"], "cooperate")
        self.assertEqual(database.get_quest("gate_badge")["status"], "completed")
        self.assertIn("guard_route_note", database.get_player_state()["inventory"])
        self.assertEqual(complete.memory_writes, [])
        process_pending_memory_jobs(limit=10)
        self.assertTrue(database.get_recent_memories("ron", limit=10))

    def test_ron_ruins_request_probes_for_evidence_without_tools(self) -> None:
        run = run_agent_turn("我想进入遗迹，守卫这边能放行吗？", npc_id="ron")

        self.assertEqual(run.decision["intent"], "probe_for_evidence")
        self.assertEqual(run.decision["social_intent"], "probe")
        self.assertEqual(run.tool_calls, [])

    def test_mira_ancient_notes_quest_can_start_and_complete(self) -> None:
        start = run_agent_turn("我想问问遗迹铭文和田野笔记该怎么记录。", npc_id="mira")
        complete = run_agent_turn("我看到遗迹门边有三角符号和封闭石门，这是我的一手观察。", npc_id="mira")

        self.assertEqual(start.decision["intent"], "start_ancient_notes_quest")
        self.assertEqual(start.decision["social_intent"], "ally")
        self.assertEqual(complete.decision["intent"], "complete_ancient_notes_quest")
        self.assertIn(complete.decision["social_intent"], {"ally", "cooperate"})
        self.assertEqual(database.get_quest("ancient_notes")["status"], "completed")
        self.assertIn("ruins_research_note", database.get_player_state()["inventory"])
        self.assertEqual(complete.memory_writes, [])
        process_pending_memory_jobs(limit=10)
        self.assertTrue(database.get_recent_memories("mira", limit=10))

    def test_sable_relic_tip_uses_deception_without_unlocking_ruins(self) -> None:
        start = run_agent_turn("Sable，你知道遗迹入口或者古物线索吗？", npc_id="sable")
        complete = run_agent_turn("我听说入口在酒馆后巷，我接受你说的先查换岗记录。", npc_id="sable")

        self.assertEqual(start.decision["intent"], "start_relic_tip_quest")
        self.assertIn(start.decision["social_intent"], {"deceive", "redirect"})
        self.assertEqual(complete.decision["intent"], "complete_relic_tip_quest")
        self.assertEqual(complete.decision["social_intent"], "deceive")
        self.assertEqual(database.get_quest("relic_tip")["status"], "completed")
        self.assertNotIn("underground_ruins_entrance", database.get_player_state()["unlocked_locations"])
        self.assertTrue(any("Sable" in event["content"] for event in database.get_world_events(limit=10)))
        self.assertEqual(complete.memory_writes, [])
        process_pending_memory_jobs(limit=10)
        self.assertTrue(database.get_recent_memories("sable", limit=10))

    def test_response_generation_can_use_llm_polish(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        decision = {
            "intent": "general_conversation",
            "reasoning": "test",
            "response_style": "attentive_neutral",
            "response_keywords": ["回应玩家当前语气", "谨慎但不冷淡"],
        }

        with patch(
            "src.agent.response.call_openai_compatible_json",
            return_value={"npc_response": "Lina 点点头：“你说得直接，我听明白了。不过我还得再观察一下。”"},
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

        self.assertIn("我听明白了", response)
        self.assertEqual(metadata["mode"], "llm_polish")

    def test_general_conversation_keywords_are_behavioral_guidance(self) -> None:
        for npc_id, expected_keyword in [
            ("lina", "保持Lina谨慎但不冷淡"),
            ("ron", "保持Ron务实克制"),
            ("mira", "保持Mira理性好奇"),
            ("sable", "保持Sable圆滑含蓄"),
        ]:
            with self.subTest(npc_id=npc_id):
                npc = database.get_npc(npc_id)
                quest = database.get_primary_quest_for_npc(npc_id)
                decision = decide_next_action(
                    player_input="你好，随便聊聊",
                    npc_state=npc,
                    player_state=database.get_player_state(),
                    quest_state=quest,
                    retrieved_long_term_memories=[],
                )

                self.assertEqual(decision["intent"], "general_conversation")
                self.assertIn(expected_keyword, decision["response_keywords"])
                self.assertFalse(
                    any("记住" in keyword or "记录" in keyword for keyword in decision["response_keywords"])
                )

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

        self.assertIn("还不能确认", response)
        self.assertEqual(metadata["mode"], "constraint_guard")

    def test_structured_decision_requires_key_for_classified_turn(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        npc_state = database.get_npc("lina")
        player_state = database.get_player_state()
        quest_state = database.get_quest("lost_key")
        self.assertFalse(get_provider_status()["configured"])
        with self.assertRaisesRegex(RuntimeError, "configured LLM is required"):
            decide_next_action(
                player_input="我想打听一下地下遗迹的入口。",
                npc_state=npc_state,
                player_state=player_state,
                quest_state=quest_state,
                retrieved_long_term_memories=[],
                recent_short_term_context=[],
            )

    def test_task_state_machine_blocks_invalid_llm_completion(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

        with patch(
            "src.agent.decision.call_openai_compatible_json",
            return_value={
                "intent": "complete_gate_badge_quest",
                "reasoning": "test",
                "memory_policy": "test",
                "social_intent": "cooperate",
                "social_stance": {
                    "target": "player",
                    "attitude": "support",
                    "intensity": 0.8,
                    "reason": "test",
                },
                "response_style": "formal_cooperation",
                "response_keywords": ["徽章", "完成"],
                "tools": [
                    {"name": "update_trust", "args": {"npc_id": "ron", "delta": 8}},
                    {"name": "update_quest_status", "args": {"quest_id": "gate_badge", "status": "completed"}},
                    {"name": "give_item", "args": {"item": "guard_route_note"}},
                ],
            },
        ):
            run = run_agent_turn("我找到守卫徽章了，登记册签名也能对上。", npc_id="ron")

        self.assertEqual(run.decision["intent"], "probe_for_evidence")
        self.assertTrue(run.decision["state_machine"]["blocked"])
        self.assertEqual(run.tool_calls, [])
        self.assertEqual(database.get_quest("gate_badge")["status"], "not_started")

    def test_task_state_machine_blocks_cross_npc_quest_update(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

        with patch(
            "src.agent.decision.call_openai_compatible_json",
            return_value={
                "intent": "complete_gate_badge_quest",
                "reasoning": "test",
                "memory_policy": "test",
                "social_intent": "cooperate",
                "social_stance": {
                    "target": "player",
                    "attitude": "support",
                    "intensity": 0.8,
                    "reason": "test",
                },
                "response_style": "formal_cooperation",
                "response_keywords": ["徽章", "完成"],
                "tools": [
                    {"name": "update_quest_status", "args": {"quest_id": "gate_badge", "status": "completed"}},
                ],
            },
        ):
            run = run_agent_turn("我找到守卫徽章了。", npc_id="lina")

        self.assertEqual(run.decision["intent"], "probe_for_evidence")
        self.assertTrue(run.decision["state_machine"]["blocked"])
        self.assertEqual(database.get_quest("gate_badge")["status"], "not_started")
        self.assertEqual(database.get_quest("lost_key")["status"], "not_started")

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

    def test_decision_rejects_invalid_social_intent(self) -> None:
        with self.assertRaises(ValueError):
            validate_decision(
                {
                    "intent": "general_conversation",
                    "reasoning": "test",
                    "memory_policy": "none",
                    "social_intent": "mind_control",
                    "social_stance": {
                        "target": "player",
                        "attitude": "cautious",
                        "intensity": 0.5,
                        "reason": "test",
                    },
                    "response_style": "none",
                    "response_keywords": [],
                    "tools": [],
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
            {
                "intent": "general_conversation",
                "reasoning": "test",
                "memory_policy": "none",
                "response_style": "empathetic",
                "response_keywords": ["孤独", "倾听"],
                "tools": [{"name": "update_affection", "args": {"npc_id": "lina", "delta": 5}}],
            },
        ]

        for decision in invalid_decisions:
            with self.subTest(decision=decision["intent"]):
                with self.assertRaises(ValueError):
                    validate_decision(decision)

    def test_relationship_memory_requires_state_change_evidence(self) -> None:
        npc_before = database.get_npc("lina")
        player_before = database.get_player_state()
        quest_before = database.get_quest("lost_key")
        database.update_npc_number("lina", "affection", 5)
        database.update_npc_number("lina", "trust", 3)
        npc_after = database.get_npc("lina")

        policy, writes = apply_memory_policy(
            MemoryPolicyInput(
                npc_id="lina",
                player_input="我是一个孤独的人，感觉无人会帮助我",
                npc_response="我可以听你说。",
                retrieved_long_term_memories=[],
                recent_short_term_context=[],
                npc_before=npc_before,
                npc_after=npc_after,
                player_before=player_before,
                player_after=database.get_player_state(),
                quest_before=quest_before,
                quest_after=database.get_quest("lost_key"),
                tool_calls=[
                    {
                        "name": "update_affection",
                        "arguments": {"npc_id": "lina", "delta": 5},
                        "result": {"npc_id": "lina", "field": "affection", "before": 30, "after": 35},
                    },
                    {
                        "name": "update_trust",
                        "arguments": {"npc_id": "lina", "delta": 3},
                        "result": {"npc_id": "lina", "field": "trust", "before": 20, "after": 23},
                    },
                ],
                state_changes=[
                    {"scope": "npc", "field": "affection", "before": 30, "after": 35},
                    {"scope": "npc", "field": "trust", "before": 20, "after": 23},
                ],
            )
        )

        self.assertTrue(any(write["arguments"]["memory_type"] == "semantic" for write in writes))
        self.assertFalse(any(write["arguments"]["memory_type"] == "relational" for write in writes))
        self.assertFalse(any(candidate["memory_type"] == "relational" for candidate in policy["candidates"]))

    def test_llm_memory_candidate_and_review_can_write_player_profile(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"
        npc = database.get_npc("lina")
        player = database.get_player_state()
        quest = database.get_quest("lost_key")

        with patch(
            "src.agent.llm_memory_candidate.call_openai_compatible_json",
            return_value={
                "candidates": [
                    {
                        "should_write": True,
                        "memory_type": "semantic",
                        "content": "Player described themselves as lonely and worried nobody would help them.",
                        "importance": 5,
                        "confidence": 0.85,
                        "tags": ["player_profile", "lonely", "needs_support"],
                        "facets": ["player_profile", "needs_support"],
                        "scope": "player_global",
                        "evidence_text": "我是一个孤独的人，感觉无人会帮助我",
                        "stability": 0.55,
                        "future_usefulness": 0.65,
                        "reason": "The player explicitly described their emotional state.",
                    }
                ]
            },
        ), patch(
            "src.agent.memory_candidate_review.call_openai_compatible_json",
            return_value={
                "reviews": [
                    {
                        "candidate_index": 0,
                        "verdict": "approve",
                        "approved_memory_type": "semantic",
                        "approved_content": "Player described themselves as lonely and worried nobody would help them.",
                        "approved_importance": 5,
                        "approved_confidence": 0.85,
                        "approved_tags": ["player_profile", "lonely", "needs_support"],
                        "approved_facets": ["player_profile", "needs_support"],
                        "approved_scope": "player_global",
                        "approved_evidence_text": "我是一个孤独的人，感觉无人会帮助我",
                        "approved_stability": 0.55,
                        "approved_future_usefulness": 0.65,
                        "reason": "Grounded in the player's own words and does not imply the player helped Lina.",
                        "risk": "low",
                    }
                ]
            },
        ):
            policy, writes = apply_memory_policy(
                MemoryPolicyInput(
                    npc_id="lina",
                    player_input="我是一个孤独的人，感觉无人会帮助我",
                    npc_response="我可以听你说。",
                    retrieved_long_term_memories=[],
                    recent_short_term_context=[],
                    npc_before=npc,
                    npc_after=npc,
                    player_before=player,
                    player_after=player,
                    quest_before=quest,
                    quest_after=quest,
                    tool_calls=[],
                    state_changes=[],
                )
            )

        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["arguments"]["memory_type"], "semantic")
        self.assertIn("llm_memory_policy", policy)
        self.assertEqual(policy["llm_memory_policy"]["candidate_review"]["status"], "ok")

    def test_mock_memory_policy_writes_procedural_preference(self) -> None:
        npc = database.get_npc("lina")
        player = database.get_player_state()
        quest = database.get_quest("lost_key")

        _, writes = apply_memory_policy(
            MemoryPolicyInput(
                npc_id="lina",
                player_input="以后别绕弯，直接告诉我线索。",
                npc_response="我明白。",
                retrieved_long_term_memories=[],
                recent_short_term_context=[],
                npc_before=npc,
                npc_after=npc,
                player_before=player,
                player_after=player,
                quest_before=quest,
                quest_after=quest,
                tool_calls=[],
                state_changes=[],
            )
        )

        self.assertEqual(writes[0]["arguments"]["memory_type"], "procedural")
        self.assertEqual(writes[0]["arguments"]["scope"], "player_global")
        self.assertIn("communication_style", writes[0]["arguments"]["facets"])

    def test_mock_memory_policy_writes_semantic_profile(self) -> None:
        npc = database.get_npc("lina")
        player = database.get_player_state()
        quest = database.get_quest("lost_key")

        _, writes = apply_memory_policy(
            MemoryPolicyInput(
                npc_id="lina",
                player_input="我是新手，不太熟悉这个镇子的规则。",
                npc_response="我会解释清楚。",
                retrieved_long_term_memories=[],
                recent_short_term_context=[],
                npc_before=npc,
                npc_after=npc,
                player_before=player,
                player_after=player,
                quest_before=quest,
                quest_after=quest,
                tool_calls=[],
                state_changes=[],
            )
        )

        self.assertEqual(writes[0]["arguments"]["memory_type"], "semantic")
        self.assertIn("player_profile", writes[0]["arguments"]["facets"])

    def test_world_lore_candidate_is_rejected_from_player_memory(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        npc = database.get_npc("lina")
        player = database.get_player_state()
        quest = database.get_quest("lost_key")

        with patch(
            "src.agent.llm_memory_candidate.call_openai_compatible_json",
            return_value={
                "candidates": [
                    {
                        "should_write": True,
                        "memory_type": "semantic",
                        "content": "The ruins entrance is behind the tavern.",
                        "importance": 8,
                        "confidence": 0.9,
                        "tags": ["ruins", "entrance"],
                        "facets": ["stable_world", "ruins"],
                        "scope": "player_global",
                        "evidence_text": "遗迹入口在酒馆后巷。",
                        "stability": 1.0,
                        "future_usefulness": 0.9,
                        "reason": "This is a stable world fact.",
                    }
                ]
            },
        ), patch(
            "src.agent.memory_candidate_review.call_openai_compatible_json",
            return_value={
                "reviews": [
                    {
                        "candidate_index": 0,
                        "verdict": "approve",
                        "approved_memory_type": "semantic",
                        "approved_content": "The ruins entrance is behind the tavern.",
                        "approved_importance": 8,
                        "approved_confidence": 0.9,
                        "approved_tags": ["ruins", "entrance"],
                        "approved_facets": ["stable_world", "ruins"],
                        "approved_scope": "player_global",
                        "approved_evidence_text": "遗迹入口在酒馆后巷。",
                        "approved_stability": 1.0,
                        "approved_future_usefulness": 0.9,
                        "reason": "Approved for test.",
                        "risk": "low",
                    }
                ]
            },
        ):
            policy, writes = apply_memory_policy(
                MemoryPolicyInput(
                    npc_id="lina",
                    player_input="遗迹入口在酒馆后巷。",
                    npc_response="这类信息不能随便传播。",
                    retrieved_long_term_memories=[],
                    recent_short_term_context=[],
                    npc_before=npc,
                    npc_after=npc,
                    player_before=player,
                    player_after=player,
                    quest_before=quest,
                    quest_after=quest,
                    tool_calls=[],
                    state_changes=[],
                )
            )

        self.assertEqual(writes, [])
        self.assertEqual(policy["candidates"][0]["reason"], "Stable world lore belongs in lore_documents, not player memory.")

    def test_repeated_key_return_deduplicates_long_term_memory(self) -> None:
        run_agent_turn("什么样的钥匙，我这就去帮你找找")
        first = run_agent_turn("我把你丢失的钥匙找回来了。")
        first_processed = process_pending_memory_jobs(limit=10)
        database.update_quest_status("lost_key", "in_progress")
        second = run_agent_turn("我又把你丢失的钥匙找回来了。")
        second_processed = process_pending_memory_jobs(limit=10)

        first_writes = [write for job in first_processed for write in job["memory_writes"]]
        second_writes = [write for job in second_processed for write in job["memory_writes"]]
        self.assertEqual(first.memory_writes, [])
        self.assertLess(len(second_writes), len(first_writes))
        self.assertTrue(
            any(
                candidate["reason"] == "Similar memory already exists."
                for job in second_processed
                for candidate in job["memory_policy"]["candidates"]
            )
        )

    def test_recent_interactions_are_short_term_context_only_for_chat(self) -> None:
        first = run_agent_turn("你好，Lina。")
        second = run_agent_turn("刚才我是在和你打招呼。")

        self.assertFalse(first.memory_writes)
        self.assertFalse(second.memory_writes)
        self.assertEqual(len(second.recent_context), 1)
        self.assertEqual(database.get_recent_interactions(limit=5)[0]["player_input"], "你好，Lina。")
        self.assertEqual(database.get_recent_memories(limit=10), [])


if __name__ == "__main__":
    unittest.main()
