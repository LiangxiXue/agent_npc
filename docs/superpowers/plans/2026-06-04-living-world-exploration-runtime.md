# Living World Exploration Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Traveler-led smoke-test simulation into an explainable autonomous exploration runtime that can diversify investigation, activate NPCs, and reach a real arc outcome without hard-blocking legitimate repeated conversations.

**Architecture:** Keep the existing `LivingWorldScheduler`, `TravelerActor`, `NpcActorAdapter`, and `ArcDirectorActor` boundaries. Add small deterministic planning helpers around Traveler decision input, NPC action fallback, event scoring, and trace export rather than replacing the runtime loop.

**Tech Stack:** Python 3.11, SQLite storage helpers in `src/storage/database.py`, pytest, existing Traveler/NPC agent modules under `src/agent/`.

---

## Current Root Causes

The current run gets stuck for five separate reasons:

1. `ArcDirectorActor` only scores the current round. It does not accumulate evidence across rounds, and `npc_conflict -> resolved` needs `total_signals >= 8`, which recent runs never reach.
2. Traveler-created events lose `payload.arc_signal` when converted for the round log, so Traveler investigations and conversations often do not contribute to arc scoring.
3. NPC tick output is mostly invalid or no-op. Many LLM decisions produce no valid `selected_action`, and the adapter collapses those into `skip`.
4. NPC scheduling only ticks NPCs with unseen inbox items, and location visibility means some NPCs, especially Sable, may never get a turn.
5. Traveler keeps talking to Mira because the decision layer has no conversation thread state, no lead graph, and no information-gain scoring. A hard repeated-dialogue cooldown would damage legitimate follow-up conversations, so this plan uses soft information-gain routing instead.

## File Structure

- Modify: `src/agent/living_world_runtime.py`
  - Preserve round/Traveler timing fields.
  - Preserve event payloads for arc scoring.
  - Accumulate arc progress.
  - Add fair NPC scheduling hooks.
- Modify: `src/agent/traveler_tick.py`
  - Preserve internal Traveler timings.
  - Add exploration context to the Traveler decision payload.
  - Preserve event payload summaries.
- Modify: `src/agent/traveler_decision.py`
  - Pass exploration context to the LLM.
  - Use information-gain-aware deterministic fallback.
- Modify: `src/agent/traveler_actions.py`
  - Keep available action generation as the source of action legality.
  - Add helper-safe argument options for lead-driven moves and targets.
- Create: `src/agent/exploration_planner.py`
  - Build conversation thread state, lead candidates, and information-gain scores from current observation and recent Traveler tick logs.
- Modify: `src/agent/autonomous_tick.py`
  - Add valid deterministic NPC fallback when LLM output is empty or malformed.
  - Correct Mira action intent mapping so safe proactive/research actions do not require invalid quest transitions.
- Modify: `src/agent/timeline_export.py`
  - Render suppressed/re-ranked Traveler choices, lead state, arc progress, and NPC skip reasons.
- Modify: `scripts/run_traveler_world_demo.py`
  - Add demo controls for round limit, target outcome, NPC tick budget, and mock/LLM mode diagnostics.
- Test: `tests/test_living_world_runtime.py`
- Test: `tests/test_traveler_tick.py`
- Test: `tests/test_traveler_decision.py`
- Test: `tests/test_autonomous_tick.py`
- Create: `tests/test_exploration_planner.py`

---

### Task 1: Protect Existing Timing Instrumentation

**Files:**
- Modify: `tests/test_traveler_tick.py`
- Modify: `tests/test_living_world_runtime.py`
- Verify: `src/agent/traveler_tick.py`
- Verify: `src/agent/living_world_runtime.py`
- Verify: `src/agent/timeline_export.py`
- Verify: `src/storage/database.py`
- Verify: `src/storage/schema.sql`

- [ ] **Step 1: Write or preserve timing tests**

Keep tests asserting these fields exist:

```python
def test_traveler_tick_records_internal_timings(self) -> None:
    result = run_traveler_tick(
        traveler_id=self.traveler_id,
        round_number=1,
        profile=self.profile,
        world_state=self._world_state(),
        use_llm=False,
    )

    expected_keys = {
        "observe_ms",
        "retrieve_memory_ms",
        "build_action_surface_ms",
        "decide_ms",
        "validate_ms",
        "act_ms",
        "reflect_ms",
        "trace_log_ms",
        "total_ms",
    }
    self.assertTrue(expected_keys.issubset(result.timings))
    self.assertEqual(database.get_traveler_tick_log(result.tick_log_id)["timings"], result.timings)
```

- [ ] **Step 2: Run focused timing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_traveler_tick.py tests\test_living_world_runtime.py
```

Expected: all tests pass.

- [ ] **Step 3: Confirm timing fields stay in exports**

Run a one-round mock demo:

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 1 --mock --export-dir data/traces/timing_probe
```

Expected: exported JSON contains `rounds[0].timings` and `rounds[0].traveler_tick.timings`; exported Markdown contains `Timing` and `Traveler internals`.

- [ ] **Step 4: Commit timing baseline**

