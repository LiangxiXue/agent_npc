# Arc Evidence and NPC Tick Reporting Design

## Goal

Make Living World chapter progression evidence-driven enough for acceptance runs, while keeping the timeline report honest about which agent behaviors actually happened.

The immediate problem is that the current run can resolve the arc too quickly because routine background events carry `arc_signal` and are counted like meaningful evidence. The report also shows direct Traveler-to-NPC dialogue, but it does not make clear when no independent NPC autonomous ticks ran.

This design intentionally does not add an `--arc-pace classroom|full` mode. The fix should improve the default runtime semantics instead of adding a demo-specific switch.

## Non-Goals

- Do not add a new script pacing option.
- Do not remove NPC routines from the world. Routines still provide ambience and can still feed NPC inboxes.
- Do not replace `LivingWorldScheduler`, `TravelerActor`, `NpcActorAdapter`, or `ArcDirectorActor`.
- Do not let the LLM decide canonical arc outcomes directly.
- Do not make repeated conversations impossible. Existing exploration routing can continue to de-prioritize low-information repetition.

## Current Root Cause

`LivingWorldScheduler` creates `npc_routine_activity` events every round. Those events include `payload.arc_signal` derived from the NPC identity. `ArcDirectorActor` then counts every event payload with an `arc_signal`, merges that into cumulative scores, and advances phase by cumulative signal thresholds.

That makes background noise equivalent to concrete evidence:

- Round routine activity adds guardian, research, and sable signals even if the Traveler did not discover anything.
- Traveler movement adds another signal based on location.
- The cumulative threshold can reach `resolved` in only a few rounds.
- The final outcome becomes the largest signal bucket, not necessarily the best-supported story conclusion.

Separately, direct social actions can generate `dialogue_exchange` by routing the Traveler utterance through the target NPC response path. That is useful, but it is not the same thing as an independent scheduler-driven NPC tick. If `npc_ticks` is empty, the Markdown should say so.

## Proposed Design

### 1. Split Arc Signals by Evidence Class

Keep `arc_signal` as the faction or route bucket:

- `guardian`
- `research`
- `sable`
- `chaos`

Add or infer an evidence class for scoring:

- `routine`: background NPC routine or idle probe.
- `traveler_action`: Traveler move, investigate, social action, trade, challenge, share, help request.
- `dialogue_response`: direct NPC reply produced during a Traveler social action.
- `autonomous_npc_action`: scheduler-driven NPC tick with an allowed action.
- `resolution_trigger`: decisive evidence submission, secret disclosure, lockdown escalation, explicit contradiction, or other high-impact event.

The implementation can start with a helper in `living_world_runtime.py`, for example `classify_arc_evidence(event, source)`, rather than changing the database schema immediately. Schema changes are only needed if later reports must query evidence classes from persisted world events.

### 2. Score Routine Events Separately

Routine events should remain visible but should not directly advance the arc phase by default.

Recommended scoring:

- `routine`: counted under `ambient_scores`, not `scores`.
- `npc_idle_routine_probe`: counted under `ambient_scores`, not `scores`.
- `traveler_action`: counts as evidence.
- `dialogue_response`: counts only if the NPC action result produced a validated state change, memory write, quest signal, relationship shift above threshold, or explicit refusal/withholding of sensitive information.
- `autonomous_npc_action`: counts if validation status is allowed and outcome is not no-op.
- `resolution_trigger`: counts and can satisfy final resolution requirements.

The round update should expose both:

- `scores`: meaningful evidence used for phase progression.
- `ambient_scores`: routine/background signals not used for phase progression.

Markdown should render both, so users can see that routines happened without mistaking them for evidence.

### 3. Replace Total-Signal Phase Gates with Evidence Gates

Phase progression should be based on evidence quality and diversity, not only total count.

Recommended gates:

- `rumor -> evidence_gathering`: at least 1 meaningful Traveler action or autonomous NPC action.
- `evidence_gathering -> npc_conflict`: at least 2 meaningful evidence events across at least 2 different route buckets or source types.
- `npc_conflict -> resolved`: at least 1 resolution trigger, or at least 3 meaningful evidence events across at least 2 route buckets with one autonomous NPC action or direct dialogue response that produced validated consequences.

The existing score buckets can still determine the winning outcome after the final gate is satisfied. This preserves the current `guardian_advantage`, `research_advantage`, `sable_advantage`, and `chaotic_lockdown` model.

### 4. Make Direct Dialogue and Autonomous NPC Tick Explicit in Reports

Timeline export should label three different behaviors:

- `Traveler action`: the Traveler selected and executed an action.
- `Direct dialogue`: the target NPC replied immediately to a Traveler utterance.
- `Autonomous NPC ticks`: scheduler-driven NPC ticks after Traveler action.

If a round has no independent NPC ticks, render a concise line:

`- **Autonomous NPC ticks**: none`

If a round has NPC ticks, keep the existing per-NPC lines but make validation visible:

`- **Autonomous NPC ron**: patrol_sensitive_route (outcome=allowed)`

