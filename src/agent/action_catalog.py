from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.storage import database


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    description: str
    args_schema: dict[str, Any]
    allowed_npcs: list[str] | str
    preconditions: list[str]
    effects: list[str]
    forbidden_effects: list[str]
    prompt_hint: str | None = None


def get_available_actions(
    npc_id: str,
    trigger_event: dict[str, Any] | None = None,
    observation: Any | None = None,
) -> list[dict[str, Any]]:
    return [
        serialize_action(spec)
        for spec in get_action_specs_for_npc(npc_id)
        if not evaluate_preconditions(spec, npc_id, trigger_event, observation)
    ]


def get_unavailable_actions_with_reasons(
    npc_id: str,
    trigger_event: dict[str, Any] | None = None,
    observation: Any | None = None,
) -> list[dict[str, Any]]:
    unavailable = []
    for spec in get_action_specs_for_npc(npc_id):
        failures = evaluate_preconditions(spec, npc_id, trigger_event, observation)
        if not failures:
            continue
        item = serialize_action(spec)
        item["failed_preconditions"] = failures
        item["reason"] = "; ".join(precondition_reason(failure, npc_id) for failure in failures)
        unavailable.append(item)
    return unavailable


def serialize_actions_for_llm_prompt(actions: list[dict[str, Any] | ActionSpec]) -> list[dict[str, Any]]:
    serialized = []
    for action in actions:
        item = serialize_action(action) if isinstance(action, ActionSpec) else dict(action)
        serialized.append(
            {
                "action_type": item["action_type"],
                "description": item["description"],
                "args_schema": item["args_schema"],
                "effects": item["effects"],
                "forbidden_effects": item["forbidden_effects"],
                "prompt_hint": item.get("prompt_hint"),
            }
        )
    return serialized


def get_action_specs_for_npc(npc_id: str) -> list[ActionSpec]:
    specs = []
    for spec in ACTION_SPECS:
        allowed = spec.allowed_npcs
        if allowed == "*" or npc_id in allowed:
            specs.append(spec)
    return specs


def evaluate_preconditions(
    spec: ActionSpec,
    npc_id: str,
    trigger_event: dict[str, Any] | None,
    observation: Any | None,
) -> list[str]:
    return [
        precondition
        for precondition in spec.preconditions
        if not precondition_is_met(precondition, npc_id, trigger_event, observation)
    ]


def precondition_is_met(
    precondition: str,
    npc_id: str,
    trigger_event: dict[str, Any] | None,
    observation: Any | None,
) -> bool:
    event_type = str((trigger_event or {}).get("event_type", ""))
    if precondition == "lina_trust_at_least_60":
        return int(database.get_npc(npc_id).get("trust", 0)) >= 60
    if precondition == "badge_evidence_verified":
        return event_type == "badge_evidence_verified" or event_payload_has(trigger_event, "badge_evidence_verified")
    if precondition == "trust_task_completed":
        return event_type == "trust_task_completed" or database.get_quest("lost_key")["status"] == "completed"
    return True


def event_payload_has(trigger_event: dict[str, Any] | None, key: str) -> bool:
    payload = (trigger_event or {}).get("payload")
    return isinstance(payload, dict) and bool(payload.get(key))


def precondition_reason(precondition: str, npc_id: str) -> str:
    if precondition == "lina_trust_at_least_60":
        return "Lina trust below 60"
    if precondition == "badge_evidence_verified":
        return "badge evidence missing"
    if precondition == "trust_task_completed":
        return "trust task is not complete"
    return f"precondition failed: {precondition}"


def serialize_action(spec: ActionSpec | dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec, dict):
        return dict(spec)
    payload = asdict(spec)
    payload["allowed_npcs"] = spec.allowed_npcs
    return payload


SABLE_FORBIDDEN_EFFECTS = [
    "unlock_location",
    "complete_quest",
    "modify_other_npc_trust",
    "grant_gate_access",
    "rewrite_lore_fact",
]


