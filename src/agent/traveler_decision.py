"""Traveler decision — profile-biased LLM decision with deterministic fallback."""

from __future__ import annotations

from typing import Any

from src.agent.llm_client import call_openai_compatible_json
from src.agent.traveler_actions import ActionBias, compute_action_biases
from src.agent.traveler_profile import TravelerProfile


TRAVELER_DECISION_SYSTEM_PROMPT = """
You are the decision layer for an autonomous Traveler agent in a living world simulation.
Return only a JSON object with exactly these keys:

{
  "selected_action": {"action_type": "<one from available_actions>", "args": {<matching args_schema>}},
  "decision_reason": "<why you chose this action>",
  "profile_alignment": {<which profile traits support this choice>},
  "profile_tension": {<which profile traits are in tension with this choice>},
  "deception_choice": null or {"type": "lie|omission|partial_disclosure", "claim": "<what was said>", "truth": "<the truth>"},
  "disclosure_choice": null or {"secret_id": "<id>", "level": "hinted|partial|full"},
  "expected_consequence": "<what you expect to happen>"
}

CRITICAL: You MUST wrap your selected action inside the "selected_action" key.
Example: {"selected_action": {"action_type": "talk_to", "args": {"npc_id": "mira", "topic": "ruins", "tone": "friendly", "honesty_level": "full", "disclosure": "none"}}, "decision_reason": "...", ...}

You may choose to lie, mislead, partially disclose, or fully disclose — but you must record
these choices. Lies only affect dialogue and events, never canonical world facts.
"""


def decide_traveler_action(
    profile: TravelerProfile,
    observation: dict[str, Any],
    available_actions: list[dict[str, Any]],
    unavailable_actions: list[dict[str, Any]] | None = None,
    use_llm: bool = True,
    allow_llm_fallback: bool = True,
) -> dict[str, Any]:
    """Select a Traveler action using profile-biased LLM or deterministic fallback.

    Returns a decision dict with keys:
        selected_action, decision_reason, profile_alignment, profile_tension,
        deception_choice, disclosure_choice, expected_consequence, mode
    """
    biases = compute_action_biases(available_actions, profile)

    if use_llm:
        try:
            return _call_llm_decision(
                profile,
                observation,
                available_actions,
                unavailable_actions,
                biases,
                allow_fallback=allow_llm_fallback,
            )
        except Exception:
            if not allow_llm_fallback:
                raise

    return deterministic_fallback_decision(available_actions, biases, profile)


def _call_llm_decision(
    profile: TravelerProfile,
    observation: dict[str, Any],
    available_actions: list[dict[str, Any]],
    unavailable_actions: list[dict[str, Any]] | None,
    biases: list[ActionBias],
    allow_fallback: bool = True,
) -> dict[str, Any]:
    from src.agent.traveler_actions import serialize_actions_for_llm_prompt

    payload = _build_decision_payload(profile, observation, available_actions, unavailable_actions, biases)
    result = call_openai_compatible_json(
        system_prompt=TRAVELER_DECISION_SYSTEM_PROMPT,
        user_payload=payload,
    )
    return _normalize_llm_decision(result, available_actions, biases, profile, allow_fallback=allow_fallback)


def _build_decision_payload(
    profile: TravelerProfile,
    observation: dict[str, Any],
    available_actions: list[dict[str, Any]],
    unavailable_actions: list[dict[str, Any]] | None,
    biases: list[ActionBias],
) -> dict[str, Any]:
    from src.agent.traveler_actions import serialize_actions_for_llm_prompt

    return {
        "traveler_profile": {
            "profile_id": profile.profile_id,
            "identity": {
                "public_name": profile.identity.public_name,
                "public_role": profile.identity.public_role,
                "cover_story": profile.identity.cover_story,
                "private_background": profile.identity.private_background,
            },
            "motivations": {
                "curiosity": profile.motivations.curiosity,
                "wealth": profile.motivations.wealth,
                "prestige": profile.motivations.prestige,
                "safety": profile.motivations.safety,
                "loyalty": profile.motivations.loyalty,
                "truth_seeking": profile.motivations.truth_seeking,
                "power": profile.motivations.power,
            },
            "personality": {
                "cautious": profile.personality.cautious,
                "bold": profile.personality.bold,
                "empathetic": profile.personality.empathetic,
                "suspicious": profile.personality.suspicious,
                "patient": profile.personality.patient,
                "manipulative": profile.personality.manipulative,
            },
            "social_tendencies": {
                "default_honesty": profile.social_tendencies.default_honesty,
                "trusts_authority": profile.social_tendencies.trusts_authority,
                "trusts_scholars": profile.social_tendencies.trusts_scholars,
                "trusts_merchants": profile.social_tendencies.trusts_merchants,
                "willing_to_lie": profile.social_tendencies.willing_to_lie,
                "willing_to_share_info": profile.social_tendencies.willing_to_share_info,
            },
            "exploration_style": {
                "primary_approach": profile.exploration_style.primary_approach,
                "avoids_public_attention": profile.exploration_style.avoids_public_attention,
            },
            "private_goals": [
                {"goal_id": g.goal_id, "description": g.description, "priority": g.priority}
                for g in profile.private_goals
            ],
            "secrets": [
                {"secret_id": s.secret_id, "label": s.label, "risk_level": s.risk_level}
                for s in profile.secrets
            ],
            "hard_boundaries": list(profile.boundaries.hard),
        },
        "world_state": observation,
        "available_actions": serialize_actions_for_llm_prompt(available_actions, biases),
        "unavailable_actions": unavailable_actions or [],
    }


