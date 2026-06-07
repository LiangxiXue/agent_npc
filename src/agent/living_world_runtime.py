"""Living World Runtime — unified ActorAgent protocol, adapters, and scheduler.

Implements the 4-phase round loop:
  Phase A: AMBIENT — NPC routines fire, generating ambient world events
  Phase B: TRAVELER — Traveler observes, decides, and acts
  Phase C: NPC — NPC autonomous ticks (inbox-driven, priority-sorted)
  Phase D: RESOLUTION — Arc director, major event detection, timeline export
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol

from src.agent.autonomous_tick import run_autonomous_tick
from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.agent.player_actions import arc_signal_for_npc
from src.agent.traveler_profile import TravelerProfile
from src.agent.traveler_state import TravelerRelationshipManager, TravelerStateManager
from src.agent.traveler_tick import TravelerTickResult, run_traveler_tick
from src.agent.world_arc import ARC_ID, ARC_OUTCOMES, apply_arc_outcome, resolve_arc_outcome
from src.storage import database


# ═══════════════════════════════════════════════════════════════════════
#  ActorAgent Protocol
# ═══════════════════════════════════════════════════════════════════════

class ActorAgent(Protocol):
    """Unified interface for Traveler, NPC, and ArcDirector actors."""

    actor_id: str
    actor_type: str  # "traveler" | "npc" | "director"

    def tick(self, world_state: dict[str, Any]) -> dict[str, Any]:
        """Execute one tick: observe → decide → act → reflect → trace."""
        ...


# ═══════════════════════════════════════════════════════════════════════
#  TravelerActor
# ═══════════════════════════════════════════════════════════════════════

class TravelerActor:
    """Actor wrapper around the Traveler tick loop."""

    actor_type = "traveler"

    def __init__(
        self,
        traveler_id: str,
        profile: TravelerProfile,
        use_llm: bool = True,
        allow_llm_fallback: bool = False,
    ):
        self.actor_id = traveler_id
        self.profile = profile
        self.use_llm = use_llm
        self.allow_llm_fallback = allow_llm_fallback

    def tick(self, world_state: dict[str, Any]) -> dict[str, Any]:
        round_number = world_state.get("round_number", 1)
        result = run_traveler_tick(
            traveler_id=self.actor_id,
            round_number=round_number,
            profile=self.profile,
            world_state=world_state,
            use_llm=self.use_llm,
            allow_llm_fallback=self.allow_llm_fallback,
        )
        return _traveler_tick_to_dict(result)

    def initialize(self) -> None:
        """Create the traveler state row and initial relationships."""
        state_mgr = TravelerStateManager(self.actor_id)
        state_mgr.initialize(
            profile_id=self.profile.profile_id,
            starting_location=self.profile.starting_location,
            inventory=list(self.profile.starting_inventory),
            private_notes=list(self.profile.private_notes),
        )
        rel_mgr = TravelerRelationshipManager(self.actor_id)
        for npc in database.list_npcs():
            rel_mgr.initialize_for_npc(npc["npc_id"])

    def get_direct_targets(self, tick_result: dict[str, Any]) -> set[str]:
        """Extract NPC IDs directly targeted by the Traveler's action."""
        targets: set[str] = set()
        action = tick_result.get("proposed_action", {})
        args = action.get("args", {})
        npc_id = args.get("npc_id")
        if npc_id:
            targets.add(str(npc_id))
        return targets


# ═══════════════════════════════════════════════════════════════════════
#  NpcActorAdapter
# ═══════════════════════════════════════════════════════════════════════

class NpcActorAdapter:
    """Adapter that wraps the existing autonomous_tick for a single NPC."""

    actor_type = "npc"

    def __init__(self, npc_id: str, autonomous_tick_mode: str = "llm_constrained"):
        self.actor_id = npc_id
        self.autonomous_tick_mode = autonomous_tick_mode

    def tick(self, world_state: dict[str, Any]) -> dict[str, Any]:
        result = run_autonomous_tick(
            npc_id=self.actor_id,
            mode=self.autonomous_tick_mode,
            run_director=False,
        )
        return _npc_tick_to_dict(result)

    def initialize(self) -> None:
        """Ensure the NPC runtime state is active."""
        db_npc = database.get_npc_runtime_state(self.actor_id)
        if db_npc.get("lifecycle_status") != "active":
            database.upsert_npc_runtime_state(self.actor_id, "active", True)