This avoids overselling the trace. A report can still say the system supports multiple actor types, but the timeline should distinguish support from actual execution in the run.

### 5. Keep NPC Scheduling but Improve Acceptance Visibility

The scheduler already has `max_npc_ticks_per_round` and idle probes. The design does not require a new CLI flag. For acceptance-quality runs, the existing runner can be invoked with enough NPC tick budget and idle probe settings.

The code change should make reports clearer even when `max_npc_ticks_per_round=0`:

- Direct dialogue remains visible.
- Autonomous NPC ticks are explicitly listed as none.
- Arc evidence excludes ambient routine noise.
- Final outcome does not appear unless meaningful evidence gates are met.

## Data Flow

1. Scheduler creates ambient routine events.
2. Traveler observes world state and executes one action.
3. Direct social actions may generate a `dialogue_exchange`.
4. Scheduler runs eligible autonomous NPC ticks.
5. ArcDirector classifies all round events into meaningful evidence and ambient signals.
6. ArcDirector updates cumulative evidence metadata and applies phase gates.
7. Timeline export renders Traveler action, direct dialogue, autonomous NPC ticks, meaningful scores, ambient scores, and final outcome.

## Arc Metadata Shape

The world arc metadata should remain JSON-compatible. A target shape:

```json
{
  "cumulative_scores": {
    "guardian": 2,
    "research": 1,
    "sable": 1,
    "chaos": 0
  },
  "cumulative_ambient_scores": {
    "guardian": 6,
    "research": 3,
    "sable": 3,
    "chaos": 0
  },
  "evidence_counts": {
    "traveler_action": 2,
    "dialogue_response": 1,
    "autonomous_npc_action": 0,
    "resolution_trigger": 0
  },
  "evidence_route_buckets": ["guardian", "sable"],
  "last_round_scores": {
    "guardian": 1,
    "research": 0,
    "sable": 1,
    "chaos": 0
  },
  "last_round_ambient_scores": {
    "guardian": 2,
    "research": 1,
    "sable": 1,
    "chaos": 0
  }
}
```

The exact field names can change during implementation, but reports and tests should verify the distinction between meaningful and ambient evidence.

## Test Plan

Add or update focused tests before implementation:

1. `test_arc_director_ignores_routine_noise_for_phase_progression`
   - Feed several rounds of only `npc_routine_activity`.
   - Assert the arc does not reach `resolved`.

2. `test_arc_director_tracks_ambient_scores_without_using_them_as_evidence`
   - Feed routine events with `arc_signal`.
   - Assert `ambient_scores` increments and `scores` remains zero or excludes routines.

3. `test_arc_director_requires_diverse_meaningful_evidence_for_conflict`
   - Feed repeated same-bucket Traveler movement.
   - Assert the arc does not jump straight to `npc_conflict` or `resolved`.

4. `test_arc_director_resolves_after_valid_resolution_trigger`
   - Feed sufficient meaningful evidence plus a trigger event.
   - Assert resolved phase and expected advantage.

5. `test_timeline_export_labels_no_autonomous_npc_ticks`
   - Export a round with direct dialogue and empty `npc_ticks`.
   - Assert Markdown contains direct dialogue and `Autonomous NPC ticks: none`.

6. `test_timeline_export_renders_ambient_vs_evidence_scores`
   - Export a round with both score maps.
   - Assert Markdown distinguishes meaningful arc evidence from ambient routine signals.

7. `test_scheduler_acceptance_run_does_not_resolve_from_background_only`
   - Run scheduler with routines enabled and a low-information Traveler sequence.
   - Assert final outcome remains empty unless evidence gates are met.

## Acceptance Criteria

- Routine-only rounds cannot resolve the arc.
- Background routines still exist and still appear in trace context.
- Markdown explicitly distinguishes direct dialogue from autonomous NPC ticks.
- Markdown says when there are no autonomous NPC ticks.
- Arc evidence includes meaningful scores and ambient scores separately.
- Existing outcomes remain unchanged once a valid resolution gate is satisfied.
- Existing direct dialogue trace behavior remains intact.
- Existing tests for timing, dialogue export, and Traveler event payload preservation continue to pass.

## Risks

- If gates are too strict, acceptance runs may never resolve. Mitigation: use targeted tests with a known valid evidence sequence.
- If direct dialogue is always counted as evidence, the system may still resolve too quickly. Mitigation: count only validated or consequential dialogue responses.
- If routine events are fully discarded, NPC inbox behavior may weaken. Mitigation: do not remove routine events, only exclude them from phase progression evidence.
- If report wording is too verbose, classroom traces become harder to read. Mitigation: use short labels and keep detailed evidence in JSON.

## Implementation Boundary

This design should be implemented as a small runtime semantics change:

- Arc classification and phase gates in `src/agent/living_world_runtime.py`.
- Outcome selection remains in `src/agent/world_arc.py`.
- Report wording in `src/agent/timeline_export.py`.
- Focused tests in `tests/test_living_world_runtime.py`.

No runner option is required.