```powershell
git add src/agent/traveler_tick.py src/agent/living_world_runtime.py src/agent/timeline_export.py src/storage/database.py src/storage/schema.sql tests/test_traveler_tick.py tests/test_living_world_runtime.py
git commit -m "feat: record living world timing breakdowns"
```

---

### Task 2: Preserve Traveler Event Payloads for Arc Scoring

**Files:**
- Modify: `src/agent/traveler_tick.py`
- Modify: `src/agent/living_world_runtime.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing test for payload preservation**

Add to `tests/test_living_world_runtime.py`:

```python
def test_traveler_events_preserve_arc_signal_for_scheduler_scoring(self) -> None:
    database.reset_database()
    profile = load_profile("truth_seeking_scholar")
    traveler = TravelerActor("payload_arc", profile, use_llm=False)
    traveler.initialize()

    scheduler = LivingWorldScheduler(
        traveler=traveler,
        npc_adapters={},
        arc_director=ArcDirectorActor(),
        max_npc_ticks_per_round=0,
        npc_routines_every_round=False,
    )

    result = scheduler.run(rounds=1)
    created_events = result["rounds"][0]["traveler_tick"]["created_events"]

    self.assertTrue(created_events)
    self.assertIn("payload", created_events[0])
    self.assertIn("arc_signal", created_events[0]["payload"])
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_traveler_events_preserve_arc_signal_for_scheduler_scoring -v
```

Expected before implementation: FAIL because event summaries omit `payload`.

- [ ] **Step 3: Preserve payload in Traveler event summaries**

Update `_event_summary` in `src/agent/traveler_tick.py`:

```python
def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return {
        "id": event.get("id"),
        "event_type": event.get("event_type"),
        "content": event.get("content"),
        "source_type": event.get("source_type"),
        "source_id": event.get("source_id"),
        "location_id": event.get("location_id"),
        "visibility": event.get("visibility"),
        "payload": dict(payload),
    }
```

- [ ] **Step 4: Ensure scheduler uses preserved payload**

In `src/agent/living_world_runtime.py`, keep:

```python
all_events = ambient_events + traveler_result.get("created_events", [])
```

No conversion should strip `payload` before `ArcDirectorActor.tick(...)`.

- [ ] **Step 5: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_traveler_events_preserve_arc_signal_for_scheduler_scoring -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/agent/traveler_tick.py src/agent/living_world_runtime.py tests/test_living_world_runtime.py
git commit -m "fix: preserve traveler event payloads in living world traces"
```

---

### Task 3: Make Arc Progress Accumulative and Reachable

**Files:**
- Modify: `src/agent/living_world_runtime.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing test for accumulated arc progress**

Add:

```python
def test_arc_director_accumulates_scores_across_rounds_until_resolved(self) -> None:
    database.reset_database()
    director = ArcDirectorActor()
    world_state = {"round_number": 1}

    event = {"payload": {"arc_signal": "research"}}

    first = director.tick(world_state, [event, event], [])
    second = director.tick({"round_number": 2}, [event, event, event], [])
    third = director.tick({"round_number": 3}, [event, event, event], [])

    self.assertEqual(first["phase"], "evidence_gathering")
    self.assertEqual(second["phase"], "npc_conflict")
    self.assertEqual(third["phase"], "resolved")
    self.assertNotEqual(third["outcome"], "")
    self.assertGreaterEqual(third["cumulative_total_signals"], 8)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest::test_arc_director_accumulates_scores_across_rounds_until_resolved -v
```

Expected before implementation: FAIL because scores are current-round only and `cumulative_total_signals` does not exist.

- [ ] **Step 3: Store cumulative arc signal counts in arc metadata**

Add helper functions to `src/agent/living_world_runtime.py`:

```python
def _merge_arc_scores(existing: dict[str, Any], current: dict[str, int]) -> dict[str, int]:
    cumulative = {
        "guardian": int(existing.get("guardian", 0)),
        "research": int(existing.get("research", 0)),
        "sable": int(existing.get("sable", 0)),
        "chaos": int(existing.get("chaos", 0)),
    }
    for key, value in current.items():
        cumulative[key] = cumulative.get(key, 0) + int(value)
    return cumulative
```

In `ArcDirectorActor.tick`, load metadata:

```python
metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
current_round_scores = _collect_scores_from_events((all_events or []) + _extract_npc_events(npc_ticks or []))
cumulative_scores = _merge_arc_scores(metadata.get("cumulative_scores", {}), current_round_scores)
cumulative_total_signals = sum(cumulative_scores.values())
```

- [ ] **Step 4: Use cumulative scores for phase thresholds**

Replace `total_signals` threshold decisions with `cumulative_total_signals`:

```python
new_phase = phase
if phase == "rumor" and cumulative_total_signals >= 2:
    new_phase = "evidence_gathering"
elif phase == "evidence_gathering" and cumulative_total_signals >= 5:
    new_phase = "npc_conflict"
elif phase == "npc_conflict" and cumulative_total_signals >= 8:
    new_phase = "resolved"