# ═══════════════════════════════════════════════════════════════════════
#  ArcDirectorActor
# ═══════════════════════════════════════════════════════════════════════

class ArcDirectorActor:
    """Actor that observes all round events and advances the narrative arc."""

    actor_type = "director"
    actor_id = "arc_director"

    def tick(
        self,
        world_state: dict[str, Any],
        all_events: list[dict[str, Any]] | None = None,
        npc_ticks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate arc state based on all accumulated events and NPC actions."""
        current = database.get_world_arc_state(ARC_ID)
        phase = str(current["phase"])
        metadata = current.get("metadata", {}) if isinstance(current.get("metadata"), dict) else {}

        # Count meaningful evidence separately from ambient routine signals.
        evidence_events = _classify_arc_evidence((all_events or []), npc_ticks or [])
        scores = _collect_scores_from_events(evidence_events["meaningful"])
        ambient_scores = _collect_scores_from_events(evidence_events["ambient"])
        cumulative_scores = _merge_arc_scores(metadata.get("cumulative_scores", {}), scores)
        cumulative_ambient_scores = _merge_arc_scores(
            metadata.get("cumulative_ambient_scores", {}),
            ambient_scores,
        )
        evidence_counts = _merge_count_map(
            metadata.get("evidence_counts", {}),
            _count_evidence_classes(evidence_events["meaningful"]),
        )

        total_signals = sum(scores.values())
        cumulative_total_signals = sum(cumulative_scores.values())
        evidence_route_buckets = _route_buckets(cumulative_scores)
        new_phase = phase
        if phase == "rumor" and _can_enter_evidence_gathering(cumulative_total_signals):
            new_phase = "evidence_gathering"
        elif phase == "evidence_gathering" and _can_enter_npc_conflict(cumulative_total_signals, evidence_route_buckets):
            new_phase = "npc_conflict"
        elif phase == "npc_conflict" and _can_resolve_arc(cumulative_total_signals, evidence_route_buckets, evidence_counts):
            new_phase = "resolved"

        metadata = {
            **metadata,
            "cumulative_scores": cumulative_scores,
            "cumulative_ambient_scores": cumulative_ambient_scores,
            "evidence_counts": evidence_counts,
            "evidence_route_buckets": evidence_route_buckets,
            "last_round_scores": scores,
            "last_round_ambient_scores": ambient_scores,
            "last_round_total_signals": total_signals,
        }
        database.update_world_arc_state(
            arc_id=ARC_ID,
            phase=new_phase,
            tension=min(10, int(current["tension"]) + (1 if new_phase != phase else 0)),
            metadata=metadata,
        )

        # If resolved, determine outcome. A long trace can keep producing
        # meaningful evidence after resolution, so refresh only when the
        # cumulative advantage actually changes.
        if new_phase == "resolved" and phase != "resolved":
            resolved = resolve_arc_outcome(cumulative_scores)
            apply_arc_outcome(
                outcome=resolved["arc_outcome"],
                reason=f"Arc resolved after {new_phase} phase.",
                confidence=0.7,
            )
        elif new_phase == "resolved":
            arc_state = database.get_world_arc_state(ARC_ID)
            resolved = resolve_arc_outcome(cumulative_scores)
            if resolved["arc_outcome"] != arc_state.get("outcome"):
                database.update_world_arc_state(
                    arc_id=ARC_ID,
                    advantage=resolved["advantage"],
                    outcome=resolved["arc_outcome"],
                    metadata={
                        **metadata,
                        "last_resolution_reason": "Resolved arc outcome refreshed after later evidence changed advantage.",
                        "last_resolution_confidence": 0.65,
                    },
                )

        arc_state = database.get_world_arc_state(ARC_ID)
        return {
            "arc_id": ARC_ID,
            "phase": arc_state["phase"],
            "tension": arc_state["tension"],
            "advantage": arc_state.get("advantage", "none"),
            "outcome": arc_state.get("outcome", ""),
            "scores": scores,
            "ambient_scores": ambient_scores,
            "total_signals": total_signals,
            "cumulative_scores": cumulative_scores,
            "cumulative_ambient_scores": cumulative_ambient_scores,
            "cumulative_total_signals": cumulative_total_signals,
            "evidence_counts": evidence_counts,
            "evidence_route_buckets": evidence_route_buckets,
        }


# ═══════════════════════════════════════════════════════════════════════
#  LivingWorldScheduler
# ═══════════════════════════════════════════════════════════════════════

class LivingWorldScheduler:
    """Round-based scheduler: Ambient → Traveler → NPC → Resolution."""

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
        self.traveler = traveler
        self.npc_adapters = npc_adapters
        self.arc_director = arc_director
        self.max_npc_ticks_per_round = max_npc_ticks_per_round
        self.npc_routines_every_round = npc_routines_every_round
        self.npc_cooldown_enabled = npc_cooldown_enabled
        self.idle_npc_probe_enabled = idle_npc_probe_enabled
        self.round_log: list[dict[str, Any]] = []

    def run(self, rounds: int) -> dict[str, Any]:
        """Execute the full simulation for the given number of rounds."""
        run_started = perf_counter()
        for round_num in range(1, rounds + 1):
            round_data = self._execute_round(round_num)
            self.round_log.append(round_data)
        result = self._build_final_result()
        result["timings"] = {"total_ms": _elapsed_ms(run_started)}
        return result

    def run_until_outcome(self, max_rounds: int) -> dict[str, Any]:
        """Execute rounds until the arc records an outcome or max_rounds is reached."""
        run_started = perf_counter()
        for round_num in range(1, max_rounds + 1):
            round_data = self._execute_round(round_num)
            self.round_log.append(round_data)
            if round_data["arc_update"].get("outcome"):
                break
        result = self._build_final_result()
        result["timings"] = {"total_ms": _elapsed_ms(run_started)}
        return result

    def _execute_round(self, round_num: int) -> dict[str, Any]:
        round_started = perf_counter()
        timings: dict[str, float] = {}

        # ═══ Phase A: AMBIENT ═══
        ambient_started = perf_counter()
        ambient_events = []
        if self.npc_routines_every_round:
            for routine in database.list_npc_routines(enabled_only=True):
                event = database.create_world_event(
                    event_type=routine["event_type"],
                    content=routine["event_content"],
                    source_type="npc_routine",
                    source_id=routine["npc_id"],
                    location_id=routine["location_id"],
                    visibility="location",
                    payload={
                        "arc_id": ARC_ID,
                        "arc_signal": arc_signal_for_npc(routine["npc_id"]),
                        "routine_type": routine["routine_type"],
                        "round": round_num,
                    },
                )
                ambient_events.append(event)
                dispatch_world_event_to_inbox(event)
        timings["ambient_routines_ms"] = _elapsed_ms(ambient_started)

        # ═══ Phase B: TRAVELER ═══
        traveler_started = perf_counter()
        world_state = self._build_world_state(round_num, ambient_events)
        traveler_result = self.traveler.tick(world_state)
        timings["traveler_tick_ms"] = _elapsed_ms(traveler_started)

        # ═══ Phase C: NPC ═══
        npc_started = perf_counter()
        npc_results = self._execute_npc_phase(traveler_result)
        timings["npc_ticks_ms"] = _elapsed_ms(npc_started)

        # ═══ Phase D: RESOLUTION ═══
        arc_started = perf_counter()
        all_events = ambient_events + traveler_result.get("created_events", [])
        all_events.extend(_extract_dialogue_evidence(traveler_result))
        for nr in npc_results:
            all_events.extend(nr.get("created_events", []))

        arc_update = self.arc_director.tick(world_state, all_events, npc_results)
        timings["arc_resolution_ms"] = _elapsed_ms(arc_started)
        timings["total_ms"] = _elapsed_ms(round_started)

        return {
            "round_number": round_num,
            "ambient_events": [{"id": e["id"], "event_type": e["event_type"]} for e in ambient_events],
            "traveler_tick": traveler_result,
            "npc_ticks": npc_results,
            "arc_update": arc_update,
            "timings": timings,
        }

    def _execute_npc_phase(self, traveler_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect and prioritize NPC ticks."""
        traveler_targets = self.traveler.get_direct_targets(traveler_result)

        # Collect NPCs with unseen inbox items
        npcs_with_inbox: list[tuple[int, str]] = []  # (priority, npc_id)
        for npc_id in self.npc_adapters:
            if not _npc_can_tick(npc_id):
                continue
            inbox = database.get_npc_event_inbox(npc_id, include_seen=False, limit=50)
            if not inbox:
                continue
            if npc_id in traveler_targets:
                npcs_with_inbox.append((0, npc_id))
            elif any(item.get("reason") == "explicit_target" for item in inbox):
                npcs_with_inbox.append((1, npc_id))
            elif any(item.get("reason") == "public" for item in inbox):
                npcs_with_inbox.append((2, npc_id))
            elif all(item.get("reason") == "idle_probe" for item in inbox):
                npcs_with_inbox.append((5, npc_id))
            else:
                npcs_with_inbox.append((3, npc_id))

        if self.idle_npc_probe_enabled:
            npcs_with_real_inbox = {npc_id for _, npc_id in npcs_with_inbox}
            for npc_id in self.npc_adapters:
                if npc_id in npcs_with_real_inbox:
                    continue
                if not _npc_can_tick(npc_id):
                    continue
                location = database.get_npc_location_state(npc_id)
                event = database.create_world_event(
                    event_type="npc_idle_routine_probe",
                    content=f"Low-priority idle routine probe for {npc_id}.",
                    source_type="scheduler",
                    source_id="living_world_scheduler",
                    location_id=location["location_id"],
                    visibility="npc_only",
                    payload={
                        "target_npc_ids": [npc_id],
                        "arc_id": ARC_ID,
                        "arc_signal": arc_signal_for_npc(npc_id),
                    },
                )
                database.add_npc_event_inbox_item(
                    npc_id=npc_id,
                    event_id=int(event["id"]),
                    relevance_score=0.2,
                    reason="idle_probe",
                )
                npcs_with_inbox.append((5, npc_id))

        npcs_with_inbox.sort(key=lambda x: x[0])

        results = []
        ticked: set[str] = set()
        for _, npc_id in npcs_with_inbox:
            if len(results) >= self.max_npc_ticks_per_round:
                break
            if npc_id in ticked:
                continue
            try:
                result = self.npc_adapters[npc_id].tick({})
                results.append(result)
                ticked.add(npc_id)
            except Exception:
                continue

        return results

    def _build_world_state(
        self, round_num: int, ambient_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        previous_events = []
        for prev in self.round_log:
            prev_events = prev.get("ambient_events", [])
            prev_events.extend(prev.get("traveler_tick", {}).get("created_events", []))
            previous_events.extend(prev_events)

        return {
            "round_number": round_num,
            "npc_states": {npc["npc_id"]: npc for npc in database.list_npcs()},
            "scene_objects": database.list_scene_objects(),
            "arc_state": database.get_world_arc_state(ARC_ID),
            "world_events_since_last_round": previous_events[-20:],
        }

    def _build_final_result(self) -> dict[str, Any]:
        arc_state = database.get_world_arc_state(ARC_ID)
        traveler_state = database.get_traveler_state(self.traveler.actor_id)
        relationships = database.get_all_traveler_relationships(self.traveler.actor_id)
        return {
            "profile_id": self.traveler.profile.profile_id,
            "traveler_id": self.traveler.actor_id,
            "total_rounds": len(self.round_log),
            "final_arc_outcome": arc_state.get("outcome", "unresolved"),
            "final_arc_phase": arc_state["phase"],
            "final_tension": arc_state["tension"],
            "final_traveler_location": traveler_state["current_location"],
            "final_relationships": {
                r["npc_id"]: {
                    "trust": r["trust"], "suspicion": r["suspicion"],
                    "affinity": r["affinity"], "last_tone": r["last_tone"],
                }
                for r in relationships
            },
            "rounds": self.round_log,
        }


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _traveler_tick_to_dict(result: TravelerTickResult) -> dict[str, Any]:
    return {
        "traveler_id": result.traveler_id,
        "round_number": result.round_number,
        "mode": result.mode,
        "observation": result.observation,
        "available_actions": [a["action_type"] for a in result.available_actions],
        "action_biases": result.action_biases,
        "decision": result.decision,
        "proposed_action": result.proposed_action,
        "validation": result.validation,
        "action_result": result.action_result,
        "state_changes": result.state_changes,
        "relationship_changes": result.relationship_changes,
        "created_events": result.created_events,
        "dialogue_exchange": result.dialogue_exchange,
        "reflection": result.reflection,
        "deception_metadata": result.deception_metadata,
        "disclosure_metadata": result.disclosure_metadata,
        "timings": result.timings,
        "tick_log_id": result.tick_log_id,
    }


def _npc_tick_to_dict(result: Any) -> dict[str, Any]:
    proposed_action = result.proposed_action if isinstance(result.proposed_action, dict) else {}
    action_type = str(proposed_action.get("action_type", "")).strip()
    validation = result.validation if isinstance(result.validation, dict) else {}
    trigger_event = result.trigger_event if isinstance(result.trigger_event, dict) else None
    trigger_payload = trigger_event.get("payload") if trigger_event and isinstance(trigger_event.get("payload"), dict) else {}
    if not action_type and str(validation.get("status", "")).startswith("rejected"):
        return {
            "npc_id": result.npc_id,
            "outcome": "skipped_no_valid_action",
            "trigger_event_id": trigger_event["id"] if trigger_event else None,
            "trigger_event_type": trigger_event.get("event_type") if trigger_event else None,
            "trigger_event_payload": trigger_payload,
            "proposed_action": {"action_type": "skip", "args": {}, "reason": "no valid NPC action selected"},
            "validation": validation,
            "action_result": result.action_result,
            "plan_update": result.plan_update,
            "proactive_message": None,
            "reflection": result.reflection,
            "tick_log_id": result.tick_log_id,
            "created_events": [],
        }
    return {
        "npc_id": result.npc_id,
        "outcome": result.outcome,
        "trigger_event_id": trigger_event["id"] if trigger_event else None,
        "trigger_event_type": trigger_event.get("event_type") if trigger_event else None,
        "trigger_event_payload": trigger_payload,
        "proposed_action": proposed_action,
        "validation": validation,
        "action_result": result.action_result,
        "plan_update": result.plan_update,
        "proactive_message": result.proactive_message["content"] if result.proactive_message else None,
        "reflection": result.reflection,
        "tick_log_id": result.tick_log_id,
        "created_events": [],
    }


def _collect_scores_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
    scores: dict[str, int] = {"guardian": 0, "research": 0, "sable": 0, "chaos": 0}
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        signal = str(payload.get("arc_signal", ""))
        if signal in scores:
            scores[signal] += 1
    return scores


def _classify_arc_evidence(events: list[dict[str, Any]], npc_ticks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    meaningful: list[dict[str, Any]] = []
    ambient: list[dict[str, Any]] = []
    for event in events:
        tagged = _tag_event_evidence(event)
        if not tagged:
            continue
        if tagged.get("evidence_class") == "routine":
            ambient.append(tagged)
        else:
            meaningful.append(tagged)
    meaningful.extend(_extract_npc_evidence(npc_ticks))
    return {"meaningful": meaningful, "ambient": ambient}


def _tag_event_evidence(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    signal = str(payload.get("arc_signal", ""))
    if signal not in {"guardian", "research", "sable", "chaos"}:
        return None
    event_type = str(event.get("event_type", ""))
    source_type = str(event.get("source_type", ""))
    tagged = {**event, "payload": payload}
    explicit_class = str(event.get("evidence_class", ""))
    if explicit_class in {"traveler_action", "dialogue_response", "autonomous_npc_action", "resolution_trigger"}:
        tagged["evidence_class"] = explicit_class
    elif event_type in {"npc_routine_activity", "npc_idle_routine_probe"} or source_type == "npc_routine":
        tagged["evidence_class"] = "routine"
    elif _is_resolution_trigger(event_type, payload):
        tagged["evidence_class"] = "resolution_trigger"
    elif event_type.startswith("traveler_") or source_type == "traveler" or not event_type:
        tagged["evidence_class"] = "traveler_action"
    else:
        tagged["evidence_class"] = "traveler_action"
    return tagged


def _is_resolution_trigger(event_type: str, payload: dict[str, Any]) -> bool:
    return (
        bool(payload.get("resolution_trigger"))
        or event_type in {"traveler_submitted_evidence", "secret_disclosed"}
        or "lockdown" in event_type
    )


def _merge_arc_scores(existing: dict[str, Any], current: dict[str, int]) -> dict[str, int]:
    existing_scores = existing if isinstance(existing, dict) else {}
    cumulative = {"guardian": 0, "research": 0, "sable": 0, "chaos": 0}
    for key in cumulative:
        cumulative[key] = _safe_int(existing_scores.get(key, 0)) + _safe_int(current.get(key, 0))
    return cumulative


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count_evidence_classes(events: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "traveler_action": 0,
        "dialogue_response": 0,
        "autonomous_npc_action": 0,
        "resolution_trigger": 0,
    }
    for event in events:
        evidence_class = str(event.get("evidence_class", ""))
        if evidence_class in counts:
            counts[evidence_class] += 1
    return counts


def _merge_count_map(existing: dict[str, Any], current: dict[str, int]) -> dict[str, int]:
    existing_counts = existing if isinstance(existing, dict) else {}
    keys = ["traveler_action", "dialogue_response", "autonomous_npc_action", "resolution_trigger"]
    return {key: _safe_int(existing_counts.get(key, 0)) + _safe_int(current.get(key, 0)) for key in keys}


def _route_buckets(scores: dict[str, int]) -> list[str]:
    return [key for key in ["guardian", "research", "sable", "chaos"] if int(scores.get(key, 0)) > 0]


def _can_enter_evidence_gathering(cumulative_total_signals: int) -> bool:
    return cumulative_total_signals >= 1


def _can_enter_npc_conflict(cumulative_total_signals: int, evidence_route_buckets: list[str]) -> bool:
    return cumulative_total_signals >= 2 and len(evidence_route_buckets) >= 2


def _can_resolve_arc(
    cumulative_total_signals: int,
    evidence_route_buckets: list[str],
    evidence_counts: dict[str, int],
) -> bool:
    if int(evidence_counts.get("resolution_trigger", 0)) >= 1:
        return True
    consequential_npc_evidence = int(evidence_counts.get("autonomous_npc_action", 0)) + int(
        evidence_counts.get("dialogue_response", 0)
    )
    return cumulative_total_signals >= 3 and len(evidence_route_buckets) >= 2 and consequential_npc_evidence >= 1


def _npc_can_tick(npc_id: str) -> bool:
    try:
        runtime = database.get_npc_runtime_state(npc_id)
    except Exception:
        return True
    return runtime.get("lifecycle_status") == "active" and bool(runtime.get("tick_enabled", True))


def _extract_dialogue_evidence(traveler_result: dict[str, Any]) -> list[dict[str, Any]]:
    dialogue = traveler_result.get("dialogue_exchange")
    if not isinstance(dialogue, dict) or not dialogue:
        return []
    if not _dialogue_has_consequence(dialogue):
        return []
    npc_id = str(dialogue.get("npc_id", ""))
    signal = arc_signal_for_npc(npc_id)
    return [{
        "event_type": "dialogue_response",
        "source_type": "npc",
        "evidence_class": "dialogue_response",
        "payload": {"arc_signal": signal},
    }]


def _dialogue_has_consequence(dialogue: dict[str, Any]) -> bool:
    action_result = dialogue.get("npc_action_result") if isinstance(dialogue.get("npc_action_result"), dict) else {}
    if action_result.get("state_changes") or action_result.get("executed_tools"):
        return True
    npc_decision = dialogue.get("npc_decision") if isinstance(dialogue.get("npc_decision"), dict) else {}
    intent = str(npc_decision.get("intent", ""))
    if intent in {"probe_for_evidence", "withhold_ruins_entrance", "reveal_safe_hint"}:
        return True
    return bool(str(dialogue.get("npc_response", "")).strip())


def _extract_npc_evidence(npc_ticks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for tick in npc_ticks:
        validation = tick.get("validation") if isinstance(tick.get("validation"), dict) else {}
        status = str(validation.get("status", ""))
        outcome = str(tick.get("outcome", ""))
        if tick.get("trigger_event_type") == "npc_idle_routine_probe":
            continue
        if status and status != "allowed":
            continue
        if outcome in {"", "no_op", "skipped_no_valid_action"}:
            continue
        trigger_payload = tick.get("trigger_event_payload") if isinstance(tick.get("trigger_event_payload"), dict) else {}
        signal = str(trigger_payload.get("arc_signal", ""))
        if signal in {"guardian", "research", "sable", "chaos"}:
            events.append({
                "event_type": "autonomous_npc_action",
                "source_type": "npc",
                "payload": {"arc_signal": signal},
                "evidence_class": "autonomous_npc_action",
            })
    return events


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
