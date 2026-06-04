"""Traveler autonomous tick — full observe→decide→act→reflect→trace loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.agent.exploration_planner import build_exploration_context
from src.agent.traveler_actions import (
    ActionBias,
    compute_action_biases,
    get_traveler_available_actions,
    get_unavailable_actions_with_reasons,
)
from src.agent.traveler_decision import decide_traveler_action
from src.agent.traveler_profile import TravelerProfile
from src.agent.traveler_state import (
    SecretTracker,
    TravelerRelationshipManager,
    TravelerStateManager,
)
from src.storage import database


@dataclass(frozen=True)
class TravelerTickResult:
    traveler_id: str
    round_number: int
    mode: str  # "llm" | "deterministic_fallback"
    observation: dict[str, Any]
    retrieved_memories: list[dict[str, Any]]
    available_actions: list[dict[str, Any]]
    unavailable_actions: list[dict[str, Any]]
    action_biases: list[dict[str, Any]]
    decision: dict[str, Any]
    proposed_action: dict[str, Any]
    validation: dict[str, Any]
    action_result: dict[str, Any]
    state_changes: list[dict[str, Any]]
    relationship_changes: list[dict[str, Any]]
    created_events: list[dict[str, Any]]
    reflection: dict[str, Any]
    deception_metadata: dict[str, Any] | None
    disclosure_metadata: dict[str, Any] | None
    timings: dict[str, float]
    tick_log_id: int


def run_traveler_tick(
    traveler_id: str,
    round_number: int,
    profile: TravelerProfile,
    world_state: dict[str, Any],
    use_llm: bool = True,
    allow_llm_fallback: bool = True,
    memory_retrieval_mode: str = "hybrid",
) -> TravelerTickResult:
    """Execute one full Traveler autonomous tick.

    Args:
        traveler_id: The traveler's unique ID.
        round_number: Current simulation round.
        profile: The validated TravelerProfile.
        world_state: Snapshot of the world (NPCs, scene objects, arc state, events).
        use_llm: Whether to use LLM for decision (False = deterministic fallback).
        memory_retrieval_mode: Memory retrieval strategy.
    """
    database.initialize_database()
    total_started = perf_counter()
    timings: dict[str, float] = {}

    # 1. OBSERVE
    observe_started = perf_counter()
    observation = _build_observation(traveler_id, round_number, world_state, memory_retrieval_mode)
    timings["observe_ms"] = _elapsed_ms(observe_started)

    # 2. RETRIEVE MEMORY
    retrieve_started = perf_counter()
    retrieved_memories = _retrieve_traveler_memories(traveler_id, observation)
    timings["retrieve_memory_ms"] = _elapsed_ms(retrieve_started)

    # 3. BUILD ACTION SURFACE
    action_surface_started = perf_counter()
    state_mgr = TravelerStateManager(traveler_id)
    traveler_state = state_mgr.get_state()
    npc_ids = _collect_npc_ids(world_state)
    scene_objects = world_state.get("scene_objects", [])

    available_actions = get_traveler_available_actions(
        traveler_state,
        npc_ids=npc_ids,
        scene_objects=scene_objects,
    )
    unavailable_actions = get_unavailable_actions_with_reasons(
        traveler_state,
        npc_ids=npc_ids,
        scene_objects=scene_objects,
    )
    biases = compute_action_biases(available_actions, profile)
    exploration_context = build_exploration_context(traveler_id, observation, available_actions)
    decision_observation = {**observation, "exploration_context": exploration_context}
    timings["build_action_surface_ms"] = _elapsed_ms(action_surface_started)

    # 4. DECIDE
    decide_started = perf_counter()
    decision = decide_traveler_action(
        profile=profile,
        observation=decision_observation,
        available_actions=available_actions,
        unavailable_actions=unavailable_actions,
        use_llm=use_llm,
        allow_llm_fallback=allow_llm_fallback,
    )
    timings["decide_ms"] = _elapsed_ms(decide_started)

    # 5. VALIDATE
    validate_started = perf_counter()
    validation = _validate_traveler_decision(decision, available_actions)
    timings["validate_ms"] = _elapsed_ms(validate_started)

    # 6. ACT
    act_started = perf_counter()
    rel_mgr = TravelerRelationshipManager(traveler_id)
    secret_tracker = SecretTracker()

    if validation["status"] == "allowed":
        action_result, state_changes, rel_changes, created_events, deception_meta, disclosure_meta = (
            _execute_traveler_action(
                traveler_id=traveler_id,
                decision=decision,
                profile=profile,
                state_mgr=state_mgr,
                rel_mgr=rel_mgr,
                secret_tracker=secret_tracker,
                round_number=round_number,
                world_state=world_state,
            )
        )
    else:
        action_result = _empty_action_result(validation.get("reason", "blocked"))
        state_changes, rel_changes = [], []
        created_events, deception_meta, disclosure_meta = [], None, None
    timings["act_ms"] = _elapsed_ms(act_started)

    # 7. REFLECT
    reflect_started = perf_counter()
    reflection = _build_reflection(traveler_id, decision, action_result, exploration_context)
    timings["reflect_ms"] = _elapsed_ms(reflect_started)

    # 8. LOG TRACE
    trace_log_started = perf_counter()
    tick_log = database.log_traveler_tick(
        traveler_id=traveler_id,
        round_number=round_number,
        observation=decision_observation,
        retrieved_memories=retrieved_memories,
        available_actions=available_actions,
        action_biases=[asdict(b) for b in biases],
        llm_decision=decision,
        proposed_action=decision.get("selected_action", {}),
        validation=validation,
        action_result=action_result,
        state_changes=state_changes,
        relationship_changes=rel_changes,
        created_events=[_event_summary(e) for e in created_events],
        reflection=reflection,
        deception_metadata=deception_meta or {},
        disclosure_metadata=disclosure_meta or {},
    )
    timings["trace_log_ms"] = _elapsed_ms(trace_log_started)
    timings["total_ms"] = _elapsed_ms(total_started)
    tick_log = database.update_traveler_tick_timings(int(tick_log["id"]), timings)

    return TravelerTickResult(
        traveler_id=traveler_id,
        round_number=round_number,
        mode=decision.get("mode", "deterministic_fallback"),
        observation=decision_observation,
        retrieved_memories=retrieved_memories,
        available_actions=available_actions,
        unavailable_actions=unavailable_actions,
        action_biases=[asdict(b) for b in biases],
        decision=decision,
        proposed_action=decision.get("selected_action", {}),
        validation=validation,
        action_result=action_result,
        state_changes=state_changes,
        relationship_changes=rel_changes,
        created_events=[_event_summary(e) for e in created_events],
        reflection=reflection,
        deception_metadata=deception_meta,
        disclosure_metadata=disclosure_meta,
        timings=timings,
        tick_log_id=int(tick_log["id"]),
    )


# ── Observation ─────────────────────────────────────────────────────

def _build_observation(
    traveler_id: str,
    round_number: int,
    world_state: dict[str, Any],
    memory_retrieval_mode: str,
) -> dict[str, Any]:
    state = database.get_traveler_state(traveler_id)
    relationships = database.get_all_traveler_relationships(traveler_id)
    return {
        "traveler_id": traveler_id,
        "round_number": round_number,
        "traveler_state": {
            "current_location": state["current_location"],
            "inventory": state["inventory"],
            "private_notes": state["private_notes"],
            "active_goal": state["active_goal"],
        },
        "relationships": {r["npc_id"]: {
            "trust": r["trust"], "suspicion": r["suspicion"],
            "affinity": r["affinity"], "last_tone": r["last_tone"],
        } for r in relationships},
        "npc_states": world_state.get("npc_states", {}),
        "scene_objects": [
            {"object_id": o["object_id"], "name": o["name"], "location_id": o["location_id"]}
            for o in world_state.get("scene_objects", [])
        ],
        "arc_state": world_state.get("arc_state", {}),
        "recent_events": world_state.get("world_events_since_last_round", [])[-10:],
        "memory_retrieval_mode": memory_retrieval_mode,
    }


def _retrieve_traveler_memories(
    traveler_id: str,
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return database.search_memories(
            f"traveler {traveler_id} observation",
            npc_id=traveler_id,
            mode=observation.get("memory_retrieval_mode", "hybrid"),
        )
    except Exception:
        return []


def _collect_npc_ids(world_state: dict[str, Any]) -> list[str]:
    npc_states = world_state.get("npc_states", {})
    if npc_states:
        return list(npc_states.keys())
    return [npc["npc_id"] for npc in database.list_npcs()]


# ── Validation ──────────────────────────────────────────────────────

def _validate_traveler_decision(
    decision: dict[str, Any],
    available_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = decision.get("selected_action", {})
    action_type = selected.get("action_type", "")

    available_types = {a["action_type"] for a in available_actions}
    if action_type not in available_types:
        return {
            "status": "rejected",
            "reason": f"Action '{action_type}' is not in available_actions.",
        }
    # Validate args against schema
    for a in available_actions:
        if a["action_type"] == action_type:
            schema = a.get("args_schema", {})
            args = selected.get("args", {})
            arg_options = a.get("arg_options", {}) if isinstance(a.get("arg_options"), dict) else {}
            for field, expected_type in schema.items():
                if field not in args:
                    return {
                        "status": "rejected",
                        "reason": f"Missing required arg '{field}' for {action_type}.",
                    }
                value = args.get(field)
                if expected_type == "string" and not str(value).strip():
                    return {
                        "status": "rejected",
                        "reason": f"Required arg '{field}' for {action_type} is empty.",
                    }
                allowed_values = arg_options.get(field)
                if isinstance(allowed_values, list) and allowed_values and str(value) not in {str(v) for v in allowed_values}:
                    return {
                        "status": "rejected",
                        "reason": f"Arg '{field}' for {action_type} is not an available option.",
                    }
            return {"status": "allowed", "reason": "Action is available and args present."}
    return {"status": "rejected", "reason": f"Action '{action_type}' not found."}


# ── Action Execution ────────────────────────────────────────────────

def _execute_traveler_action(
    traveler_id: str,
    decision: dict[str, Any],
    profile: TravelerProfile,
    state_mgr: TravelerStateManager,
    rel_mgr: TravelerRelationshipManager,
    secret_tracker: SecretTracker,
    round_number: int,
    world_state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    selected = decision.get("selected_action", {})
    action_type = selected.get("action_type", "")
    args = selected.get("args", {})

    state_changes: list[dict[str, Any]] = []
    rel_changes: list[dict[str, Any]] = []
    created_events: list[dict[str, Any]] = []
    deception_meta = None
    disclosure_meta = None

    before_state = state_mgr.get_state()

    if action_type == "move_to":
        location_id = str(args.get("location_id", ""))
        if location_id:
            before_loc = state_mgr.current_location
            state_mgr.move_to(location_id)
            state_changes.append({"field": "location", "before": before_loc, "after": location_id})
            event = _create_world_event(
                event_type="traveler_moved",
                content=f"{profile.identity.public_name} moved to {location_id}.",
                source_id=traveler_id,
                location_id=location_id,
                round_number=round_number,
            )
            created_events.append(event)

    elif action_type == "talk_to":
        npc_id = str(args.get("npc_id", ""))
        topic = str(args.get("topic", ""))
        tone = str(args.get("tone", "neutral"))
        honesty = str(args.get("honesty_level", "full"))

        if npc_id:
            rel_mgr.set_tone(npc_id, tone)
            # Update relationship based on tone and honesty
            if tone in ("friendly", "warm"):
                rel_mgr.update_affinity(npc_id, 0.1)
                rel_mgr.update_trust(npc_id, 0.05)
            elif tone in ("guarded", "suspicious"):
                rel_mgr.update_suspicion(npc_id, 0.1)

            after_rel = rel_mgr.get(npc_id)
            rel_changes = rel_mgr.snapshot_changes(npc_id, after_rel)

            # Handle deception
            deception_meta = _handle_deception(decision, npc_id, round_number)
            # Handle disclosure
            disclosure_meta = _handle_disclosure(decision, npc_id, secret_tracker, round_number)

            event = _create_world_event(
                event_type="traveler_talked_to_npc",
                content=f"{profile.identity.public_name} talked to {npc_id} about '{topic}' (tone={tone}, honesty={honesty}).",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"npc_id": npc_id, "topic": topic, "tone": tone, "honesty_level": honesty},
            )
            created_events.append(event)

    elif action_type == "investigate":
        target_id = str(args.get("target_id", ""))
        method = str(args.get("method", ""))
        if target_id:
            try:
                scene_obj = database.get_scene_object(target_id)
                state = dict(scene_obj.get("state", {}))
                state["observed"] = True
                state["last_investigated_by"] = traveler_id
                state["last_investigated_round"] = round_number
                database.update_scene_object_state(target_id, state)
                state_changes.append({"field": f"scene_object.{target_id}.observed", "before": False, "after": True})
            except Exception:
                pass
            event = _create_world_event(
                event_type="traveler_investigated",
                content=f"{profile.identity.public_name} investigated {target_id} using {method}.",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"target_id": target_id, "method": method},
            )
            created_events.append(event)

    elif action_type == "ask_for_help":
        npc_id = str(args.get("npc_id", ""))
        if npc_id:
            rel_mgr.set_tone(npc_id, "requesting")
            after_rel = rel_mgr.get(npc_id)
            rel_changes = rel_mgr.snapshot_changes(npc_id, after_rel)
            event = _create_world_event(
                event_type="traveler_asked_help",
                content=f"{profile.identity.public_name} asked {npc_id} for help: {args.get('request', '')}",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"npc_id": npc_id, "request": args.get("request", "")},
            )
            created_events.append(event)

    elif action_type == "share_information":
        npc_id = str(args.get("npc_id", ""))
        if npc_id:
            rel_mgr.update_exposure(npc_id, 0.1)
            after_rel = rel_mgr.get(npc_id)
            rel_changes = rel_mgr.snapshot_changes(npc_id, after_rel)
            event = _create_world_event(
                event_type="traveler_shared_info",
                content=f"{profile.identity.public_name} shared information with {npc_id}.",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"npc_id": npc_id, "claim": args.get("claim", "")},
            )
            created_events.append(event)

    elif action_type == "trade_with":
        npc_id = str(args.get("npc_id", ""))
        if npc_id:
            offered = str(args.get("offered_item", ""))
            if offered and offered in state_mgr.inventory:
                state_mgr.remove_inventory_item(offered)
                state_changes.append({"field": "inventory", "removed": offered})
            rel_mgr.update_affinity(npc_id, 0.05)
            after_rel = rel_mgr.get(npc_id)
            rel_changes = rel_mgr.snapshot_changes(npc_id, after_rel)
            event = _create_world_event(
                event_type="traveler_traded",
                content=f"{profile.identity.public_name} traded with {npc_id}.",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"npc_id": npc_id, "offered_item": offered},
            )
            created_events.append(event)

    elif action_type == "challenge_claim":
        npc_id = str(args.get("npc_id", ""))
        if npc_id:
            rel_mgr.update_suspicion(npc_id, -0.1)
            rel_mgr.update_trust(npc_id, -0.1)
            after_rel = rel_mgr.get(npc_id)
            rel_changes = rel_mgr.snapshot_changes(npc_id, after_rel)
            event = _create_world_event(
                event_type="traveler_challenged",
                content=f"{profile.identity.public_name} challenged {npc_id}'s claim.",
                source_id=traveler_id,
                location_id=state_mgr.current_location,
                round_number=round_number,
                payload={"npc_id": npc_id, "evidence_id": args.get("evidence_id", "")},
            )
            created_events.append(event)

    elif action_type == "follow_lead":
        state_mgr.add_private_note(f"Round {round_number}: followed lead {args.get('lead_id', 'unknown')}.")
        state_changes.append({"field": "private_notes", "change": "note_added"})

    elif action_type == "record_private_note":
        content = str(args.get("content", ""))
        if content:
            state_mgr.add_private_note(content)
            state_changes.append({"field": "private_notes", "change": "note_added"})

    elif action_type == "wait_and_observe":
        event = _create_world_event(
            event_type="traveler_waited",
            content=f"{profile.identity.public_name} waited and observed at {state_mgr.current_location}.",
            source_id=traveler_id,
            location_id=state_mgr.current_location,
            round_number=round_number,
        )
        created_events.append(event)

    # Dispatch all created events to NPC inboxes
    for event in created_events:
        try:
            dispatch_world_event_to_inbox(event)
        except Exception:
            pass

    action_result = {
        "accepted": True,
        "blocked_reason": "",
        "action_type": action_type,
        "state_changes": state_changes,
        "relationship_changes": rel_changes,
        "created_event_ids": [e.get("id") for e in created_events],
    }

    return action_result, state_changes, rel_changes, created_events, deception_meta, disclosure_meta


# ── Helpers ─────────────────────────────────────────────────────────

def _create_world_event(
    event_type: str,
    content: str,
    source_id: str,
    location_id: str,
    round_number: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return database.create_world_event(
        event_type=event_type,
        content=content,
        source_type="traveler",
        source_id=source_id,
        location_id=location_id,
        visibility="location",
        payload={
            **(payload or {}),
            "round": round_number,
            "arc_signal": "chaos",
        },
    )


def _handle_deception(
    decision: dict[str, Any],
    npc_id: str,
    round_number: int,
) -> dict[str, Any] | None:
    deception = decision.get("deception_choice")
    if not isinstance(deception, dict) or not deception:
        return None
    return {
        "round_number": round_number,
        "target_npc_id": npc_id,
        "deception_type": str(deception.get("type", "unknown")),
        "claim_made": str(deception.get("claim", "")),
        "truth": str(deception.get("truth", "")),
        "detected": False,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _handle_disclosure(
    decision: dict[str, Any],
    npc_id: str,
    secret_tracker: SecretTracker,
    round_number: int,
) -> dict[str, Any] | None:
    disclosure = decision.get("disclosure_choice")
    if not isinstance(disclosure, dict) or not disclosure:
        return None
    secret_id = str(disclosure.get("secret_id", ""))
    level = str(disclosure.get("level", "partial"))
    if secret_id:
        try:
            secret_tracker.record_disclosure(
                secret_id=secret_id,
                disclosed_to=npc_id,
                actor_type="npc",
                round_number=round_number,
                method=level,
            )
        except Exception:
            pass
    return {
        "round_number": round_number,
        "secret_id": secret_id,
        "disclosed_to": npc_id,
        "disclosure_level": level,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_reflection(
    traveler_id: str,
    decision: dict[str, Any],
    action_result: dict[str, Any],
    exploration_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "traveler_id": traveler_id,
        "action_type": decision.get("selected_action", {}).get("action_type", "unknown"),
        "accepted": action_result.get("accepted", False),
        "summary": f"Traveler {decision.get('selected_action', {}).get('action_type', 'unknown')} — {'accepted' if action_result.get('accepted') else 'blocked'}.",
        "decision_reason": decision.get("decision_reason", ""),
        "exploration_context": exploration_context or {},
    }


def _empty_action_result(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "blocked_reason": reason,
        "action_type": "none",
        "state_changes": [],
        "relationship_changes": [],
        "created_event_ids": [],
    }


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "id": event.get("id"),
        "event_type": event.get("event_type"),
        "content": event.get("content"),
    }
    payload = event.get("payload")
    if isinstance(payload, dict):
        safe_payload = _json_safe_payload(payload)
        if safe_payload:
            summary["payload"] = safe_payload
    return summary


def _json_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): safe_value
        for key, value in payload.items()
        if (safe_value := _json_safe_value(value)) is not _UNSAFE_PAYLOAD_VALUE
    }


_UNSAFE_PAYLOAD_VALUE = object()


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        safe_items = [_json_safe_value(item) for item in value]
        if any(item is _UNSAFE_PAYLOAD_VALUE for item in safe_items):
            return _UNSAFE_PAYLOAD_VALUE
        return safe_items
    if isinstance(value, dict):
        return _json_safe_payload(value)
    return _UNSAFE_PAYLOAD_VALUE


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