def _normalize_llm_decision(
    raw: dict[str, Any],
    available_actions: list[dict[str, Any]],
    biases: list[ActionBias],
    profile: TravelerProfile,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    # Accept both {"selected_action": {...}} and direct action shapes
    selected = raw.get("selected_action")
    if not isinstance(selected, dict):
        # Maybe the LLM returned the action directly without wrapping
        if isinstance(raw.get("action_type"), str) and isinstance(raw.get("args"), dict):
            selected = {"action_type": raw["action_type"], "args": raw["args"]}
        else:
            if not allow_fallback:
                raise ValueError("LLM decision missing selected_action.")
            return deterministic_fallback_decision(available_actions, biases, profile)

    action_type = str(selected.get("action_type", ""))
    args = selected.get("args") if isinstance(selected.get("args"), dict) else {}

    # Validate that the selected action_type is in available_actions
    available_types = {a["action_type"] for a in available_actions}
    if action_type not in available_types:
        if not allow_fallback:
            raise ValueError(f"LLM selected unavailable action '{action_type}'.")
        return deterministic_fallback_decision(available_actions, biases, profile)

    return {
        "selected_action": {"action_type": action_type, "args": args},
        "decision_reason": str(raw.get("decision_reason", "")),
        "profile_alignment": raw.get("profile_alignment") if isinstance(raw.get("profile_alignment"), dict) else {},
        "profile_tension": raw.get("profile_tension") if isinstance(raw.get("profile_tension"), dict) else {},
        "deception_choice": raw.get("deception_choice") if isinstance(raw.get("deception_choice"), dict) else None,
        "disclosure_choice": raw.get("disclosure_choice") if isinstance(raw.get("disclosure_choice"), dict) else None,
        "expected_consequence": str(raw.get("expected_consequence", "")),
        "mode": "llm",
    }


def deterministic_fallback_decision(
    available_actions: list[dict[str, Any]],
    biases: list[ActionBias] | None = None,
    profile: TravelerProfile | None = None,
) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable or fails.

    Selects the action with the highest profile_alignment_score.
    If no biases available, picks the first safe action (wait_and_observe or record_private_note).
    """
    if biases and available_actions:
        bias_map = {b.action_type: b for b in biases}
        scored = [
            (a, bias_map.get(a["action_type"], ActionBias(a["action_type"], (), (), "low", 0.0)))
            for a in available_actions
        ]
        scored.sort(key=lambda pair: pair[1].profile_alignment_score, reverse=True)
        best_action, best_bias = scored[0]
        return {
            "selected_action": {
                "action_type": best_action["action_type"],
                "args": _default_args_for_action(best_action),
            },
            "decision_reason": (
                f"Deterministic fallback: selected '{best_action['action_type']}' "
                f"with alignment score {best_bias.profile_alignment_score}."
            ),
            "profile_alignment": {
                "supporting": list(best_bias.supporting_motivations),
                "opposing": list(best_bias.opposing_personality),
            },
            "profile_tension": {},
            "deception_choice": None,
            "disclosure_choice": None,
            "expected_consequence": f"The traveler will {best_action['action_type']}.",
            "mode": "deterministic_fallback",
        }

    # Ultimate fallback: wait_and_observe
    return {
        "selected_action": {"action_type": "wait_and_observe", "args": {}},
        "decision_reason": "Deterministic fallback: no actions available, waiting and observing.",
        "profile_alignment": {},
        "profile_tension": {},
        "deception_choice": None,
        "disclosure_choice": None,
        "expected_consequence": "The traveler will wait and observe.",
        "mode": "deterministic_fallback",
    }


def _default_args_for_action(action: dict[str, Any]) -> dict[str, Any]:
    schema = action.get("args_schema", {})
    if not isinstance(schema, dict):
        return {}
    options = action.get("arg_options") if isinstance(action.get("arg_options"), dict) else {}
    args = {}
    for field, expected_type in schema.items():
        field_options = options.get(field) if isinstance(options.get(field), list) else []
        if field_options:
            args[field] = str(field_options[0])
        elif expected_type == "string":
            args[field] = _fallback_string_arg(action.get("action_type", ""), field)
        elif expected_type == "integer":
            args[field] = 0
    return args


def _fallback_string_arg(action_type: str, field: str) -> str:
    defaults = {
        ("talk_to", "topic"): "local ruins",
        ("talk_to", "tone"): "neutral",
        ("talk_to", "honesty_level"): "full",
        ("talk_to", "disclosure"): "none",
        ("investigate", "method"): "careful observation",
        ("ask_for_help", "request"): "guidance about the ruins",
        ("ask_for_help", "honesty_level"): "full",
        ("share_information", "claim"): "I am trying to understand the ruins safely.",
        ("share_information", "honesty_level"): "full",
        ("trade_with", "requested_info"): "information about the ruins",
        ("record_private_note", "content"): "Record current observations for later review.",
    }
    return defaults.get((action_type, field), "")