```

- [ ] **Step 5: Persist cumulative metadata every tick**

When calling `database.update_world_arc_state`, pass metadata preserving the title:

```python
metadata = {
    **metadata,
    "cumulative_scores": cumulative_scores,
    "last_round_scores": current_round_scores,
    "last_round_total_signals": sum(current_round_scores.values()),
}
database.update_world_arc_state(
    arc_id=ARC_ID,
    phase=new_phase,
    tension=min(10, int(current["tension"]) + (1 if new_phase != phase else 0)),
    metadata=metadata,
)
```

If `database.update_world_arc_state` does not accept `metadata`, add that parameter with JSON serialization in `src/storage/database.py` and a focused storage test.

- [ ] **Step 6: Return current and cumulative scores in trace**

Return:

```python
return {
    "arc_id": ARC_ID,
    "phase": arc_state["phase"],
    "tension": arc_state["tension"],
    "advantage": arc_state.get("advantage", "none"),
    "outcome": arc_state.get("outcome", ""),
    "scores": current_round_scores,
    "total_signals": sum(current_round_scores.values()),
    "cumulative_scores": cumulative_scores,
    "cumulative_total_signals": cumulative_total_signals,
}
```

- [ ] **Step 7: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::ActorAdapterTest::test_arc_director_accumulates_scores_across_rounds_until_resolved -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/agent/living_world_runtime.py src/storage/database.py tests/test_living_world_runtime.py
git commit -m "feat: accumulate living world arc progress"
```

---

### Task 4: Add Exploration Planner Without Hard Dialogue Cooldowns

**Files:**
- Create: `src/agent/exploration_planner.py`
- Modify: `src/agent/traveler_tick.py`
- Modify: `src/agent/traveler_decision.py`
- Test: `tests/test_exploration_planner.py`
- Test: `tests/test_traveler_decision.py`

- [ ] **Step 1: Write failing tests for thread state and information gain**

Create `tests/test_exploration_planner.py`:

```python
import unittest

from src.agent.exploration_planner import build_exploration_context


class ExplorationPlannerTest(unittest.TestCase):
    def test_repeated_same_topic_without_new_evidence_has_low_information_gain(self) -> None:
        observation = {
            "traveler_state": {"current_location": "archive", "private_notes": []},
            "recent_events": [
                {
                    "event_type": "traveler_talked_to_npc",
                    "payload": {"npc_id": "mira", "topic": "safe ruins exploration"},
                },
                {
                    "event_type": "traveler_talked_to_npc",
                    "payload": {"npc_id": "mira", "topic": "safe ruins exploration"},
                },
            ],
            "arc_state": {"phase": "npc_conflict"},
        }
        available_actions = [
            {"action_type": "talk_to", "arg_options": {"npc_id": ["mira"]}},
            {"action_type": "move_to", "arg_options": {"location_id": ["guard_post"]}},
        ]

        context = build_exploration_context("traveler_main", observation, available_actions)

        self.assertEqual(context["conversation_threads"][0]["status"], "waiting_for_external_evidence")
        self.assertGreater(
            context["action_scores"]["move_to:guard_post"]["information_gain"],
            context["action_scores"]["talk_to:mira"]["information_gain"],
        )

    def test_repeated_same_npc_with_new_evidence_stays_high_value(self) -> None:
        observation = {
            "traveler_state": {"current_location": "archive", "private_notes": []},
            "recent_events": [
                {
                    "event_type": "traveler_investigated",
                    "payload": {"target_id": "mira_field_notes", "method": "careful observation"},
                }
            ],
            "arc_state": {"phase": "evidence_gathering"},
        }
        available_actions = [
            {"action_type": "talk_to", "arg_options": {"npc_id": ["mira"]}},
            {"action_type": "move_to", "arg_options": {"location_id": ["guard_post"]}},
        ]

        context = build_exploration_context("traveler_main", observation, available_actions)

        self.assertEqual(context["conversation_threads"][0]["status"], "open_with_new_evidence")
        self.assertGreaterEqual(
            context["action_scores"]["talk_to:mira"]["information_gain"],
            context["action_scores"]["move_to:guard_post"]["information_gain"],
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_exploration_planner.py -v
```

Expected before implementation: FAIL because module does not exist.

- [ ] **Step 3: Implement `src/agent/exploration_planner.py`**

Create:

