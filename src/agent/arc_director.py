from __future__ import annotations

from typing import Any

from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.agent.llm_client import call_openai_compatible_json
from src.agent.world_arc import ARC_ID, ARC_OUTCOMES, apply_arc_outcome, resolve_arc_outcome
from src.storage import database


ARC_DIRECTOR_SYSTEM_PROMPT = """
You are a constrained narrative director for the ruins chapter demo.
Return only JSON. You may choose one allowed arc_outcome and propose events,
but all state changes will be validated by the program before persistence.
"""

ALLOWED_STATE_FIELDS = {"phase", "tension", "advantage", "outcome", "metadata"}


def run_arc_director(use_llm: bool = True) -> dict[str, Any]:
    context = build_director_context()
    llm_payload = call_director_llm(context) if use_llm else deterministic_director_payload()
    return validate_and_apply_director_payload(llm_payload)


def build_director_context() -> dict[str, Any]:
    return {
        "arc_state": database.get_world_arc_state(ARC_ID),
        "scene_objects": database.list_scene_objects(),
        "npc_locations": database.list_npc_locations(),
        "recent_world_events": database.get_world_events(limit=30),
        "allowed_outcomes": sorted(ARC_OUTCOMES),
        "allowed_state_fields": sorted(ALLOWED_STATE_FIELDS),
    }


def call_director_llm(context: dict[str, Any]) -> dict[str, Any]:
    try:
        return call_openai_compatible_json(
            system_prompt=ARC_DIRECTOR_SYSTEM_PROMPT,
            user_payload=context,
        )
    except Exception as exc:
        payload = deterministic_director_payload()
        payload["reason"] = f"Fallback used because arc director LLM failed: {exc}"
        return payload


def deterministic_director_payload() -> dict[str, Any]:
    resolved = resolve_arc_outcome()
    return {
        "arc_outcome": resolved["arc_outcome"],
        "confidence": 0.6,
        "reason": f"Deterministic arc scores selected {resolved['arc_outcome']}.",
        "recommended_events": [],
        "state_change_requests": [{"field": "outcome", "value": resolved["arc_outcome"]}],
        "npc_reaction_hints": [],
    }


def validate_and_apply_director_payload(payload: dict[str, Any]) -> dict[str, Any]:
    outcome = str(payload.get("arc_outcome", ""))
    if outcome not in ARC_OUTCOMES:
        outcome = resolve_arc_outcome()["arc_outcome"]
    confidence = parse_confidence(payload.get("confidence"))
    accepted_requests = []
    rejected_requests = []
    for request in payload.get("state_change_requests", []):
        if not isinstance(request, dict):
            rejected_requests.append({"request": request, "reason": "state change request must be an object"})
            continue
        field = str(request.get("field", ""))
        value = request.get("value")
        if field not in ALLOWED_STATE_FIELDS:
            rejected_requests.append({**request, "reason": "field is not allowed"})
            continue
        if field == "outcome" and str(value) not in ARC_OUTCOMES:
            rejected_requests.append({**request, "reason": "outcome is not allowed"})
            continue
        accepted_requests.append(request)
    arc_state = apply_arc_outcome(
        outcome=outcome,
        reason=str(payload.get("reason", "")),
        confidence=confidence,
    )
    created_events = create_recommended_events(payload.get("recommended_events", []))
    return {
        "arc_id": ARC_ID,
        "arc_outcome": outcome,
        "confidence": confidence,
        "reason": str(payload.get("reason", "")),
        "accepted_state_change_requests": accepted_requests,
        "rejected_state_change_requests": rejected_requests,
        "created_events": created_events,
        "npc_reaction_hints": payload.get("npc_reaction_hints", [])
        if isinstance(payload.get("npc_reaction_hints"), list)
        else [],
        "arc_state": arc_state,
    }


def create_recommended_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    created = []
    for item in events:
        if not isinstance(item, dict):
            continue
        visibility = str(item.get("visibility", "public"))
        if visibility not in {"public", "location", "private", "npc_only"}:
            visibility = "public"
        target_npc_ids = item.get("target_npc_ids", [])
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if isinstance(target_npc_ids, list):
            payload = {**payload, "target_npc_ids": [str(npc_id) for npc_id in target_npc_ids]}
        event = database.create_world_event(
            event_type=str(item.get("event_type", "arc_director_event")),
            content=str(item.get("content", "")) or "The ruins arc director recommended an event.",
            source_type="arc_director",
            source_id=ARC_ID,
            location_id=item.get("location_id"),
            visibility=visibility,
            payload={**payload, "arc_id": ARC_ID},
        )
        dispatch_world_event_to_inbox(event)
        created.append(event)
    return created


def parse_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
