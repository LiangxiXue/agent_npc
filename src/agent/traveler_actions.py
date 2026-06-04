"""Traveler action catalog — available actions, preconditions, and profile biases."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.agent.traveler_profile import TravelerProfile
from src.storage import database


# ── Action spec ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TravelerActionSpec:
    action_type: str
    description: str
    args_schema: dict[str, Any]
    preconditions: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    forbidden_effects: list[str] = field(default_factory=list)
    prompt_hint: str | None = None


@dataclass(frozen=True)
class ActionBias:
    action_type: str
    supporting_motivations: tuple[str, ...]
    opposing_personality: tuple[str, ...]
    risk_level: str  # low | medium | high
    profile_alignment_score: float  # -1.0 .. 1.0


# ── Action catalog ─────────────────────────────────────────────────────

TRAVELER_ACTION_SPECS: list[TravelerActionSpec] = [
    TravelerActionSpec(
        action_type="move_to",
        description="Move to a different location in the town.",
        args_schema={"location_id": "string"},
        preconditions=["location_exists", "location_not_current"],
        effects=["traveler_location_changed"],
        forbidden_effects=[],
        prompt_hint="Use to explore a new area or reach a specific NPC.",
    ),
    TravelerActionSpec(
        action_type="talk_to",
        description="Initiate a conversation with an NPC at the current location.",
        args_schema={"npc_id": "string", "topic": "string", "tone": "string", "honesty_level": "string", "disclosure": "string"},
        preconditions=["npc_exists", "npc_same_location"],
        effects=["dialogue_event", "relationship_update"],
        forbidden_effects=["unlock_location", "complete_quest", "modify_canonical_fact"],
        prompt_hint="Choose topic, tone (friendly/neutral/guarded/formal), honesty (full/partial/omission/lie), and whether to disclose any secret.",
    ),
    TravelerActionSpec(
        action_type="investigate",
        description="Investigate a scene object at the current location.",
        args_schema={"target_id": "string", "method": "string"},
        preconditions=["object_exists", "object_same_location", "object_not_destroyed"],
        effects=["scene_object_observed", "evidence_collected"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use to examine objects, gather clues, or find evidence.",
    ),
    TravelerActionSpec(
        action_type="ask_for_help",
        description="Ask an NPC for help with a goal or problem.",
        args_schema={"npc_id": "string", "request": "string", "honesty_level": "string"},
        preconditions=["npc_exists", "npc_same_location"],
        effects=["dialogue_event", "relationship_update", "quest_trigger_possible"],
        forbidden_effects=["unlock_location", "complete_quest"],
        prompt_hint="Be specific about what help you need. NPC may refuse based on relationship.",
    ),
    TravelerActionSpec(
        action_type="share_information",
        description="Share information or a claim with an NPC.",
        args_schema={"npc_id": "string", "claim": "string", "honesty_level": "string"},
        preconditions=["npc_exists", "npc_same_location"],
        effects=["dialogue_event", "relationship_update", "rumor_possible"],
        forbidden_effects=["modify_canonical_fact"],
        prompt_hint="Information shared may spread as rumor to other NPCs.",
    ),
    TravelerActionSpec(
        action_type="trade_with",
        description="Propose a trade with an NPC — item for information, or item for item.",
        args_schema={"npc_id": "string", "offered_item": "string", "requested_info": "string"},
        preconditions=["npc_exists", "npc_same_location", "traveler_has_offered_item"],
        effects=["trade_event", "inventory_change", "relationship_update"],
        forbidden_effects=["unlock_location"],
        prompt_hint="NPCs value different things: scholars value evidence, merchants value coin.",
    ),
    TravelerActionSpec(
        action_type="challenge_claim",
        description="Challenge an NPC's previous statement with evidence.",
        args_schema={"npc_id": "string", "evidence_id": "string"},
        preconditions=["npc_exists", "npc_same_location", "evidence_recorded"],
        effects=["dialogue_event", "relationship_update", "deception_may_be_exposed"],
        forbidden_effects=["modify_canonical_fact"],
        prompt_hint="Use when you suspect an NPC is lying or when you have contradictory evidence.",
    ),
    TravelerActionSpec(
        action_type="follow_lead",
        description="Follow up on a previously recorded lead or clue.",
        args_schema={"lead_id": "string"},
        preconditions=["lead_exists", "lead_not_expired"],
        effects=["location_change_possible", "evidence_collected"],
        forbidden_effects=[],
        prompt_hint="Leads are created by rumors, NPC tips, or investigation results.",
    ),
    TravelerActionSpec(
        action_type="wait_and_observe",
        description="Wait and observe the current location without taking action.",
        args_schema={},
        preconditions=[],
        effects=["ambient_events_advance", "npc_routines_fire"],
        forbidden_effects=[],
        prompt_hint="Use when you want to see what happens naturally or need time to think.",
    ),
    TravelerActionSpec(
        action_type="record_private_note",
        description="Record a private observation or thought. No NPC will see this.",
        args_schema={"content": "string"},
        preconditions=[],
        effects=["private_note_added"],
        forbidden_effects=[],
        prompt_hint="Use to track suspicions, plan next moves, or remember important details.",
    ),
]


# ── Available actions builder ──────────────────────────────────────────

def get_traveler_available_actions(
    traveler_state: dict[str, Any],
    npc_ids: list[str] | None = None,
    scene_objects: list[dict[str, Any]] | None = None,
    active_leads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return actions whose preconditions are met for the current Traveler state."""
    available = []
    for spec in TRAVELER_ACTION_SPECS:
        failures = _check_preconditions(spec, traveler_state, npc_ids, scene_objects, active_leads)
        if not failures:
            item = _serialize_action_spec(spec)
            _attach_runtime_options(item, traveler_state, npc_ids, scene_objects, active_leads)
            available.append(item)
    return available