```python
"""Exploration planner helpers for Traveler action selection."""

from __future__ import annotations

from typing import Any


def build_exploration_context(
    traveler_id: str,
    observation: dict[str, Any],
    available_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    recent_events = observation.get("recent_events", [])
    threads = _conversation_threads(recent_events)
    leads = _lead_candidates(observation, threads)
    action_scores = _score_actions(available_actions, threads, leads)
    return {
        "traveler_id": traveler_id,
        "conversation_threads": threads,
        "leads": leads,
        "action_scores": action_scores,
        "selection_policy": (
            "Prefer the highest information-gain action. Repeating an NPC is allowed when there is "
            "new evidence, a pending request, or a direct NPC message. Repeating the same NPC and topic "
            "without new evidence is lower priority, not forbidden."
        ),
    }


def _conversation_threads(recent_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last_talk = None
    new_evidence_after_talk = False
    repeated_count = 0
    for event in recent_events:
        event_type = str(event.get("event_type", ""))
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "traveler_talked_to_npc":
            npc_id = str(payload.get("npc_id", ""))
            topic = str(payload.get("topic", ""))
            if last_talk and last_talk["npc_id"] == npc_id and last_talk["topic"] == topic:
                repeated_count += 1
            else:
                repeated_count = 1
            last_talk = {"npc_id": npc_id, "topic": topic}
            new_evidence_after_talk = False
        elif event_type in {"traveler_investigated", "player_investigated_scene", "player_submitted_evidence"}:
            new_evidence_after_talk = True
    if not last_talk:
        return []
    status = "open"
    if repeated_count >= 2 and not new_evidence_after_talk:
        status = "waiting_for_external_evidence"
    if new_evidence_after_talk:
        status = "open_with_new_evidence"
    return [
        {
            "npc_id": last_talk["npc_id"],
            "topic": last_talk["topic"],
            "status": status,
            "repeat_count": repeated_count,
        }
    ]


def _lead_candidates(observation: dict[str, Any], threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phase = str(observation.get("arc_state", {}).get("phase", "rumor"))
    current_location = str(observation.get("traveler_state", {}).get("current_location", ""))
    leads: list[dict[str, Any]] = []
    if any(thread["status"] == "waiting_for_external_evidence" for thread in threads):
        if current_location != "guard_post":
            leads.append({"lead_id": "ask_ron_about_guard_ledger", "action_type": "move_to", "target": "guard_post"})
        if current_location != "market":
            leads.append({"lead_id": "question_sable_about_rumors", "action_type": "move_to", "target": "market"})
    if phase in {"evidence_gathering", "npc_conflict"} and current_location != "tavern":
        leads.append({"lead_id": "inspect_tavern_back_alley", "action_type": "move_to", "target": "tavern"})
    return leads


def _score_actions(
    available_actions: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    blocked_npcs = {
        thread["npc_id"]
        for thread in threads
        if thread["status"] == "waiting_for_external_evidence"
    }
    lead_targets = {str(lead["target"]) for lead in leads}
    for action in available_actions:
        action_type = str(action.get("action_type", ""))
        options = action.get("arg_options") if isinstance(action.get("arg_options"), dict) else {}
        if action_type in {"talk_to", "ask_for_help", "share_information"}:
            for npc_id in options.get("npc_id", []):
                key = f"{action_type}:{npc_id}"
                information_gain = 0.25 if str(npc_id) in blocked_npcs else 0.8
                scores[key] = {"information_gain": information_gain, "reason": "conversation thread state"}
        elif action_type == "move_to":
            for location_id in options.get("location_id", []):
                key = f"move_to:{location_id}"
                information_gain = 0.9 if str(location_id) in lead_targets else 0.55
                scores[key] = {"information_gain": information_gain, "reason": "lead target" if information_gain == 0.9 else "general exploration"}
        else:
            scores[action_type] = {"information_gain": 0.5, "reason": "neutral action"}
    return scores
```

- [ ] **Step 4: Pass exploration context into Traveler decision**

In `src/agent/traveler_tick.py`, import and call:

```python
from src.agent.exploration_planner import build_exploration_context

exploration_context = build_exploration_context(traveler_id, observation, available_actions)
decision = decide_traveler_action(
    profile=profile,
    observation={**observation, "exploration_context": exploration_context},
    available_actions=available_actions,
    unavailable_actions=unavailable_actions,
    use_llm=use_llm,
    allow_llm_fallback=allow_llm_fallback,
)
```

Add `exploration_context` to the returned tick result or `reflection` so it is visible in trace:

```python
reflection = _build_reflection(traveler_id, decision, action_result)
reflection["exploration_context"] = exploration_context
```

- [ ] **Step 5: Make deterministic fallback information-gain aware**

In `src/agent/traveler_decision.py`, inside `deterministic_fallback_decision`, accept an optional `exploration_context` or read it from observation via a new parameter. Use this ordering:

```python
def _information_gain_for_action(action: dict[str, Any], exploration_context: dict[str, Any] | None) -> float:
    if not exploration_context:
        return 0.5
    action_type = str(action.get("action_type", ""))
    options = action.get("arg_options") if isinstance(action.get("arg_options"), dict) else {}
    keys = [action_type]
    if action_type == "move_to":
        keys.extend(f"move_to:{item}" for item in options.get("location_id", []))
    if action_type in {"talk_to", "ask_for_help", "share_information"}:
        keys.extend(f"{action_type}:{item}" for item in options.get("npc_id", []))
    scores = exploration_context.get("action_scores", {})
    return max(float(scores.get(key, {}).get("information_gain", 0.5)) for key in keys)
```

- [ ] **Step 6: Run planner and Traveler tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_exploration_planner.py tests\test_traveler_decision.py tests\test_traveler_tick.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/agent/exploration_planner.py src/agent/traveler_tick.py src/agent/traveler_decision.py tests/test_exploration_planner.py tests/test_traveler_decision.py tests/test_traveler_tick.py
git commit -m "feat: add traveler exploration planning context"
```

---

### Task 5: Generate and Follow Leads Across NPCs and Locations

**Files:**
- Modify: `src/agent/exploration_planner.py`
- Modify: `src/agent/traveler_decision.py`
- Test: `tests/test_exploration_planner.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing test for cross-NPC routing**