ACTION_SPECS = [
    ActionSpec(
        action_type="ask_clarifying_question",
        description="Ask why the player wants restricted ruins knowledge before escalating.",
        args_schema={"message_intent": "string"},
        allowed_npcs=["lina"],
        preconditions=[],
        effects=["proactive_message"],
        forbidden_effects=["unlock_location", "complete_quest"],
        prompt_hint="Use when Lina needs motive before revealing anything.",
    ),
    ActionSpec(
        action_type="offer_minor_task",
        description="Offer a small trust test before discussing restricted ruins information.",
        args_schema={"quest_id": "string", "message_intent": "string"},
        allowed_npcs=["lina"],
        preconditions=[],
        effects=["start_or_update_plan", "proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use for player_asked_ruins_too_early.",
    ),
    ActionSpec(
        action_type="refuse_restricted_info",
        description="Refuse to reveal restricted information while staying in character.",
        args_schema={"message_intent": "string"},
        allowed_npcs=["lina"],
        preconditions=[],
        effects=["proactive_message"],
        forbidden_effects=["unlock_location", "complete_quest"],
        prompt_hint="Use when trust is too low and no trust test should start.",
    ),
    ActionSpec(
        action_type="reveal_partial_lore",
        description="Reveal a limited, non-unlocking lore clue once Lina trusts the player.",
        args_schema={"lore_scope": "string", "message_intent": "string"},
        allowed_npcs=["lina"],
        preconditions=["lina_trust_at_least_60"],
        effects=["proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Only safe after Lina trust reaches the threshold.",
    ),
    ActionSpec(
        action_type="update_trust_after_task",
        description="Update Lina's trust after a completed trust task.",
        args_schema={"npc_id": "string", "delta": "integer", "evidence": "string"},
        allowed_npcs=["lina"],
        preconditions=["trust_task_completed"],
        effects=["update_trust"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use only when the environment already confirms the task result.",
    ),
    ActionSpec(
        action_type="verify_badge",
        description="Verify badge evidence and keep gate security procedural.",
        args_schema={"evidence_id": "string", "message_intent": "string"},
        allowed_npcs=["ron"],
        preconditions=[],
        effects=["proactive_message", "plan_update"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use when Ron needs to inspect evidence before access.",
    ),
    ActionSpec(
        action_type="block_gate_access",
        description="Block gate access until evidence is verified.",
        args_schema={"reason": "string"},
        allowed_npcs=["ron"],
        preconditions=[],
        effects=["proactive_message", "plan_blocker"],
        forbidden_effects=["unlock_location", "complete_quest"],
        prompt_hint="Use when badge evidence is missing.",
    ),
    ActionSpec(
        action_type="grant_conditional_access",
        description="Grant conditional procedural access after badge evidence is verified.",
        args_schema={"quest_id": "string", "message_intent": "string"},
        allowed_npcs=["ron"],
        preconditions=["badge_evidence_verified"],
        effects=["update_quest_status", "proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Only available after badge_evidence_verified.",
    ),
    ActionSpec(
        action_type="warn_player",
        description="Warn the player about gate procedure and restricted areas.",
        args_schema={"message_intent": "string"},
        allowed_npcs=["ron"],
        preconditions=[],
        effects=["proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use for safety reminders.",
    ),
    ActionSpec(
        action_type="request_evidence",
        description="Request specific evidence before advancing gate access.",
        args_schema={"evidence_type": "string", "message_intent": "string"},
        allowed_npcs=["ron"],
        preconditions=[],
        effects=["proactive_message", "plan_blocker"],
        forbidden_effects=["unlock_location", "complete_quest"],
        prompt_hint="Use when badge evidence is missing.",
    ),
    ActionSpec(
        action_type="inspect_clue",
        description="Inspect a new ruins clue without changing world facts.",
        args_schema={"clue_id": "string", "message_intent": "string"},
        allowed_npcs=["mira"],
        preconditions=[],
        effects=["memory_candidate", "proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use for new observed clue events.",
    ),
    ActionSpec(
        action_type="connect_evidence",
        description="Connect visible evidence with existing ruins research.",
        args_schema={"evidence_summary": "string"},
        allowed_npcs=["mira"],
        preconditions=[],
        effects=["reflection", "memory_candidate"],
        forbidden_effects=["rewrite_lore_fact"],
        prompt_hint="Use to form hypotheses, not facts.",
    ),
    ActionSpec(
        action_type="archive_memory",
        description="Archive a relevant observation for later research.",
        args_schema={"memory_candidate": "string"},
        allowed_npcs=["mira"],
        preconditions=[],
        effects=["memory_candidate"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use for low-urgency research events.",
    ),
    ActionSpec(
        action_type="suggest_next_investigation",
        description="Suggest a safe next investigation step.",
        args_schema={"message_intent": "string"},
        allowed_npcs=["mira"],
        preconditions=[],
        effects=["proactive_message"],
        forbidden_effects=["unlock_location"],
        prompt_hint="Use after Mira has a grounded clue.",
    ),
    ActionSpec(
        action_type="mislead_player",
        description="Give a plausible but non-authoritative misdirection.",
        args_schema={"message_intent": "string", "false_clue_theme": "string"},
        allowed_npcs=["sable"],
        preconditions=[],
        effects=["proactive_message", "memory_candidate"],
        forbidden_effects=SABLE_FORBIDDEN_EFFECTS,
        prompt_hint="Use when Sable wants leverage without mechanical authority.",
    ),
    ActionSpec(
        action_type="redirect_to_false_clue",
        description="Redirect the player toward an unofficial and unreliable lead.",
        args_schema={"message_intent": "string", "redirect_target": "string"},
        allowed_npcs=["sable"],
        preconditions=[],
        effects=["proactive_message"],
        forbidden_effects=SABLE_FORBIDDEN_EFFECTS,
        prompt_hint="Use for active ruins interest.",
    ),
    ActionSpec(
        action_type="ask_leading_question",
        description="Ask a leading question to learn what the player knows.",
        args_schema={"question_focus": "string"},
        allowed_npcs=["sable"],
        preconditions=[],
        effects=["proactive_message", "memory_candidate"],
        forbidden_effects=SABLE_FORBIDDEN_EFFECTS,
        prompt_hint="Use when Sable probes for exploitable secrets.",
    ),
    ActionSpec(
        action_type="probe_player_secret",
        description="Probe for the player's hidden ruins knowledge.",
        args_schema={"probe_topic": "string"},
        allowed_npcs=["sable"],
        preconditions=[],
        effects=["memory_candidate", "proactive_message"],
        forbidden_effects=SABLE_FORBIDDEN_EFFECTS,
        prompt_hint="Use when the player may know a valuable lead.",
    ),
]
