# Environment Refactor With LLM-Required Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the turn workflow so `NarrativeEnvironment` owns observation, validation, execution, and action results, while all runtime model paths use the configured LLM path instead of deterministic model substitutes.

**Architecture:** `src/agent/environment.py` introduces `Observation`, `NPCAction`, `ActionResult`, and `NarrativeEnvironment`. `src/agent/workflow.py` delegates context loading and tool execution to the environment, then response generation receives `Observation + NPCAction + ActionResult` so dialogue cannot claim effects the environment did not execute. Program rule gates such as turn classification and the task state machine remain deterministic validators; they are not treated as model substitutes.

**Tech Stack:** Python dataclasses, FastAPI response serialization through `dataclasses.asdict`, SQLite state tools in `src/tools/sqlite_tools.py`, existing `unittest` suite, React/Vite frontend trace display.

---

## Non-Negotiable Runtime Rule

All places that choose between a deterministic model substitute and an LLM path must use the LLM path in player-facing/runtime behavior.

Allowed deterministic code:

- `classify_turn(...)` as a local routing and rule gate.
- `apply_task_state_machine(...)`, `validate_decision(...)`, `validate_tool_call(...)`, and business-rule validators.
- Unit tests may patch `call_openai_compatible_json` with `unittest.mock` so tests do not hit the network, but the configured provider in those tests must still be `openai_compatible`.

Disallowed runtime behavior after this plan:

- Falling back from a failed LLM decision to `mock_decide_next_action(...)`.
- Falling back from response LLM failure to normal player-facing template text without marking the response as blocked/error-constrained.
- Using mock memory candidate generation when memory LLM is enabled for runtime.
- Setting test/runtime defaults to `AGENT_NPC_LLM_PROVIDER=mock` for the main turn workflow.

## File Structure

- Create `src/agent/environment.py`: environment dataclasses, action adaptation, validation delegation, tool execution, action result construction, response constraints.
- Modify `src/agent/workflow.py`: replace direct `build_context_inputs(...)` and `execute_tools(decision)` ownership with `NarrativeEnvironment`, attach environment trace, update workflow steps.
- Modify `src/agent/response.py`: accept optional `observation`, `npc_action`, and `action_result`; send response constraints to LLM; enforce deterministic guard checks on generated text.
- Modify `src/agent/decision.py`: keep rule classification and task-state-machine gates; remove player-runtime fallback from LLM failure to deterministic model decisions for ambiguous/social turns.
- Modify `src/agent/llm_memory_candidate.py` and `src/agent/memory_candidate_review.py`: make runtime memory candidate/review paths require configured LLM when enabled.
- Modify `src/api/server.py`: keep `/api/turn` output stable while exposing `run.decision.environment`.
- Modify `tests/test_workflow.py`: add environment tests and update LLM-required tests to patch LLM calls under `openai_compatible`.
- Modify `tests/test_api.py`: assert API exposes environment trace.
- Modify `docs/design/llm_integration.md`: update docs from optional mock-first language to LLM-required runtime language.

---

### Task 1: Add Environment Data Model Tests

**Files:**
- Test: `tests/test_workflow.py`
- Create: `src/agent/environment.py`

- [ ] **Step 1: Add failing dataclass shape test**

Add this test class near the existing workflow tests:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.EnvironmentDataModelTest -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.agent.environment'`.

- [ ] **Step 3: Add dataclasses**

Create `src/agent/environment.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Observation:
    npc_id: str
    player_input: str
    npc_state: dict[str, Any]
    player_state: dict[str, Any]
    quest_state: dict[str, Any]
    recent_context: list[dict[str, Any]]
    retrieved_lore: list[dict[str, Any]]
    retrieved_memories: list[dict[str, Any]]
    visible_world_events: list[dict[str, Any]]
    memory_retrieval_mode: str


@dataclass(frozen=True)
class NPCAction:
    action_type: str
    intent: str
    target: str
    subject: str
    reason: str
    response_style: str
    response_keywords: list[str]
    social_intent: str
    social_stance: dict[str, Any]
    proposed_effects: list[dict[str, Any]]
    raw_decision: dict[str, Any]


@dataclass(frozen=True)
class ActionResult:
    accepted: bool
    blocked_reason: str
    executed_tools: list[dict[str, Any]]
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    state_changes: list[dict[str, Any]]
    events: list[dict[str, Any]]
    response_constraints: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.EnvironmentDataModelTest -v
```