Add:

```python
def test_repeated_mira_thread_routes_to_ron_or_sable_lead(self) -> None:
    observation = {
        "traveler_state": {"current_location": "archive", "private_notes": []},
        "recent_events": [
            {"event_type": "traveler_talked_to_npc", "payload": {"npc_id": "mira", "topic": "ruins"}},
            {"event_type": "traveler_talked_to_npc", "payload": {"npc_id": "mira", "topic": "ruins"}},
        ],
        "arc_state": {"phase": "npc_conflict"},
    }
    available_actions = [
        {"action_type": "move_to", "arg_options": {"location_id": ["guard_post", "market", "tavern"]}},
        {"action_type": "talk_to", "arg_options": {"npc_id": ["mira"]}},
    ]

    context = build_exploration_context("traveler_main", observation, available_actions)
    lead_ids = {lead["lead_id"] for lead in context["leads"]}

    self.assertIn("ask_ron_about_guard_ledger", lead_ids)
    self.assertIn("question_sable_about_rumors", lead_ids)
```

- [ ] **Step 2: Add lead types**

In `src/agent/exploration_planner.py`, ensure `_lead_candidates` can emit:

```python
{
    "lead_id": "ask_ron_about_guard_ledger",
    "action_type": "move_to",
    "target": "guard_post",
    "reason": "Mira thread needs external procedural evidence.",
}
```

```python
{
    "lead_id": "question_sable_about_rumors",
    "action_type": "move_to",
    "target": "market",
    "reason": "Ruins rumors need adversarial cross-checking.",
}
```

```python
{
    "lead_id": "inspect_tavern_back_alley",
    "action_type": "move_to",
    "target": "tavern",
    "reason": "Guardian route needs physical evidence.",
}
```

```python
{
    "lead_id": "return_to_mira_with_field_notes",
    "action_type": "move_to",
    "target": "archive",
    "reason": "New field evidence should be interpreted by Mira.",
}
```

- [ ] **Step 3: Add lead-aware fallback args**

In `src/agent/traveler_decision.py`, when fallback chooses `move_to`, use the highest information-gain location from `exploration_context["action_scores"]`:

```python
def _best_option_for_action(action: dict[str, Any], field: str, exploration_context: dict[str, Any] | None) -> str | None:
    options = action.get("arg_options") if isinstance(action.get("arg_options"), dict) else {}
    values = [str(item) for item in options.get(field, []) if str(item)]
    if not values:
        return None
    scores = exploration_context.get("action_scores", {}) if exploration_context else {}
    action_type = str(action.get("action_type", ""))
    return max(
        values,
        key=lambda value: float(scores.get(f"{action_type}:{value}", {}).get("information_gain", 0.0)),
    )
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_exploration_planner.py tests\test_traveler_decision.py -v
```

Expected: PASS.

- [ ] **Step 5: Run a mock simulation and inspect behavior**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 12 --mock --export-dir data/traces/exploration_probe
```

Expected: after repeated Mira interaction without new evidence, Traveler should move to at least one of `guard_post`, `market`, or `tavern`.

- [ ] **Step 6: Commit**

```powershell
git add src/agent/exploration_planner.py src/agent/traveler_decision.py tests/test_exploration_planner.py tests/test_traveler_decision.py
git commit -m "feat: route traveler exploration through leads"
```

---

### Task 6: Make NPC Tick Fallback Produce Valid Actions

**Files:**
- Modify: `src/agent/autonomous_tick.py`
- Test: `tests/test_autonomous_tick.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing test for invalid empty NPC decision**

Add to `tests/test_autonomous_tick.py`:

```python
def test_empty_autonomous_llm_decision_falls_back_to_valid_available_action(self) -> None:
    database.reset_database()
    event = database.create_world_event(
        event_type="traveler_talked_to_npc",
        content="Traveler asked Mira about ruins.",
        source_type="traveler",
        source_id="traveler_main",
        location_id="archive",
        visibility="location",
        payload={"arc_id": "ruins_chapter_1", "arc_signal": "research"},
    )
    database.add_npc_event_inbox_item("mira", int(event["id"]), relevance_score=1.0, reason="explicit_target")

    with patch("src.agent.autonomous_tick.call_openai_compatible_json", return_value={}):
        result = run_autonomous_tick("mira", mode="llm_constrained", run_director=False)

    self.assertNotEqual(result.proposed_action.get("action_type"), "")
    self.assertNotEqual(result.validation["status"], "rejected_by_available_actions")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_tick.py::AutonomousTickTest::test_empty_autonomous_llm_decision_falls_back_to_valid_available_action -v
```

Expected before implementation: FAIL because empty result produces rejected action.

- [ ] **Step 3: Add post-normalization fallback**

In `src/agent/autonomous_tick.py`, after:

```python
proposed_action = normalize_selected_action(llm_decision.get("selected_action"))
```

Add:

