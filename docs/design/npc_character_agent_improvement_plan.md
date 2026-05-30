# NPC Character Agent Improvement Plan

## Goal

Upgrade the current environment-driven NPC workflow into a character-agent workflow based on `docs/design/npc_character_agent_plan.md`.

The improvement should turn each NPC from a turn-by-turn responder into a narrative character agent that can:

- hold subjective beliefs that differ from world facts;
- select goals from belief, emotion, relationship, quest, and lore context;
- advance plans across multiple turns;
- express each action through `social_intent` and `social_stance`;
- let `NarrativeEnvironment` validate and execute world consequences;
- reflect after meaningful results and write future-facing memory;
- generate player-facing dialogue constrained by the actual `ActionResult`.

The player-facing runtime must keep using the configured LLM path for decision and response generation. Deterministic logic remains appropriate for classification, schema validation, task-state-machine checks, action validation, state updates, and test fixtures.

## Current Baseline

The project already has the first environment foundation:

- `src/agent/environment.py` defines `Observation`, `NPCAction`, `ActionResult`, and `NarrativeEnvironment`.
- `src/agent/workflow.py` routes tool execution through `NarrativeEnvironment.execute()` instead of directly executing `decision["tools"]`.
- `src/agent/response.py` receives `observation`, `npc_action`, `action_result`, and response constraints.
- `tests/test_workflow.py` covers environment dataclass shape, environment execution, validation blocking, environment trace, LLM-required runtime behavior, and response constraint guards.
- `src/storage/schema.sql` already supports typed memories with `memory_type`, `facets`, `scope`, `evidence_text`, `stability`, and `future_usefulness`.

That means this plan should not restart the environment refactor. It should build the character-mind layer on top of the existing environment loop.

## Architecture Direction

Target runtime shape:

```text
Player Input
-> NarrativeEnvironment.observe()
-> NPCMind.perceive()
-> BeliefUpdater
-> EmotionEngine
-> GoalManager
-> Planner
-> SocialStrategySelector
-> NPCActionProposer
-> NarrativeEnvironment.validate()
-> NarrativeEnvironment.execute()
-> ReflectionEngine
-> MemoryWriter / belief-plan-emotion persistence
-> ResponseGenerator
-> Trace
```

Responsibility split:

- Environment layer: observes current world state, validates proposed actions, executes legal consequences, records real events.
- NPC mind layer: interprets the observation, updates subjective state, chooses goals, advances plans, selects social strategy, proposes actions.
- Response layer: turns character state plus action result into in-character Chinese dialogue without inventing consequences.
- Memory layer: stores episodic facts, relational changes, procedural guidance, and character-agent facets such as `belief`, `plan`, and `reflection`.

## Stage 0: Stabilize The Environment Boundary

Purpose: make the current environment layer a reliable base before adding more mind state.

Work:

- Extract validation responsibility from `src/agent/environment.py` into `src/agent/action_validator.py`.
- Keep `decision.py` responsible for structured LLM decision normalization and business-rule helpers.
- Keep `NarrativeEnvironment` responsible for observation, action execution, and trace packaging.
- Remove duplicate validation calls where possible. `trace_payload()` should report the already validated action rather than revalidating with possible side effects or drift.
- Expand `ActionResult.events` beyond raw `record_world_event` tool calls into a stable event shape with `event_type`, `actor_id`, `target_id`, `content`, `visibility`, and `payload`.

Primary files:

- `src/agent/environment.py`
- `src/agent/action_validator.py`
- `src/agent/decision.py`
- `src/agent/workflow.py`
- `tests/test_workflow.py`

Acceptance:

- Environment execution still blocks invalid quest completion before tools run.
- Response constraints still prevent false unlock, reward, quest-completion, trust, and affection claims.
- Workflow trace still includes Observation, NPC Action, Action Validation, Environment Execution, Action Result, and Response Generation.

## Stage 1: Add NPC Mind Data Models

Purpose: introduce stable typed objects before adding behavior.

Create `src/agent/npc_mind.py` with dataclasses:

- `Belief`: `belief_id`, `npc_id`, `content`, `confidence`, `source`, `evidence`, `stance`, `created_at`, `updated_at`.
- `EmotionState`: `npc_id`, `mood`, `suspicion`, `tension`, `fear`, `curiosity`, `respect`, `manipulation_pressure`.
- `Goal`: `goal_id`, `npc_id`, `goal_type`, `description`, `priority`, `status`, `reason`.
- `Plan`: `plan_id`, `npc_id`, `goal_id`, `steps`, `current_step`, `status`.
- `PlanStep`: `step_id`, `description`, `status`.
- `MindState`: current beliefs, emotion, active goal, active plan, and relevant memories.
- `MindUpdate`: belief updates, emotion updates, goal selection reason, plan changes, and trace metadata.

Initial persistence should be conservative:

- Prefer storing `belief`, `plan`, and `reflection` as `memories.facets` first.
- Add dedicated tables only when behavior needs reliable update/query semantics that become awkward in the generic memory table.

Primary files:

