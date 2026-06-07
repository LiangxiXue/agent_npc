# Arc Evidence and NPC Tick Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make arc progression use meaningful evidence instead of routine noise, and make timeline reports explicit about direct dialogue versus autonomous NPC ticks.

**Architecture:** Keep the existing scheduler and actor classes. Add deterministic evidence classification inside `src/agent/living_world_runtime.py`, keep routine signals as ambient scores, gate phase progression on meaningful evidence metadata, and update `src/agent/timeline_export.py` wording.

**Tech Stack:** Python, unittest/pytest, SQLite-backed runtime, existing `LivingWorldScheduler`, `ArcDirectorActor`, and Markdown timeline export.

---

### Task 1: Arc Evidence Classification

**Files:**
- Modify: `tests/test_living_world_runtime.py`
- Modify: `src/agent/living_world_runtime.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting routine events populate `ambient_scores` but not `scores`, repeated same-bucket events do not resolve, and explicit resolution triggers can resolve.

- [ ] **Step 2: Run focused tests and watch them fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest -q`

Expected: failures showing current ArcDirector counts routine signals as evidence and resolves by cumulative total alone.

- [ ] **Step 3: Implement classification and gates**

Add helpers for score maps, event classification, cumulative metadata, evidence diversity, resolution triggers, and phase gating.

- [ ] **Step 4: Run focused tests and watch them pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest -q`

Expected: pass.

### Task 2: Timeline Reporting

**Files:**
- Modify: `tests/test_living_world_runtime.py`
- Modify: `src/agent/timeline_export.py`

- [ ] **Step 1: Write failing export tests**

Add tests asserting Markdown renders `Autonomous NPC ticks: none` for empty `npc_ticks` and separates ambient routine signals from meaningful arc evidence.

- [ ] **Step 2: Run focused export tests and watch them fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest::test_timeline_export_renders_dialogue_and_arc_evidence tests\test_living_world_runtime.py::ActorAdapterTest::test_timeline_export_renders_ambient_vs_evidence_scores -q`

Expected: failures showing the current exporter omits no-tick wording and ambient scores.

- [ ] **Step 3: Implement report wording**

Render direct dialogue as direct dialogue, autonomous NPC tick status for every round, meaningful evidence scores, and ambient scores when present.

- [ ] **Step 4: Run focused export tests and watch them pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest::test_timeline_export_renders_dialogue_and_arc_evidence tests\test_living_world_runtime.py::ActorAdapterTest::test_timeline_export_renders_ambient_vs_evidence_scores -q`

Expected: pass.

### Task 3: Integration Verification

**Files:**
- Verify: `tests/test_living_world_runtime.py`
- Verify: `tests/test_traveler_tick.py`
- Verify: full test suite

- [ ] **Step 1: Run runtime and traveler tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py tests\test_traveler_tick.py -q`

Expected: pass.

- [ ] **Step 2: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: pass, or report exact unrelated pre-existing failures if present.