```python
if not proposed_action.get("action_type") and available_actions:
    llm_decision = deterministic_fallback_decision(
        available_actions,
        trigger_event,
        "LLM returned no valid selected_action.",
    )
    proposed_action = normalize_selected_action(llm_decision.get("selected_action"))
```

- [ ] **Step 4: Keep trace honest**

Ensure fallback reason remains in `llm_decision["fallback_reason"]`, `reflection.summary`, or `reflection.belief_update`.

- [ ] **Step 5: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_tick.py::AutonomousTickTest::test_empty_autonomous_llm_decision_falls_back_to_valid_available_action -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/agent/autonomous_tick.py tests/test_autonomous_tick.py
git commit -m "fix: fallback invalid autonomous npc decisions"
```

---

### Task 7: Correct NPC Action Intent Mapping

**Files:**
- Modify: `src/agent/autonomous_tick.py`
- Test: `tests/test_autonomous_tick.py`

- [ ] **Step 1: Write failing test for Mira suggest action**

Add:

```python
def test_mira_suggest_next_investigation_does_not_require_quest_start(self) -> None:
    database.reset_database()
    selected_action = {
        "action_type": "suggest_next_investigation",
        "args": {"message_intent": "Check the guard ledger before returning to the archive."},
    }
    decision = decision_from_selected_action(
        selected_action,
        {"reflection_summary": "Mira suggests a grounded next step."},
    )

    self.assertEqual(decision["intent"], "general_conversation")
    self.assertEqual(decision["tools"], [])
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_tick.py::AutonomousTickTest::test_mira_suggest_next_investigation_does_not_require_quest_start -v
```

Expected before implementation: FAIL because the action maps to `start_ancient_notes_quest`.

- [ ] **Step 3: Split Mira action intent mapping**

In `decision_from_selected_action`, replace the Mira branch with:

```python
elif action_type in {"request_field_notes"}:
    intent = "start_ancient_notes_quest"
    social_intent = "cooperate"
    tools = [{"name": "update_quest_status", "args": {"quest_id": "ancient_notes", "status": "in_progress"}}]
elif action_type in {"preserve_research_record", "inspect_clue", "connect_evidence", "archive_memory", "suggest_next_investigation"}:
    intent = "general_conversation"
    social_intent = "cooperate"
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_tick.py::AutonomousTickTest::test_mira_suggest_next_investigation_does_not_require_quest_start -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/agent/autonomous_tick.py tests/test_autonomous_tick.py
git commit -m "fix: map mira autonomous actions to safe intents"
```

---

### Task 8: Improve NPC Scheduling Coverage Without Forcing All NPCs Every Round

**Files:**
- Modify: `src/agent/living_world_runtime.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing test for scheduled coverage**

Add:

```python
def test_scheduler_can_add_low_priority_routine_ticks_for_idle_npcs(self) -> None:
    database.reset_database()
    profile = load_profile("truth_seeking_scholar")
    traveler = TravelerActor("coverage_traveler", profile, use_llm=False)
    traveler.initialize()

    scheduler = LivingWorldScheduler(
        traveler=traveler,
        npc_adapters={
            "lina": NpcActorAdapter("lina"),
            "ron": NpcActorAdapter("ron"),
            "mira": NpcActorAdapter("mira"),
            "sable": NpcActorAdapter("sable"),
        },
        arc_director=ArcDirectorActor(),
        max_npc_ticks_per_round=4,
        npc_routines_every_round=False,
        idle_npc_probe_enabled=True,
    )

    result = scheduler.run(rounds=1)
    ticked_npcs = {tick["npc_id"] for tick in result["rounds"][0]["npc_ticks"]}

    self.assertIn("sable", ticked_npcs)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_scheduler_can_add_low_priority_routine_ticks_for_idle_npcs -v
```

Expected before implementation: FAIL because constructor has no `idle_npc_probe_enabled` parameter and Sable has no inbox.

- [ ] **Step 3: Add scheduler option**

Update `LivingWorldScheduler.__init__`:

```python
def __init__(
    self,
    traveler: TravelerActor,
    npc_adapters: dict[str, NpcActorAdapter],
    arc_director: ArcDirectorActor,
    max_npc_ticks_per_round: int = 3,
    npc_routines_every_round: bool = True,
    npc_cooldown_enabled: bool = True,
    idle_npc_probe_enabled: bool = False,
):
    self.idle_npc_probe_enabled = idle_npc_probe_enabled
```

- [ ] **Step 4: Add low-priority synthetic routine event for idle NPCs**

In `_execute_npc_phase`, after inbox-priority NPCs are collected:

```python
if self.idle_npc_probe_enabled:
    for npc_id in self.npc_adapters:
        if npc_id in {item[1] for item in npcs_with_inbox}:
            continue
        event = database.create_world_event(
            event_type="npc_idle_routine_probe",
            content=f"{npc_id} considered routine activity while the traveler explored.",
            source_type="scheduler",
            source_id="living_world_scheduler",
            location_id=database.get_npc_location_state(npc_id)["location_id"],
            visibility="npc_only",
            payload={"target_npc_ids": [npc_id], "arc_id": ARC_ID, "arc_signal": arc_signal_for_npc(npc_id)},
        )
        inbox_item = database.add_npc_event_inbox_item(npc_id, int(event["id"]), relevance_score=0.2, reason="idle_probe")
        npcs_with_inbox.append((5, npc_id))
```

