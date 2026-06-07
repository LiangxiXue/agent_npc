# Traveler Dialogue Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a classroom-ready Traveler trace where each speaking turn records what the Traveler says, what the NPC replies, what state changes, and why the main arc advances.

**Architecture:** Keep Traveler as the first actor in each round. When Traveler selects a direct social action, synthesize a first-person utterance from the LLM decision, route only that utterance to the target NPC response layer, record the NPC LLM reply and any validated state changes, then let ArcDirector score the resulting events. Non-speaking Traveler actions keep the existing move/investigate behavior.

**Tech Stack:** Python, pytest, SQLite-backed runtime, existing OpenAI-compatible LLM client, existing Traveler/NPC response generation and timeline export.

---

### Task 1: Record Traveler Utterances

**Files:**
- Modify: `src/agent/traveler_decision.py`
- Modify: `src/agent/traveler_tick.py`
- Test: `tests/test_traveler_tick.py`

- [ ] **Step 1: Write the failing test**

Add a test that patches the Traveler LLM decision for `talk_to` with `traveler_utterance`, runs one tick, and asserts the created event payload includes that utterance.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py::TravelerTickTest::test_tick_talk_to_records_traveler_utterance -q`

Expected: fail because current Traveler decisions do not preserve `traveler_utterance`.

- [ ] **Step 3: Implement minimal code**

Extend the Traveler decision prompt/schema and normalization to include `traveler_utterance`. In `_execute_traveler_action`, attach it to social-action event payloads.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py::TravelerTickTest::test_tick_talk_to_records_traveler_utterance -q`

Expected: pass.

### Task 2: Generate Direct NPC Replies

**Files:**
- Modify: `src/agent/traveler_tick.py`
- Test: `tests/test_traveler_tick.py`

- [ ] **Step 1: Write the failing test**

Add a test for a `talk_to` Traveler tick that patches NPC response generation and asserts the tick result contains `dialogue_exchange` with `traveler_utterance`, `npc_response`, `npc_id`, and response generation metadata.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py::TravelerTickTest::test_tick_talk_to_records_npc_dialogue_response -q`

Expected: fail because current ticks do not call NPC response generation for Traveler social actions.

- [ ] **Step 3: Implement minimal code**

For direct social actions, construct a small NPC decision from the Traveler utterance and call `generate_npc_response`. Record the reply in the `TravelerTickResult`, tick log decision/reflection payload, and created event payload. The NPC must receive only the Traveler utterance as `player_input`; canonical state mutation remains under existing validation/execution.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py::TravelerTickTest::test_tick_talk_to_records_npc_dialogue_response -q`

Expected: pass.

### Task 3: Export Dialogue and Arc Evidence

**Files:**
- Modify: `src/agent/living_world_runtime.py`
- Modify: `src/agent/timeline_export.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write the failing test**

Add an export test with a round containing `dialogue_exchange` and `arc_update.scores`, then assert Markdown includes "Traveler says", "NPC replies", "State changes", and "Arc evidence".

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_timeline_export_renders_dialogue_and_arc_evidence -q`

Expected: fail because current Markdown omits dialogue text and arc scoring evidence.

- [ ] **Step 3: Implement minimal code**

Include `dialogue_exchange` in serialized Traveler ticks. Update Markdown export to render Traveler utterance, NPC reply, direct state/relationship changes, and per-round arc scores/cumulative scores.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_timeline_export_renders_dialogue_and_arc_evidence -q`

Expected: pass.

### Task 4: Verify and Produce Real LLM Classroom Trace

**Files:**
- Output: `data/traces/classroom_dialogue_llm_run/*.json`
- Output: `data/traces/classroom_dialogue_llm_run/*.md`

- [ ] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py tests\test_living_world_runtime.py -q`

Expected: pass.

- [ ] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: pass.

- [ ] **Step 3: Run real LLM trace**

Run: `.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --max-npc-ticks 0 --stop-on-outcome --export-dir data/traces/classroom_dialogue_llm_run`

Expected: exported JSON and Markdown; Traveler ticks are `mode=llm`; speaking rounds contain LLM-generated Traveler utterance and LLM-generated NPC reply; final arc phase is `resolved` with non-empty outcome.