Expected: PASS.

---

### Task 2: Implement Observation and Action Adaptation

**Files:**
- Modify: `src/agent/environment.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing observe/propose test**

Add:

```python
class NarrativeEnvironmentObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"

    def test_observe_and_propose_action_from_decision(self) -> None:
        from src.agent.environment import NarrativeEnvironment

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
            "social_intent": "withhold",
            "social_stance": {"target": "player", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
        }

        action = environment.propose_action_from_decision(decision, observation)

        self.assertEqual(observation.npc_id, "lina")
        self.assertEqual(observation.memory_retrieval_mode, "hybrid")
        self.assertEqual(action.intent, "withhold_ruins_entrance")
        self.assertEqual(action.proposed_effects, [])
        self.assertEqual(action.raw_decision["tools"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.NarrativeEnvironmentObservationTest -v
```

Expected: FAIL with `AttributeError` for missing `NarrativeEnvironment`.

- [ ] **Step 3: Implement environment observation and adaptation**

Append to `src/agent/environment.py`:

```python
from dataclasses import asdict

from src.agent.context import build_context_inputs
from src.storage import database


class NarrativeEnvironment:
    def observe(
        self,
        player_input: str,
        npc_id: str,
        memory_retrieval_mode: str,
    ) -> Observation:
        context_inputs = build_context_inputs(
            player_input=player_input,
            npc_id=npc_id,
            memory_retrieval_mode=memory_retrieval_mode,
        )
        return Observation(
            npc_id=npc_id,
            player_input=player_input,
            npc_state=database.get_npc(npc_id),
            player_state=database.get_player_state(),
            quest_state=database.get_primary_quest_for_npc(npc_id),
            recent_context=context_inputs["recent_context"],
            retrieved_lore=context_inputs["retrieved_lore"],
            retrieved_memories=context_inputs["retrieved_memories"],
            visible_world_events=[],
            memory_retrieval_mode=memory_retrieval_mode,
        )

    def propose_action_from_decision(
        self,
        decision: dict[str, Any],
        observation: Observation,
    ) -> NPCAction:
        tools = decision.get("tools", [])
        proposed_effects = [
            {
                "effect_type": tool.get("name", "unknown"),
                "args": dict(tool.get("args", {})),
            }
            for tool in tools
        ]
        return NPCAction(
            action_type="dialogue",
            intent=str(decision["intent"]),
            target="player",
            subject=self._infer_subject(decision),
            reason=str(decision.get("reasoning", "")),
            response_style=str(decision["response_style"]),
            response_keywords=list(decision["response_keywords"]),
            social_intent=str(decision.get("social_intent", "cooperate")),
            social_stance=dict(decision.get("social_stance", {})),
            proposed_effects=proposed_effects,
            raw_decision=dict(decision),
        )

    def _infer_subject(self, decision: dict[str, Any]) -> str:
        intent = str(decision.get("intent", "general_conversation"))
        if "ruins" in intent:
            return "underground_ruins_entrance"
        if "lost_key" in intent:
            return "lost_key"
        if "gate_badge" in intent:
            return "gate_badge"
        if "ancient_notes" in intent:
            return "ancient_notes"
        if "relic_tip" in intent:
            return "relic_tip"
        return "conversation"

    def trace_payload(self, observation: Observation, action: NPCAction, result: ActionResult) -> dict[str, Any]:
        return {
            "observation_summary": {
                "npc_id": observation.npc_id,
                "player_input": observation.player_input,
                "quest": observation.quest_state,
                "retrieved_lore_count": len(observation.retrieved_lore),
                "retrieved_memories_count": len(observation.retrieved_memories),
                "memory_retrieval_mode": observation.memory_retrieval_mode,
            },
            "npc_action": asdict(action),
            "action_result": asdict(result),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.NarrativeEnvironmentObservationTest -v
```

Expected: PASS.

---

### Task 3: Move Tool Execution Into NarrativeEnvironment

**Files:**
- Modify: `src/agent/environment.py`
- Modify: `src/agent/workflow.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing execution test**

Add:

```python
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
                {"name": "record_world_event", "args": {"event": "Lina recovered her lost key."}},
            ],
            "social_intent": "cooperate",
            "social_stance": {"target": "player", "attitude": "warm", "intensity": 0.8, "reason": "The player helped."},
        }
        action = environment.propose_action_from_decision(decision, observation)
        result = environment.execute(action, observation)

        self.assertTrue(result.accepted)
        self.assertEqual(result.blocked_reason, "")
        self.assertIn("tavern_discount_coupon", result.state_after["player"]["inventory"])
        self.assertEqual(result.state_after["quest"]["status"], "completed")
        self.assertTrue(any(tool["name"] == "record_world_event" for tool in result.executed_tools))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.NarrativeEnvironmentExecutionTest -v
```

Expected: FAIL with missing `execute`.

- [ ] **Step 3: Implement validation and execution**

Append imports and methods in `src/agent/environment.py`:

```python
from src.agent.decision import apply_task_state_machine, validate_decision
from src.agent.workflow import build_state_snapshot, collect_state_changes
from src.tools import sqlite_tools
```

Add these methods inside `NarrativeEnvironment`:

```python
    def validate(self, action: NPCAction, observation: Observation) -> NPCAction:
        validated_decision = apply_task_state_machine(
            validate_decision(dict(action.raw_decision)),
            player_input=observation.player_input,
            npc_state=observation.npc_state,
            quest_state=observation.quest_state,
        )
        return self.propose_action_from_decision(validated_decision, observation)

    def execute(self, action: NPCAction, observation: Observation) -> ActionResult:
        state_before = build_state_snapshot(
            observation.npc_state,
            observation.player_state,
            observation.quest_state,
        )
        blocked_reason = self._blocked_reason(action)
        if blocked_reason:
            state_after = build_state_snapshot(
                database.get_npc(observation.npc_id),
                database.get_player_state(),
                database.get_primary_quest_for_npc(observation.npc_id),
            )
            return ActionResult(
                accepted=False,
                blocked_reason=blocked_reason,
                executed_tools=[],
                state_before=state_before,
                state_after=state_after,
                state_changes=[],
                events=[],
                response_constraints=self._response_constraints([], accepted=False),
            )

        tool_executions = self._execute_tools(action.raw_decision.get("tools", []))
        npc_after = database.get_npc(observation.npc_id)
        player_after = database.get_player_state()
        quest_after = database.get_primary_quest_for_npc(observation.npc_id)
        state_after = build_state_snapshot(npc_after, player_after, quest_after)
        state_changes = collect_state_changes(
            npc_before=observation.npc_state,
            npc_after=npc_after,
            player_before=observation.player_state,
            player_after=player_after,
            quest_before=observation.quest_state,
            quest_after=quest_after,
        )
        executed_tools = sqlite_tools.serialize_tool_executions(tool_executions)
        return ActionResult(
            accepted=True,
            blocked_reason="",
            executed_tools=executed_tools,
            state_before=state_before,
            state_after=state_after,
            state_changes=state_changes,
            events=[tool for tool in executed_tools if tool["name"] == "record_world_event"],
            response_constraints=self._response_constraints(executed_tools, accepted=True),
        )

    def _execute_tools(self, tools: list[dict[str, Any]]) -> list[sqlite_tools.ToolExecution]:
        tool_executions = []
        for tool in tools:
            name = tool["name"]
            args = tool["args"]
            if name == "add_memory":
                tool_executions.append(sqlite_tools.add_memory(**args))
            elif name == "update_trust":
                tool_executions.append(sqlite_tools.update_trust(**args))
            elif name == "update_affection":
                tool_executions.append(sqlite_tools.update_affection(**args))
            elif name == "give_item":
                tool_executions.append(sqlite_tools.give_item(**args))
            elif name == "update_quest_status":
                tool_executions.append(sqlite_tools.update_quest_status(**args))
            elif name == "unlock_location":
                tool_executions.append(sqlite_tools.unlock_location(**args))
            elif name == "record_world_event":
                tool_executions.append(sqlite_tools.record_world_event(**args))
            else:
                raise ValueError(f"Unknown tool: {name}")
        return tool_executions

    def _blocked_reason(self, action: NPCAction) -> str:
        state_machine = action.raw_decision.get("state_machine", {})
        if state_machine.get("blocked"):
            return str(state_machine.get("reason", "Action blocked by task state machine."))
        return ""

    def _response_constraints(self, executed_tools: list[dict[str, Any]], accepted: bool) -> list[str]:
        tool_names = {tool["name"] for tool in executed_tools}
        constraints = []
        if not accepted:
            constraints.append("Do not claim quest completion, location unlocks, item rewards, trust changes, or affection changes.")
        if "unlock_location" not in tool_names:
            constraints.append("Do not claim the underground ruins entrance is unlocked or available.")
        if "give_item" not in tool_names:
            constraints.append("Do not claim the player received an item reward.")
        return constraints
```

- [ ] **Step 4: Remove circular import before running**

If importing `build_state_snapshot` and `collect_state_changes` from `workflow.py` creates a circular import, move those two helper functions from `workflow.py` into `environment.py`, then import them back into `workflow.py` from `src.agent.environment`.

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.NarrativeEnvironmentExecutionTest -v
```

Expected: PASS.

---

### Task 4: Wire Workflow Through Environment

**Files:**
- Modify: `src/agent/workflow.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing workflow environment trace test**

Add:

```python
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
            "social_intent": "withhold",
            "social_stance": {"target": "player", "attitude": "cautious", "intensity": 0.7, "reason": "Trust gate."},
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
        self.assertTrue(any(step["stage"] == "Environment Execution" for step in run.workflow_steps))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.WorkflowEnvironmentTraceTest -v
```

Expected: FAIL because `decision["environment"]` is missing.

- [ ] **Step 3: Update `run_agent_turn()`**

In `src/agent/workflow.py`, import:

```python
from src.agent.environment import NarrativeEnvironment
```

Replace direct context loading and `execute_tools(decision)` with this shape:

```python
    environment = NarrativeEnvironment()
    context_started = perf_counter()
    observation = environment.observe(
        player_input=player_input,
        npc_id=npc_id,
        memory_retrieval_mode=memory_retrieval_mode,
    )
    timings["context_retrieval_ms"] = elapsed_ms(context_started)
    recent_context = observation.recent_context
    retrieved_lore = observation.retrieved_lore
    retrieved_memories = observation.retrieved_memories
    npc_before = observation.npc_state
    player_before = observation.player_state
    quest_before = observation.quest_state
    state_snapshot = build_state_snapshot(npc_before, player_before, quest_before)
```

After `decide_next_action(...)`, replace direct tool execution with:

```python
    decision["memory_retrieval_mode"] = memory_retrieval_mode
    decision["state_before"] = build_state_snapshot(npc_before, player_before, quest_before)
    npc_action = environment.propose_action_from_decision(decision, observation)
    npc_action = environment.validate(npc_action, observation)
    decision = dict(npc_action.raw_decision)
    decision["memory_retrieval_mode"] = memory_retrieval_mode
    decision["state_before"] = build_state_snapshot(npc_before, player_before, quest_before)

    tools_started = perf_counter()
    action_result = environment.execute(npc_action, observation)
    timings["tool_execution_ms"] = elapsed_ms(tools_started)

    tool_calls = action_result.executed_tools
    state_changes = action_result.state_changes
    npc_after = database.get_npc(npc_id)
    player_after = database.get_player_state()
    quest_after = database.get_primary_quest_for_npc(npc_id)
    decision["state_after"] = action_result.state_after
    decision["environment"] = environment.trace_payload(observation, npc_action, action_result)
```

Keep memory job, interaction logging, and `AgentRun(...)` return shape unchanged, using `tool_calls` and `state_changes` from `action_result`.

- [ ] **Step 4: Remove or demote `execute_tools(decision)`**

Delete `execute_tools(decision)` from `workflow.py` if no tests import it. If tests import it, keep a thin compatibility wrapper that constructs `NarrativeEnvironment()._execute_tools(decision["tools"])`, then add a comment that runtime must call environment execution.

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.WorkflowEnvironmentTraceTest -v
```

Expected: PASS.

---

### Task 5: Enforce ActionResult Response Constraints

**Files:**
- Modify: `src/agent/response.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing response constraint test**

Add:

```python
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
            "social_intent": "withhold",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.ResponseConstraintTest -v
```

Expected: FAIL because `generate_npc_response()` does not accept `action_result`.

- [ ] **Step 3: Add parameters and payload fields**

Modify `generate_npc_response(...)` signature:

```python
    observation: Any | None = None,
    npc_action: Any | None = None,
    action_result: Any | None = None,
```

Add to the LLM payload:

```python
                    "observation": asdict(observation) if observation else None,
                    "npc_action": asdict(npc_action) if npc_action else None,
                    "action_result": asdict(action_result) if action_result else None,
                    "response_constraints": (
                        action_result.response_constraints if action_result else []
                    ),
```

Import `asdict` from `dataclasses`.

- [ ] **Step 4: Add constraint guard**

Add:

```python
def violates_action_result_constraints(response: str, action_result: Any | None) -> bool:
    if action_result is None:
        return False
    executed_names = {tool.get("name") for tool in action_result.executed_tools}
    unlock_claims = ["入口已经开放", "入口已开放", "可以直接过去", "已经解锁"]
    reward_claims = ["给你", "收下", "折扣券", "奖励"]
    if "unlock_location" not in executed_names and any(term in response for term in unlock_claims):
        return True
    if "give_item" not in executed_names and any(term in response for term in reward_claims):
        return True
    if not action_result.accepted:
        blocked_claims = unlock_claims + reward_claims + ["任务完成", "已经完成", "更信任你"]
        return any(term in response for term in blocked_claims)
    return False
```

After `validate_response_payload(payload)`:

```python
            if violates_action_result_constraints(response, action_result):
                return fallback_response(decision, npc_state, quest_state), {
                    "provider": settings.provider,
                    "mode": "constraint_guard",
                    "reason": "LLM response violated ActionResult constraints.",
                }
```

- [ ] **Step 5: Pass environment objects from workflow**

In `run_agent_turn()`, add:

```python
        observation=observation,
        npc_action=npc_action,
        action_result=action_result,
```

to the `generate_npc_response(...)` call.

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.ResponseConstraintTest -v
```

Expected: PASS.

---

### Task 6: Make Main Turn Runtime LLM-Required

**Files:**
- Modify: `src/agent/decision.py`
- Modify: `src/agent/llm_client.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing LLM-required decision tests**

Add:

```python
class LLMRequiredRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_ambiguous_turn_requires_configured_llm(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        with self.assertRaisesRegex(RuntimeError, "configured LLM is required"):
            run_agent_turn("你能不能暗中帮我绕过守卫？", npc_id="ron")

    def test_ambiguous_turn_does_not_fallback_to_deterministic_decision_on_llm_error(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        with patch("src.agent.decision.call_openai_compatible_json", side_effect=RuntimeError("network failed")):
            with self.assertRaisesRegex(RuntimeError, "LLM decision failed"):
                run_agent_turn("你能不能暗中帮我绕过守卫？", npc_id="ron")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.LLMRequiredRuntimeTest -v
```

Expected: FAIL because current code falls back to deterministic decisions.

- [ ] **Step 3: Update `decide_next_action()`**

In `src/agent/decision.py`, keep local classification as metadata for the prompt and route every player-facing structured decision through the configured LLM:

```python
    classification = classify_turn(...)
    settings = get_llm_settings()
    if settings.provider != "openai_compatible" or not settings.is_configured:
        raise RuntimeError("A configured LLM is required for structured decisions.")
    try:
        decision = call_openai_compatible_json(...)
        routed = apply_task_state_machine(
            validate_decision(decision),
            player_input=player_input,
            npc_state=npc_state,
            quest_state=quest_state,
        )
        return annotate_decision_route(routed, "llm_assisted", classification)
    except Exception as exc:
        raise RuntimeError(f"LLM decision failed: {exc}") from exc
```

Do not call `mock_decide_next_action(...)` from runtime decision routing. Tests may still use it as a fixture by patching the OpenAI-compatible call.

- [ ] **Step 4: Keep deterministic gates explicit**

Keep local classification and task-state-machine validation as deterministic gates only. They may annotate or constrain the LLM decision, but they must not author the final intent, social stance, response keywords, or tool list without the LLM.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.LLMRequiredRuntimeTest -v
```

Expected: PASS.

---

### Task 7: Update Existing Tests Away From Provider Mock Defaults

**Files:**
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_display_translation.py`

- [ ] **Step 1: Replace main workflow provider defaults**

In test setup blocks that currently contain:

```python
os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"
```

replace with:

```python
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
```

For tests that exercise response generation or ambiguous decisions, patch `src.agent.response.call_openai_compatible_json` and `src.agent.decision.call_openai_compatible_json` as needed.

- [ ] **Step 2: Replace rule-fast-path expectations**

Tests that previously asserted `decision_route == "rule_fast_path"` should now assert `decision_route == "llm_assisted"` when the decision LLM call is patched. Deterministic classification/state-machine tests should assert constraint behavior, not runtime authorship.

- [ ] **Step 3: Replace fallback-template expectation**

Where a test expects:

```python
self.assertEqual(run.decision["response_generation"]["mode"], "fallback_template")
```

change the scenario to patch the response LLM and expect:

```python
self.assertEqual(run.decision["response_generation"]["mode"], "llm_polish")
```

If the test intentionally covers LLM response failure, assert `constraint_guard` or an explicit error path, not normal player-facing deterministic substitution.

- [ ] **Step 4: Run workflow and API tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow tests.test_api tests.test_display_translation -v
```

Expected: PASS.

---

### Task 8: Make Memory Candidate Runtime LLM-Required

**Files:**
- Modify: `src/agent/llm_memory_candidate.py`
- Modify: `src/agent/memory_candidate_review.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing memory test**

Add:

```python
class MemoryLLMRequiredTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_database()

    def test_memory_candidate_generation_requires_llm_when_enabled(self) -> None:
        from src.agent.llm_memory_candidate import generate_memory_candidates
        from src.agent.memory_policy import MemoryPolicyInput

        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["AGENT_NPC_MEMORY_LLM_ENABLED"] = "1"

        policy_input = MemoryPolicyInput(
            npc_id="lina",
            player_input="我把钥匙找回来了。",
            npc_response="谢谢你。",
            recent_context=[],
            retrieved_lore=[],
            retrieved_memories=[],
            state_before={},
            state_after={},
            tool_calls=[],
            state_changes=[],
        )

        with self.assertRaisesRegex(RuntimeError, "Memory LLM is enabled but not configured"):
            generate_memory_candidates(policy_input)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.MemoryLLMRequiredTest -v
```

Expected: FAIL because current code returns disabled metadata instead of raising.

- [ ] **Step 3: Update candidate generator**

In `src/agent/llm_memory_candidate.py`, change the disabled/configuration branch:

```python
    if not memory_llm_enabled():
        raise RuntimeError("Memory LLM is enabled but not configured.")
```

Keep explicit `AGENT_NPC_MEMORY_LLM_ENABLED=0` as the only disabled case if the product needs memory disabled for an ablation run.

- [ ] **Step 4: Update review behavior**

In `src/agent/memory_candidate_review.py`, remove the provider `mock` pass-through branch. If review is enabled and provider is not configured, raise:

```python
raise RuntimeError("Memory review LLM is enabled but not configured.")
```

- [ ] **Step 5: Run memory tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.MemoryLLMRequiredTest -v
```

Expected: PASS.

---

### Task 9: API Environment Trace Coverage

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing API assertion**

In the `/api/turn` test, patch decision and response LLM calls, then assert:

```python
payload = response.json()
environment = payload["run"]["decision"]["environment"]
self.assertIn("observation_summary", environment)
self.assertIn("npc_action", environment)
self.assertIn("action_result", environment)
self.assertEqual(environment["npc_action"]["intent"], "withhold_ruins_entrance")
```

- [ ] **Step 2: Run API test to verify behavior**

Run:

```bash
.venv/bin/python -m unittest tests.test_api -v
```

Expected: PASS after Task 4 wiring.

---

### Task 10: Trace Step Update

**Files:**
- Modify: `src/agent/workflow.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add workflow step assertions**

Add assertions to `WorkflowEnvironmentTraceTest`:

```python
stages = [step["stage"] for step in run.workflow_steps]
self.assertIn("Observation", stages)
self.assertIn("NPC Action", stages)
self.assertIn("Action Validation", stages)
self.assertIn("Environment Execution", stages)
self.assertIn("Action Result", stages)
```

- [ ] **Step 2: Update `build_workflow_steps()`**

Replace the current `Tool Execution` stage with:

```python
        {"stage": "Observation", "result": "Environment observed input, context, lore, memory, and SQLite state."},
        {
            "stage": "NPC Action",
            "result": f"Action intent: {decision.get('environment', {}).get('npc_action', {}).get('intent', decision['intent'])}.",
        },
        {
            "stage": "Action Validation",
            "result": (
                "Accepted."
                if decision.get("environment", {}).get("action_result", {}).get("accepted", True)
                else f"Blocked: {decision.get('environment', {}).get('action_result', {}).get('blocked_reason', 'unknown')}"
            ),
        },
        {"stage": "Environment Execution", "result": f"Executed {len(tool_calls)} environment-approved tool call(s)."},
        {"stage": "Action Result", "result": f"Recorded {len(state_changes)} state change(s)."},
```

Keep `Response Generation`, `Memory Policy`, and `Trace Logging`.

- [ ] **Step 3: Run workflow trace test**

Run:

```bash
.venv/bin/python -m unittest tests.test_workflow.WorkflowEnvironmentTraceTest -v
```

Expected: PASS.

---

### Task 11: Documentation Update

**Files:**
- Modify: `docs/design/llm_integration.md`
- Modify: `docs/design/environment_refactor_plan.md`

- [ ] **Step 1: Update LLM integration defaults**

Change language that says the project defaults to provider `mock` for the main turn workflow. The new documented runtime contract:

```text
Player-facing runtime requires AGENT_NPC_LLM_PROVIDER=openai_compatible and a configured API key.
Local classification and task-state-machine validation remain deterministic rule gates.
Tests may patch OpenAI-compatible calls, but should not configure the main turn workflow as provider=mock.
```

- [ ] **Step 2: Add environment plan addendum**

Add a short addendum to `docs/design/environment_refactor_plan.md`:

```text
LLM-required runtime constraint:
When a component has a mock-vs-LLM branch, Phase 1 implementation must route runtime behavior through the LLM branch. The allowed deterministic exceptions are local classification, task-state-machine validation, schema validation, and business-rule enforcement.
```

- [ ] **Step 3: Run documentation grep**

Run:

```bash
rg -n "AGENT_NPC_LLM_PROVIDER=mock|provider=mock|mock mode|mock 模式" docs src tests -g '!frontend/node_modules' -g '!frontend/dist'
```

Expected: remaining hits are historical notes, explicit test patching references, or non-runtime embedding docs. Update any main-turn runtime guidance that still says mock is the default.

---

### Task 12: Final Verification

**Files:**
- Verify: full repository behavior

- [ ] **Step 1: Run backend suite serially**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Check generated artifact churn**

Run:

```bash
git status --short
```

Expected: implementation files are modified; generated churn such as `data/agent_trace_export.json` is reviewed before staging and is not included unless the user explicitly wants it.

- [ ] **Step 4: Manual smoke with patched or real LLM configuration**

For real runtime:

```bash
export AGENT_NPC_LLM_PROVIDER=openai_compatible
export AGENT_NPC_LLM_API_KEY="$OPENAI_API_KEY"
.venv/bin/python -m unittest tests.test_workflow.WorkflowEnvironmentTraceTest -v
```

Expected: PASS when tests patch calls; a real local app run requires an actual API key and should show `decision.environment` in the trace JSON.

---

## Self-Review

- Spec coverage: Covers environment dataclasses, observation, action adaptation, validation, execution, response constraints, trace, API, test plan, and frontend build verification.
- LLM-required constraint: Explicitly included for decision, response, memory candidate/review, docs, and tests. Rule classification and task-state-machine validation are preserved as deterministic rule gates.
- Scope control: Does not add Goal, Belief, Plan, Reflection, rumor propagation, agent ticks, event sourcing, or database schema redesign.
- Type consistency: Uses `Observation`, `NPCAction`, and `ActionResult` consistently across environment, workflow, response, trace, and API tests.