Ensure `arc_signal_for_npc` is imported from `src.agent.player_actions`.

- [ ] **Step 5: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_scheduler_can_add_low_priority_routine_ticks_for_idle_npcs -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/agent/living_world_runtime.py tests/test_living_world_runtime.py
git commit -m "feat: add optional idle npc scheduling probes"
```

---

### Task 9: Improve Trace and Markdown Explanation

**Files:**
- Modify: `src/agent/timeline_export.py`
- Modify: `src/agent/living_world_runtime.py`
- Modify: `src/agent/traveler_tick.py`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Write failing export test**

Add:

```python
def test_timeline_export_explains_exploration_routing_and_arc_progress(self) -> None:
    profile = load_profile("truth_seeking_scholar")
    result = {
        "rounds": [
            {
                "round_number": 1,
                "timings": {"total_ms": 1.0},
                "traveler_tick": {
                    "proposed_action": {"action_type": "move_to", "args": {"location_id": "guard_post"}},
                    "decision": {"decision_reason": "Follow higher information-gain lead."},
                    "reflection": {
                        "exploration_context": {
                            "leads": [{"lead_id": "ask_ron_about_guard_ledger", "reason": "Need external evidence."}],
                            "selection_policy": "Prefer the highest information-gain action.",
                        }
                    },
                    "relationship_changes": [],
                },
                "npc_ticks": [
                    {
                        "npc_id": "mira",
                        "outcome": "no_op",
                        "proposed_action": {"action_type": "suggest_next_investigation"},
                        "validation": {"status": "allowed"},
                    }
                ],
                "arc_update": {
                    "phase": "npc_conflict",
                    "tension": 2,
                    "outcome": "",
                    "cumulative_total_signals": 6,
                },
            }
        ],
        "final_arc_phase": "npc_conflict",
        "final_arc_outcome": "",
        "final_tension": 2,
        "final_traveler_location": "guard_post",
        "final_relationships": {},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        _, md_path = export_simulation_result(result, profile, tmpdir, run_id="trace-explain")
        markdown = md_path.read_text(encoding="utf-8")

    self.assertIn("Exploration leads", markdown)
    self.assertIn("ask_ron_about_guard_ledger", markdown)
    self.assertIn("cumulative signals=6", markdown)
    self.assertIn("NPC mira", markdown)
```

- [ ] **Step 2: Render exploration leads**

In `timeline_export.py`, after Traveler line:

```python
exploration_context = traveler.get("reflection", {}).get("exploration_context", {})
leads = exploration_context.get("leads", [])
if leads:
    lines.append("- **Exploration leads**:")
    for lead in leads:
        lines.append(f"  - `{lead.get('lead_id')}`: {lead.get('reason', '')}")
```

- [ ] **Step 3: Render cumulative arc progress**

Replace current Arc line with:

```python
if arc:
    cumulative = arc.get("cumulative_total_signals")
    cumulative_text = f", cumulative signals={cumulative}" if cumulative is not None else ""
    lines.append(
        f"- **Arc**: phase={arc.get('phase')}, tension={arc.get('tension')}, "
        f"outcome={arc.get('outcome', 'unresolved')}{cumulative_text}"
    )
```

- [ ] **Step 4: Render NPC validation reason**

For NPC ticks:

```python
validation = nt.get("validation", {})
reason = validation.get("reason", "")
suffix = f", reason={reason}" if reason else ""
lines.append(f"- **NPC {nt.get('npc_id', '?')}**: `{nt_action}` (outcome={nt.get('outcome', 'unknown')}{suffix})")
```

- [ ] **Step 5: Run export tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_timeline_export_explains_exploration_routing_and_arc_progress -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/agent/timeline_export.py tests/test_living_world_runtime.py
git commit -m "feat: explain exploration routing in timeline export"
```

---

### Task 10: Add Demo Controls and End-to-End Acceptance Run

**Files:**
- Modify: `scripts/run_traveler_world_demo.py`
- Modify: `docs/delivery/demo_script.md`
- Test: `tests/test_living_world_runtime.py`

- [ ] **Step 1: Add CLI options**

Modify `scripts/run_traveler_world_demo.py` parser:

```python
parser.add_argument("--max-npc-ticks", type=int, default=2, help="Maximum NPC ticks per round.")
parser.add_argument("--idle-npc-probe", action="store_true", help="Allow low-priority idle NPC routine probes.")
parser.add_argument("--stop-on-outcome", action="store_true", help="Stop early after the arc reaches a resolved outcome.")
```

- [ ] **Step 2: Wire options into scheduler**

```python
scheduler = LivingWorldScheduler(
    traveler=traveler,
    npc_adapters=npc_adapters,
    arc_director=director,
    max_npc_ticks_per_round=args.max_npc_ticks,
    npc_routines_every_round=True,
    idle_npc_probe_enabled=args.idle_npc_probe,
)
```

If `--stop-on-outcome` is selected, run one round at a time:

```python
if args.stop_on_outcome:
    result = scheduler.run_until_outcome(max_rounds=args.rounds)
else:
    result = scheduler.run(rounds=args.rounds)
```

Implement `run_until_outcome` in `LivingWorldScheduler`:

```python
def run_until_outcome(self, max_rounds: int) -> dict[str, Any]:
    run_started = perf_counter()
    for round_num in range(1, max_rounds + 1):
        round_data = self._execute_round(round_num)
        self.round_log.append(round_data)
        if round_data.get("arc_update", {}).get("outcome"):
            break
    result = self._build_final_result()
    result["timings"] = {"total_ms": _elapsed_ms(run_started)}
    return result
```

- [ ] **Step 3: Add acceptance test for outcome run**

Add:

```python
def test_scheduler_can_run_until_outcome(self) -> None:
    profile = load_profile("truth_seeking_scholar")
    traveler = TravelerActor("outcome_run", profile, use_llm=False)
    traveler.initialize()

    scheduler = LivingWorldScheduler(
        traveler=traveler,
        npc_adapters={
            "lina": NpcActorAdapter("lina"),
            "ron": NpcActorAdapter("ron"),
            "mira": NpcActorAdapter("mira"),
            "sable": NpcActorAdapter("sable"),
        },
        arc_director=ArcDirectorActor(),
        max_npc_ticks_per_round=4,
        npc_routines_every_round=True,
        idle_npc_probe_enabled=True,
    )

    result = scheduler.run_until_outcome(max_rounds=20)

    self.assertLessEqual(result["total_rounds"], 20)
    self.assertEqual(result["final_arc_phase"], "resolved")
    self.assertNotEqual(result["final_arc_outcome"], "")
```

- [ ] **Step 4: Run acceptance test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_living_world_runtime.py::SchedulerTest::test_scheduler_can_run_until_outcome -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass. If `data/agent_trace_export.json` changes only by generated timestamps, restore it from the worktree before commit.

- [ ] **Step 6: Run demo**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --mock --max-npc-ticks 4 --idle-npc-probe --stop-on-outcome --export-dir data/traces/living_world_acceptance
```

Expected:
- `Final Arc Phase: resolved`
- `Final Arc Outcome:` is non-empty
- Markdown timeline shows Traveler visiting at least two locations after archive
- Markdown timeline includes NPC validation reasons and exploration leads
- JSON includes round timings and Traveler internal timings

- [ ] **Step 7: Update demo script docs**

In `docs/delivery/demo_script.md`, add the acceptance command:

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --mock --max-npc-ticks 4 --idle-npc-probe --stop-on-outcome --export-dir data/traces/living_world_acceptance
```

- [ ] **Step 8: Commit**

```powershell
git add scripts/run_traveler_world_demo.py src/agent/living_world_runtime.py tests/test_living_world_runtime.py docs/delivery/demo_script.md
git commit -m "feat: add living world acceptance demo controls"
```

---

## Final Verification

- [ ] Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exploration_planner.py tests/test_traveler_tick.py tests/test_traveler_decision.py tests/test_autonomous_tick.py tests/test_living_world_runtime.py -v
```

- [ ] Run full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

- [ ] Run acceptance demo:

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --mock --max-npc-ticks 4 --idle-npc-probe --stop-on-outcome --export-dir data/traces/living_world_acceptance
```

- [ ] Inspect latest JSON:

```powershell
Get-ChildItem data\traces\living_world_acceptance -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

- [ ] Confirm outcome and route diversity:

```powershell
@'
import json
from pathlib import Path
path = sorted(Path("data/traces/living_world_acceptance").glob("*.json"), key=lambda p: p.stat().st_mtime)[-1]
data = json.loads(path.read_text(encoding="utf-8"))
locations = [rd["traveler_tick"]["observation"]["traveler_state"]["current_location"] for rd in data["rounds"]]
targets = [
    rd["traveler_tick"]["proposed_action"].get("args", {}).get("npc_id")
    for rd in data["rounds"]
    if rd["traveler_tick"]["proposed_action"].get("args", {}).get("npc_id")
]
print("phase", data["final_arc_phase"])
print("outcome", data["final_arc_outcome"])
print("locations", locations)
print("npc_targets", targets)
'@ | .\.venv\Scripts\python.exe -
```

Expected:
- `phase resolved`
- `outcome` is not blank
- `locations` includes more than `archive`
- `npc_targets` includes at least two NPC IDs across the run

- [ ] Check worktree:

```powershell
git status --short
```

Expected: only intended source/test/docs changes are present, or clean after commits.

---

## Execution Notes

- Do not use a hard repeated-dialogue cooldown. Use thread state and information gain so legitimate follow-up conversations remain possible.
- Keep LLM authority constrained. The LLM may choose actions and explain motives, but world facts, quest transitions, arc scoring, and location unlocks remain program-owned.
- Keep every new behavior trace-visible. A future reviewer should see why Traveler did not ask Mira again, why an NPC did or did not act, and why the arc reached an outcome.
- Preserve `.\.venv\Scripts\python.exe -m pytest` as the validation command for this repo.