def get_unavailable_actions_with_reasons(
    traveler_state: dict[str, Any],
    npc_ids: list[str] | None = None,
    scene_objects: list[dict[str, Any]] | None = None,
    active_leads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return actions that fail preconditions, with reasons."""
    unavailable = []
    for spec in TRAVELER_ACTION_SPECS:
        failures = _check_preconditions(spec, traveler_state, npc_ids, scene_objects, active_leads)
        if failures:
            item = _serialize_action_spec(spec)
            _attach_runtime_options(item, traveler_state, npc_ids, scene_objects, active_leads)
            item["failed_preconditions"] = failures
            item["reason"] = "; ".join(failures)
            unavailable.append(item)
    return unavailable


def compute_action_biases(
    available_actions: list[dict[str, Any]],
    profile: TravelerProfile,
) -> list[ActionBias]:
    """Compute profile-driven biases for each available action.

    Each action gets a profile_alignment_score in [-1.0, 1.0] based on
    how well it matches the traveler's motivations, personality, and tendencies.
    """
    biases = []
    for action in available_actions:
        action_type = action["action_type"]
        supporting, opposing = _motivation_personality_match(action_type, profile)
        risk = _estimate_risk(action_type, profile)
        score = _compute_alignment_score(supporting, opposing, profile)
        biases.append(ActionBias(
            action_type=action_type,
            supporting_motivations=tuple(supporting),
            opposing_personality=tuple(opposing),
            risk_level=risk,
            profile_alignment_score=round(score, 3),
        ))
    return biases


# ── Precondition checking ──────────────────────────────────────────────

def _check_preconditions(
    spec: TravelerActionSpec,
    traveler_state: dict[str, Any],
    npc_ids: list[str] | None,
    scene_objects: list[dict[str, Any]] | None,
    active_leads: list[dict[str, Any]] | None,
) -> list[str]:
    failures = []
    for precondition in spec.preconditions:
        if not _precondition_met(precondition, traveler_state, npc_ids, scene_objects, active_leads):
            failures.append(_precondition_reason(precondition))
    return failures


def _precondition_met(
    precondition: str,
    traveler_state: dict[str, Any],
    npc_ids: list[str] | None,
    scene_objects: list[dict[str, Any]] | None,
    active_leads: list[dict[str, Any]] | None,
) -> bool:
    current_location = str(traveler_state.get("current_location", ""))
    inventory = list(traveler_state.get("inventory", []))

    if precondition == "location_exists":
        return True  # any location_id is accepted for now
    if precondition == "location_not_current":
        return True  # checked at action proposal time
    if precondition == "npc_exists":
        return bool(npc_ids)
    if precondition == "npc_same_location":
        return _any_npc_at_location(npc_ids or [], current_location)
    if precondition == "object_exists":
        return bool(scene_objects)
    if precondition == "object_same_location":
        return _any_object_at_location(scene_objects or [], current_location)
    if precondition == "object_not_destroyed":
        return True  # no destruction mechanic yet
    if precondition == "traveler_has_offered_item":
        return bool(inventory)
    if precondition == "evidence_recorded":
        return _has_recorded_evidence(traveler_state)
    if precondition == "lead_exists":
        return bool(active_leads)
    if precondition == "lead_not_expired":
        return bool(active_leads)
    return True


def _precondition_reason(precondition: str) -> str:
    reasons = {
        "location_exists": "location does not exist",
        "location_not_current": "already at this location",
        "npc_exists": "no NPCs available",
        "npc_same_location": "NPC is not at your current location",
        "object_exists": "no scene objects available",
        "object_same_location": "object is not at your current location",
        "object_not_destroyed": "object has been destroyed",
        "traveler_has_offered_item": "you have no items to trade",
        "evidence_recorded": "no evidence recorded yet",
        "lead_exists": "no active leads",
        "lead_not_expired": "lead has expired",
    }
    return reasons.get(precondition, f"precondition failed: {precondition}")


def _any_npc_at_location(npc_ids: list[str], location_id: str) -> bool:
    for npc_id in npc_ids:
        try:
            loc = database.get_npc_location_state(npc_id)
            if loc.get("location_id") == location_id:
                return True
        except Exception:
            continue
    return False


def _any_object_at_location(scene_objects: list[dict[str, Any]], location_id: str) -> bool:
    return any(obj.get("location_id") == location_id for obj in scene_objects)


def _has_recorded_evidence(traveler_state: dict[str, Any]) -> bool:
    notes = traveler_state.get("private_notes", [])
    return any("evidence" in str(note).lower() for note in notes)


def _attach_runtime_options(
    action: dict[str, Any],
    traveler_state: dict[str, Any],
    npc_ids: list[str] | None,
    scene_objects: list[dict[str, Any]] | None,
    active_leads: list[dict[str, Any]] | None,
) -> None:
    """Attach concrete argument choices for deterministic fallback and validation."""
    current_location = str(traveler_state.get("current_location", ""))
    action_type = action["action_type"]
    options: dict[str, list[str]] = {}

    if action_type == "move_to":
        locations = _known_locations()
        options["location_id"] = [loc for loc in locations if loc and loc != current_location]

    if action_type in {"talk_to", "ask_for_help", "share_information", "trade_with", "challenge_claim"}:
        options["npc_id"] = _npc_ids_at_location(npc_ids or [], current_location)

    if action_type == "investigate":
        options["target_id"] = [
            str(obj["object_id"])
            for obj in (scene_objects or [])
            if obj.get("location_id") == current_location and obj.get("object_id")
        ]

    if action_type == "trade_with":
        options["offered_item"] = [str(item) for item in traveler_state.get("inventory", []) if str(item)]

    if action_type == "follow_lead":
        options["lead_id"] = [
            str(lead.get("lead_id"))
            for lead in (active_leads or [])
            if lead.get("lead_id")
        ]

    if options:
        action["arg_options"] = options


def _known_locations() -> list[str]:
    locations: set[str] = set()
    try:
        locations.update(str(item["location_id"]) for item in database.list_npc_locations())
    except Exception:
        pass
    try:
        locations.update(str(item["location_id"]) for item in database.list_scene_objects())
    except Exception:
        pass
    return sorted(loc for loc in locations if loc)


def _npc_ids_at_location(npc_ids: list[str], location_id: str) -> list[str]:
    matches = []
    for npc_id in npc_ids:
        try:
            loc = database.get_npc_location_state(npc_id)
            if loc.get("location_id") == location_id:
                matches.append(str(npc_id))
        except Exception:
            continue
    return matches


# ── Bias helpers ───────────────────────────────────────────────────────

_ACTION_MOTIVATION_MAP: dict[str, list[str]] = {
    "move_to": ["curiosity", "safety"],
    "talk_to": ["curiosity", "truth_seeking", "loyalty"],
    "investigate": ["curiosity", "truth_seeking"],
    "ask_for_help": ["safety", "loyalty"],
    "share_information": ["truth_seeking", "loyalty", "prestige"],
    "trade_with": ["wealth", "power"],
    "challenge_claim": ["truth_seeking", "power"],
    "follow_lead": ["curiosity", "truth_seeking", "wealth"],
    "wait_and_observe": ["safety"],
    "record_private_note": ["truth_seeking", "safety"],
}

_ACTION_PERSONALITY_CONFLICT: dict[str, list[str]] = {
    "move_to": [],
    "talk_to": ["suspicious"],
    "investigate": [],
    "ask_for_help": ["cautious", "suspicious"],
    "share_information": ["cautious", "suspicious"],
    "trade_with": ["empathetic"],
    "challenge_claim": ["cautious", "empathetic"],
    "follow_lead": [],
    "wait_and_observe": ["bold"],
    "record_private_note": [],
}


def _motivation_personality_match(
    action_type: str,
    profile: TravelerProfile,
) -> tuple[list[str], list[str]]:
    mot_weights = {
        "curiosity": profile.motivations.curiosity,
        "wealth": profile.motivations.wealth,
        "prestige": profile.motivations.prestige,
        "safety": profile.motivations.safety,
        "loyalty": profile.motivations.loyalty,
        "truth_seeking": profile.motivations.truth_seeking,
        "power": profile.motivations.power,
    }
    pers_weights = {
        "cautious": profile.personality.cautious,
        "bold": profile.personality.bold,
        "empathetic": profile.personality.empathetic,
        "suspicious": profile.personality.suspicious,
        "patient": profile.personality.patient,
        "manipulative": profile.personality.manipulative,
    }
    supporting = [
        m for m in _ACTION_MOTIVATION_MAP.get(action_type, [])
        if mot_weights.get(m, 0.0) >= 0.5
    ]
    opposing = [
        p for p in _ACTION_PERSONALITY_CONFLICT.get(action_type, [])
        if pers_weights.get(p, 0.0) >= 0.5
    ]
    return supporting, opposing


def _estimate_risk(action_type: str, profile: TravelerProfile) -> str:
    high_risk_actions = {"challenge_claim", "share_information"}
    medium_risk_actions = {"talk_to", "ask_for_help", "trade_with", "follow_lead"}
    if action_type in high_risk_actions:
        return "medium" if profile.personality.cautious > 0.6 else "high"
    if action_type in medium_risk_actions:
        return "low" if profile.personality.cautious > 0.7 else "medium"
    return "low"


def _compute_alignment_score(
    supporting: list[str],
    opposing: list[str],
    profile: TravelerProfile,
) -> float:
    mot_weights = {
        "curiosity": profile.motivations.curiosity,
        "wealth": profile.motivations.wealth,
        "prestige": profile.motivations.prestige,
        "safety": profile.motivations.safety,
        "loyalty": profile.motivations.loyalty,
        "truth_seeking": profile.motivations.truth_seeking,
        "power": profile.motivations.power,
    }
    pers_weights = {
        "cautious": profile.personality.cautious,
        "bold": profile.personality.bold,
        "empathetic": profile.personality.empathetic,
        "suspicious": profile.personality.suspicious,
        "patient": profile.personality.patient,
        "manipulative": profile.personality.manipulative,
    }
    support_score = sum(mot_weights.get(m, 0.0) for m in supporting) / max(len(supporting), 1)
    oppose_score = sum(pers_weights.get(p, 0.0) for p in opposing) / max(len(opposing), 1)
    # Score ranges from -1 (fully opposed) to +1 (fully supported)
    if supporting and opposing:
        return support_score - oppose_score
    if supporting:
        return support_score
    if opposing:
        return -oppose_score
    return 0.0


def _serialize_action_spec(spec: TravelerActionSpec | dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec, dict):
        return dict(spec)
    return {
        "action_type": spec.action_type,
        "description": spec.description,
        "args_schema": dict(spec.args_schema),
        "preconditions": list(spec.preconditions),
        "effects": list(spec.effects),
        "forbidden_effects": list(spec.forbidden_effects),
        "prompt_hint": spec.prompt_hint,
    }


def serialize_actions_for_llm_prompt(
    actions: list[dict[str, Any]],
    biases: list[ActionBias] | None = None,
) -> list[dict[str, Any]]:
    """Serialize available actions with optional profile biases for LLM prompt."""
    bias_map: dict[str, ActionBias] = {}
    if biases:
        bias_map = {b.action_type: b for b in biases}

    result = []
    for action in actions:
        action_type = action["action_type"]
        item = {
            "action_type": action_type,
            "description": action["description"],
            "args_schema": action["args_schema"],
            "effects": action["effects"],
            "forbidden_effects": action["forbidden_effects"],
            "prompt_hint": action.get("prompt_hint"),
        }
        if "arg_options" in action:
            item["arg_options"] = action["arg_options"]
        if action_type in bias_map:
            b = bias_map[action_type]
            item["profile_alignment"] = {
                "score": b.profile_alignment_score,
                "supporting_motivations": list(b.supporting_motivations),
                "opposing_personality": list(b.opposing_personality),
                "risk_level": b.risk_level,
            }
        result.append(item)
    return result
