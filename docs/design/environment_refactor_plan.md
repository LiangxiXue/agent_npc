# Environment Refactor Plan

## Goal

Refactor the current linear turn workflow:

```text
player_input -> context -> decision(tools) -> execute_tools -> response -> memory/trace
```

Into an environment-driven workflow:

```text
player_input
-> NarrativeEnvironment.observe()
-> decision proposes NPCAction
-> ActionValidator validates
-> NarrativeEnvironment.execute()
-> ActionResult
-> response from Observation + NPCAction + ActionResult
-> memory/trace
```

Phase 1 only changes the environment layer. Do not implement Goal, Belief, Plan, Reflection, rumor propagation, or agent ticks yet.

The main goal is to move world-state authority away from `decision["tools"]` and into the environment.

## Core Principles

1. LLM and decision code should not directly own database tool calls.
2. NPCs propose narrative action intent.
3. The environment observes, validates, executes, and records consequences.
4. Existing state machine rules, SQLite tools, memory jobs, and trace behavior should be reused where possible.
5. Build the smallest working loop first, then extend NPC intelligence later.

## LLM-Required Runtime Constraint

When a component has a mock-vs-LLM branch, Phase 1 implementation must route player-facing runtime behavior through the LLM branch. The allowed deterministic exceptions are local classification, task-state-machine validation, schema validation, and business-rule enforcement.

## Phase 1: Add Environment Data Structures

Create:

```text
src/agent/environment.py
```

Define three core dataclasses:

```python
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

Keep `proposed_effects` simple in the first version. It can initially be a readable list derived from the old tool calls.

## Phase 2: Add NarrativeEnvironment

In `src/agent/environment.py`, define:

```python
class NarrativeEnvironment:
    def observe(...)
    def propose_action_from_decision(...)
    def validate(...)
    def execute(...)
```

Responsibilities:

```text
observe:
Reuse build_context_inputs plus database state loading to produce Observation.

propose_action_from_decision:
Temporarily adapt the existing decision object into NPCAction.

validate:
Reuse existing decision validation and task-state-machine rules.

execute:
Execute validated actions through existing sqlite_tools.
```

In Phase 1, `raw_decision` may still contain old `tools`, but `workflow.py` should no longer execute `decision["tools"]` directly. Tool execution must go through `NarrativeEnvironment.execute()`.

## Phase 3: Update workflow.py

Modify:

```text
src/agent/workflow.py
```

Current shape:

```text
build_context_inputs
-> decide_next_action
-> execute_tools(decision)
-> generate_npc_response
```

Target shape:

```text
environment = NarrativeEnvironment(...)
observation = environment.observe(...)
decision = decide_next_action(... fields from observation ...)
npc_action = environment.propose_action_from_decision(decision, observation)
validated_action = environment.validate(npc_action, observation)
action_result = environment.execute(validated_action, observation)
npc_response = generate_npc_response(... observation + npc_action + action_result ...)
```

Keep `decide_next_action()` mostly intact in the first pass. The important change is that tool execution moves from `workflow.execute_tools(decision)` into the environment.

## Phase 4: Extract ActionValidator Later

Current validation logic lives mostly in:

```text
src/agent/decision.py
- validate_decision()
- validate_tool_call()
- validate_decision_business_rules()
- apply_task_state_machine()
```

Do not move all of this immediately. In the first version, `environment.py` can call these functions.

After the environment loop is stable, create:

```text
src/agent/action_validator.py
```

Target responsibility split:

```text
decision.py:
Generate and normalize NPC action semantics.

action_validator.py:
Validate whether an action is legal and stage-appropriate.

environment.py:
Build observations and execute validated actions.
```

## Phase 5: Update response.py Semantics

Current response generation depends on:

```text
decision
tool_calls
state_changes
```

Phase 1 can keep those parameters, but also pass:

```text
observation
npc_action
action_result
```

The response must obey `ActionResult.response_constraints`.

Rules:

```text
If action_result.accepted is false:
The response must not claim quest completion, location unlock, item reward, or relationship change.

If action_result has no unlock_location effect:
The response must not say the entrance is unlocked or available.

If action_result has no give_item effect:
The response must not say the player received a reward.
```

This prevents a mismatch where the database rejects an action but the NPC dialogue still claims it happened.

## Phase 6: Enhance Trace

Avoid schema changes in the first pass. Store the environment trace inside the existing `decision` JSON:

```python
decision["environment"] = {
    "observation_summary": ...,
    "npc_action": asdict(npc_action),
    "action_result": asdict(action_result),
}
```

Update `build_workflow_steps()` to show:

```text
Observation
NPC Action
Action Validation
Environment Execution
Action Result
Response Generation
```

The developer trace panel can display the new environment block through the existing JSON trace view first. A polished UI can come later.

## Phase 7: Test Plan

Update or add tests in:

```text
tests/test_workflow.py
tests/test_api.py
```

Required coverage:

1. Lina low-trust ruins request
   - `NPCAction` should represent withholding information.
   - `ActionResult.accepted` should be true.
   - No location should be unlocked.

2. Lina returned key
   - Environment completes `lost_key`.
   - Trust increases.
   - Player receives `tavern_discount_coupon`.
   - A world event is recorded.

3. Direct completion before task start
   - Validator blocks or downgrades the action.
   - The result should request evidence or probe instead of completing the quest.

4. Sable cannot unlock ruins entrance
   - Even if Sable action involves relic or entrance information, the environment must not execute `unlock_location`.

5. API turn response
   - `/api/turn` should return `run.decision.environment`.
   - Trace should include `npc_action` and `action_result`.

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Also run the frontend build after any type or API-contract changes:

```bash
cd frontend
npm run build
```

## Phase 8: Frontend Minimum

Do not redesign the player UI in Phase 1.

Only expose the new data in the developer trace panel:

```text
Environment
- observed context
- proposed action
- validation result
- executed effects
```

If the existing trace JSON already displays it, that is enough for the first pass.

## Recommended Implementation Order

Follow this order strictly:

```text
1. Add environment.py dataclasses and NarrativeEnvironment shell.
2. Implement observe() using existing context and state reads.
3. Implement propose_action_from_decision() to adapt old decisions into NPCAction.
4. Move tool execution into NarrativeEnvironment.execute().
5. Wire workflow.py through environment.observe / validate / execute.
6. Record npc_action and action_result in trace.
7. Run backend tests.
8. Run frontend build.
9. Only then weaken or remove decision["tools"] as a direct decision output.
```

## Do Not Do In Phase 1

Do not implement:

```text
GoalManager
BeliefUpdater
Planner
ReflectionWriter
Rumor propagation
Agent tick
Complete event sourcing
Large database schema redesign
```

Those belong to the later NPC intelligence phase.

## Completion Criteria

Phase 1 is complete when:

```text
NPC/LLM output is represented as action intent, not direct database operation.
The environment decides actual state changes.
Responses are constrained by ActionResult.
Trace explains observation, action, validation, and consequence.
Existing workflow/API behavior still passes equivalent tests.
```

After that, Phase 2 can add the single-NPC intelligence layer:

```text
Observation
-> Belief
-> Goal
-> Plan
-> NPCAction
-> ActionResult
-> Reflection
-> Response
```