- `src/agent/npc_mind.py`
- `src/storage/database.py`
- `tests/test_npc_mind.py`

Acceptance:

- Tests can instantiate and serialize each mind dataclass.
- Mind objects can be included in trace JSON without losing nested fields.
- No player-facing behavior changes yet.

## Stage 2: Implement Belief And Emotion Updates

Purpose: let the NPC interpret the same observation differently depending on role, lore, relationship, and recent context.

Work:

- Implement `BeliefUpdater.update(observation, mind_state)`.
- Implement `EmotionEngine.update(observation, belief_updates, mind_state)`.
- Start deterministic and transparent:
  - Lina: ruins-access pressure raises `suspicion` and `tension`.
  - Ron: unsupported access claims raise procedural suspicion.
  - Mira: concrete observations raise `curiosity` and `respect`; rumor-like claims raise skepticism.
  - Sable: ruins leads raise `curiosity` and `manipulation_pressure`.
- Store belief and emotion summaries in trace.
- Persist high-value belief changes as typed memory rows:
  - `memory_type`: `procedural` or `relational`, depending on future use.
  - `facets`: include `belief`, NPC id, subject, and stance.
  - `evidence_text`: the player input or `ActionResult` event that caused it.

Primary files:

- `src/agent/npc_mind.py`
- `src/agent/workflow.py`
- `src/agent/memory_jobs.py`
- `src/agent/llm_memory_candidate.py`
- `src/agent/memory_candidate_gate.py`
- `tests/test_npc_mind.py`
- `tests/test_workflow.py`

Acceptance:

- Low-trust Lina ruins request creates or updates a belief that the player is pushing toward sensitive ruins access.
- The same ruins request can produce different belief stance for Lina, Ron, Mira, and Sable.
- Emotion deltas are bounded and deterministic in tests.
- Reflection/belief memory never appears directly in player-facing response text.

## Stage 3: Add Goal Selection

Purpose: make responses explainable by what the NPC wants, not only by the latest player input.

Work:

- Seed per-NPC long-term goals from lore:
  - Lina protects the tavern and underground ruins entrance while testing trust.
  - Ron protects public order and verifies evidence before access.
  - Mira seeks grounded research observations and resists rumor.
  - Sable extracts useful ruins or relic leads while hiding manipulative intent.
- Implement `GoalManager.select(observation, belief_updates, emotion_update, mind_state)`.
- Keep priority scoring deterministic at first. Use inputs such as intent classification, quest status, hidden alignment, trust, suspicion, and relevant beliefs.
- Add goal selection to workflow trace.

Primary files:

- `src/agent/npc_mind.py`
- `src/agent/lore_seed.py`
- `data/lore/npc_lina.md`
- `data/lore/npc_ron.md`
- `data/lore/npc_mira.md`
- `data/lore/npc_sable.md`
- `tests/test_npc_mind.py`

Acceptance:

- A ruins-access request activates Lina's protection/trust-test goal at low trust.
- The same request activates Sable's lead-extraction goal.
- Goal selection reason is visible in trace but not spoken directly to the player.

## Stage 4: Add Multi-Turn Plans

Purpose: let an NPC pursue a strategy across turns instead of restarting from scratch.

Work:

- Implement `Planner.advance_or_create(observation, active_goal, mind_state)`.
- Represent plan lifecycle with `pending`, `active`, `completed`, `blocked`, and `abandoned`.
- For Lina, create a `test_player_trust` plan:
  - `ask_motive`
  - `offer_minor_task`
  - `reward_trust`
  - `partial_disclosure`
- Advance plans from `ActionResult`, not from dialogue claims.
- Persist plan state through memory facets initially:
  - `facets`: `plan`, `plan:<plan_id>`, `goal:<goal_id>`, current step.
- Add trace output for active plan and current step.

Primary files:

- `src/agent/npc_mind.py`
- `src/agent/workflow.py`
- `src/agent/memory_policy.py`
- `src/storage/database.py`
- `tests/test_npc_mind.py`
- `tests/test_workflow.py`

Acceptance:

- Lina does not reveal the ruins entrance on first low-trust request.
- A later turn can continue the same trust-test plan instead of treating the request as brand new.
- Plan advancement only happens after accepted environment results.

## Stage 5: Move Social Strategy Under NPCAction

Purpose: preserve the current social strategy layer while making it one expression of a wider character mind.

Work:

- Implement `SocialStrategySelector.select(observation, active_goal, plan, emotion_update)`.
- Keep existing allowed social intents:
  - `cooperate`
  - `conceal`
  - `probe`
  - `deceive`
  - `redirect`
  - `ally`
  - `oppose`
  - `accuse`
- Extend `NPCAction` from generic `dialogue` to richer action types:
  - `probe_intent`
  - `withhold_information`
  - `request_evidence`
  - `accept_returned_item`
  - `reward_trust`
  - `share_partial_information`
  - `redirect_topic`
  - `deceive_for_leverage`
  - `challenge_claim`
  - `seek_clarification`
- Keep `social_intent` and `social_stance` as fields on `NPCAction`.
- Update prompts so the LLM proposes an action compatible with the selected mind state instead of inventing direct tools.

