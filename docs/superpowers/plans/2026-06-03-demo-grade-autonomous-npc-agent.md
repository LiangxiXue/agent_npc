# Demo-Grade Autonomous NPC Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a demo-grade LLM-constrained autonomous NPC runtime without replacing the existing player-driven workflow.

**Architecture:** Add a parallel autonomous path around the existing `NPCMind`, `NarrativeEnvironment`, and `ActionValidator`. World events are stored structurally, dispatched through visibility-filtered inbox items, consumed by `run_autonomous_tick`, constrained by `ActionCatalog`, executed only through `NarrativeEnvironment.execute()`, and persisted to plans, cooldowns, proactive messages, and autonomous trace logs.

**Tech Stack:** Python, SQLite, FastAPI, unittest, OpenAI-compatible LLM client.

---

### Task 1: Schema And Storage Migration

**Files:**
- Modify: `src/storage/schema.sql`
- Modify: `src/storage/database.py`
- Test: `tests/test_autonomous_storage.py`

- [ ] Write failing tests for structured `world_events`, legacy fallback, additive columns, `npc_event_inbox`, `autonomous_tick_logs`, `proactive_messages`, `npc_plans`, `npc_cooldowns`, and `npc_runtime_state`.
- [ ] Run `python -m unittest tests.test_autonomous_storage -v` and confirm failures are due to missing storage APIs/schema.
- [ ] Implement additive migration helpers and typed storage functions while preserving `record_world_event(content)` compatibility.
- [ ] Run `python -m unittest tests.test_autonomous_storage -v`.
- [ ] Commit schema/storage changes.

### Task 2: Visibility Resolver, Inbox Dispatch, And Event API

**Files:**
- Create: `src/agent/event_visibility.py`
- Modify: `src/agent/environment.py`
- Modify: `src/api/server.py`
- Test: `tests/test_event_visibility.py`
- Test: `tests/test_api.py`

- [ ] Write failing tests for `public`, `location`, `private`, and `npc_only` dispatch, inbox seen behavior, and invisible event exclusion from observations.
- [ ] Write failing API tests for `POST /api/world/events`, optional inbox/runtime GET endpoints, and no direct NPC tick side effects from event creation.
- [ ] Implement visibility resolver, inbox dispatch, visible-event loading, and API models.
- [ ] Run `python -m unittest tests.test_event_visibility tests.test_api -v`.
- [ ] Commit event visibility and API changes.

### Task 3: ActionCatalog And Preconditions

**Files:**
- Create: `src/agent/action_catalog.py`
- Test: `tests/test_action_catalog.py`

- [ ] Write failing tests for Lina, Ron, Mira, and Sable available actions, unavailable action reasons, Ron badge evidence preconditions, and Sable forbidden effects.
- [ ] Implement `ActionSpec`, `get_available_actions`, `get_unavailable_actions_with_reasons`, and `serialize_actions_for_llm_prompt`.
- [ ] Run `python -m unittest tests.test_action_catalog -v`.
- [ ] Commit catalog changes.

### Task 4: LLM-Constrained Autonomous Tick

**Files:**
- Create: `src/agent/autonomous_tick.py`
- Modify: `src/agent/workflow.py`
- Modify: `src/agent/action_validator.py`
- Test: `tests/test_autonomous_tick.py`

- [ ] Write failing tests for `run_autonomous_tick(mode="llm_constrained")`, available-action rejection, one-command guard, invalid args trace, memory-only outcome, no-op outcome, and `NarrativeEnvironment.execute()` integration.
- [ ] Implement autonomous context building, LLM JSON decision parsing, deterministic fallback, selected-action to existing decision conversion, validation envelope, and tick timeline.
- [ ] Run `python -m unittest tests.test_autonomous_tick -v`.
- [ ] Commit autonomous tick changes.

### Task 5: Proactive Mailbox, Plans, Cooldowns, And Lifecycle

**Files:**
- Modify: `src/agent/autonomous_tick.py`
- Modify: `src/api/server.py`
- Test: `tests/test_autonomous_tick.py`
- Test: `tests/test_api.py`

- [ ] Write failing tests for proactive mailbox polling/delivery, plan blocker persistence, cooldown suppression, proactive budget, paused memory-only behavior, and disabled no-op behavior.
- [ ] Implement `proactive_messages`, `npc_plans`, `npc_cooldowns`, and `npc_runtime_state` behavior in tick and API endpoints.
- [ ] Run `python -m unittest tests.test_autonomous_tick tests.test_api -v`.
- [ ] Commit mailbox/plan/runtime changes.

### Task 6: Autonomous Trace API And Demo View

**Files:**
- Modify: `src/api/server.py`
- Modify: `src/agent/trace_export.py`
- Test: `tests/test_api.py`

- [ ] Write failing tests for `GET /api/trace/autonomous/{tick_log_id}` returning trigger, visible events, memories, available/unavailable actions, LLM decision, validation, action result, plan update, reflection, proactive message, and ordered timeline.
- [ ] Implement JSON trace endpoint and a simple HTML rendering path when `?format=html` is requested.
- [ ] Run `python -m unittest tests.test_api -v`.
- [ ] Commit trace changes.

### Task 7: Demo Scripts, Docs, And Full Verification

**Files:**
- Create: `scripts/reset_demo_db.py`
- Create: `scripts/seed_autonomous_demo.py`
- Create: `scripts/run_autonomous_llm_demo.py`
- Create: `docs/demo_autonomous_tick.md`
- Modify: `docs/design/autonomous_tick_next_slice_plan.md`
- Modify: `docs/reference/external_pattern_library_for_agent_npc.md`
- Modify: `docs/evaluation/test_plan.md`
- Modify: `docs/delivery/demo_script.md`
- Modify: `docs/README.md`

- [ ] Add scripts for reset, seeding, and real OpenAI-compatible LLM demo cases: `lina_early_ruins`, `ron_badge_verified`, and `sable_deception_constrained`.
- [ ] Update docs with architecture, schema, demo API flow, trace screenshots/log instructions, and test plan.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run smoke checks for the demo scripts with mocked or skipped LLM where appropriate.
- [ ] Commit demo/docs changes.

### Self-Review Checklist

- [ ] Existing player `/api/turn` and `run_agent_turn` behavior remains intact.
- [ ] World events are not treated as player input.
- [ ] NPC observations include only visibility-approved events.
- [ ] LLM selects from available actions and cannot directly mutate world facts.
- [ ] All world side effects pass through `ActionValidator` and `NarrativeEnvironment.execute()`.
- [ ] Sable can mislead but cannot unlock, complete quests, grant access, rewrite lore facts, or modify other NPC trust.
- [ ] Trace explains every autonomous decision stage.
- [ ] Full unittest suite passes.