Primary files:

- `src/agent/npc_mind.py`
- `src/agent/environment.py`
- `src/agent/prompts.py`
- `src/agent/decision.py`
- `tests/test_npc_mind.py`
- `tests/test_workflow.py`

Acceptance:

- `NPCAction` contains action type, goal id, plan step, social intent, social stance, intended effects, and speech goal.
- A social strategy cannot grant permission to mutate state; `ActionValidator` remains the authority.
- Trace shows belief -> goal -> plan -> social strategy -> proposed action.

## Stage 6: Add Reflection

Purpose: make meaningful outcomes change future behavior.

Work:

- Implement `ReflectionEngine.reflect(observation, npc_action, action_result, mind_state)`.
- Reflections should update:
  - beliefs;
  - plan step status;
  - emotion deltas;
  - future procedural memory;
  - social strategy hints.
- Store reflection records as memory rows first:
  - `memory_type`: `procedural`
  - `facets`: `reflection`, NPC id, goal id, plan id, subject.
  - `evidence_text`: concise summary of the accepted or blocked `ActionResult`.
- Keep reflection text internal. It may appear in developer trace, not in NPC dialogue.

Primary files:

- `src/agent/npc_mind.py`
- `src/agent/workflow.py`
- `src/agent/memory_jobs.py`
- `src/agent/llm_memory_candidate.py`
- `tests/test_npc_mind.py`
- `tests/test_workflow.py`

Acceptance:

- A blocked action creates a reflection that the NPC must adapt rather than pretend success.
- Lina's repeated ruins-pressure reflection increases guarded behavior in later turns.
- Reflection memory is retrievable for future decisions but not spoken as "我记住了".

## Stage 7: Response Integration

Purpose: make final dialogue reflect character mind without leaking internal mechanics.

Work:

- Pass a compact mind payload into `generate_npc_response()`:
  - belief summary;
  - active goal;
  - current plan step;
  - emotion state;
  - social stance;
  - action result constraints;
  - optional reflection summary.
- Update `RESPONSE_SYSTEM_PROMPT` to treat mind state as private character context.
- Expand constraint guards to cover plan and reflection leaks:
  - do not mention `belief_id`, `goal_id`, plan ids, JSON, database fields, or trace stages.
  - do not claim plan advancement unless the environment result supports it.
- Keep response concise and Chinese-only, as the current prompt requires.

Primary files:

- `src/agent/response.py`
- `src/agent/prompts.py`
- `src/agent/workflow.py`
- `tests/test_workflow.py`

Acceptance:

- Player-facing text reflects guarded, curious, manipulative, or procedural tone naturally.
- Internal belief, goal, plan, and reflection ids never leak into NPC dialogue.
- `ActionResult.response_constraints` still override any LLM attempt to invent outcomes.

## Stage 8: Evaluation And Demo

Purpose: prove the system is no longer a linear chatbot.

Add scripted demos and tests for:

1. Same input, different belief state -> different response.
2. Same input, different active goal -> different action.
3. Multi-turn plan advances across turns.
4. NPC refuses or redirects based on hidden goal.
5. Reflection changes future strategy.
6. Environment blocks a desired action and NPC adapts.

Primary files:

- `scripts/run_mvp_demo.py`
- `scripts/run_memory_eval.py`
- `docs/evaluation/test_plan.md`
- `docs/delivery/demo_script.md`
- `tests/test_npc_mind.py`
- `tests/test_workflow.py`

Acceptance:

- Automated unit tests cover belief, emotion, goal, plan, social strategy, reflection, and response constraints.
- Demo script includes at least Lina and Sable showing different interpretations of ruins-related input.
- Evaluation docs distinguish engineering trace from player-facing project presentation.

## Recommended Implementation Order

1. Finish Stage 0 first. It lowers risk by making the environment boundary explicit.
2. Add Stage 1 data models with tests and no runtime behavior change.
3. Add Stage 2 belief/emotion updates behind the workflow trace first.
4. Add Stage 3 goal selection and Stage 4 plan advancement only after belief/emotion trace is stable.
5. Move social strategy into richer `NPCAction` in Stage 5.
6. Add reflection in Stage 6 once plans and action results have stable ids.
7. Tighten response generation in Stage 7.
8. Update demos and evaluation docs in Stage 8.

## Testing Commands

Use the project virtual environment:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

For frontend trace/UI regression after workflow trace changes:

```bash
cd frontend && npm run build
```

Do not run the SQLite-backed unittest groups in parallel.

## Open Decisions

- Dedicated tables vs memory facets: start with memory facets for `belief`, `plan`, and `reflection`; move to tables only when update/query needs justify schema growth.
- LLM role in NPCMind: deterministic mind components should come first for testability. Later, the LLM can assist belief wording, reflection summaries, and plan alternatives, but program validation must remain authoritative.
- Plan persistence scope: initial plan state can be NPC-specific. Cross-NPC rumor propagation or autonomous agent ticks should stay out of this phase.
- UI trace polish: JSON trace is enough at first. A custom visual timeline can come after behavior is proven.
