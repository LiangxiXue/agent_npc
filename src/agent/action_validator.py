from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from src.agent.decision import apply_task_state_machine, validate_decision


class ActionValidator:
    """Validate proposed NPC actions before the environment can execute them."""

    def validate(self, action: Any, observation: Any) -> Any:
        try:
            validated_decision = apply_task_state_machine(
                validate_decision(deepcopy(action.raw_decision)),
                player_input=observation.player_input,
                npc_state=observation.npc_state,
                quest_state=observation.quest_state,
            )
        except ValueError as exc:
            validated_decision = rejected_decision(action.raw_decision, str(exc))
        return replace(
            action,
            intent=str(validated_decision["intent"]),
            subject=infer_subject(validated_decision),
            reason=str(validated_decision.get("reasoning", "")),
            response_style=str(validated_decision["response_style"]),
            response_keywords=list(validated_decision["response_keywords"]),
            social_intent=str(validated_decision.get("social_intent", "cooperate")),
            social_stance=deepcopy(validated_decision.get("social_stance", {})),
            proposed_effects=proposed_effects_from_tools(validated_decision.get("tools", [])),
            raw_decision=validated_decision,
        )


def proposed_effects_from_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "effect_type": tool.get("name", "unknown"),
            "args": deepcopy(tool.get("args", {})),
        }
        for tool in tools
    ]


def infer_subject(decision: dict[str, Any]) -> str:
    intent = str(decision.get("intent", "general_conversation"))
    if "ruins" in intent:
        return "underground_ruins_entrance"
    if "lost_key" in intent:
        return "lost_key"
    if "gate_badge" in intent:
        return "gate_badge"
    if "ancient_notes" in intent:
        return "ancient_notes"
    if "relic_tip" in intent:
        return "relic_tip"
    return "conversation"


def rejected_decision(original: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "intent": "probe_for_evidence",
        "reasoning": f"Environment validation rejected the proposed action: {reason}",
        "memory_policy": "Do not write task progress memory because the environment rejected the action.",
        "response_style": "cautious_state_guard",
        "response_keywords": ["动作被环境拒绝", "需要更多证据", "不能改变状态"],
        "tools": [],
        "social_intent": "probe",
        "social_stance": {
            "target": "player",
            "attitude": "cautious",
            "intensity": 0.65,
            "reason": "The proposed action failed environment validation.",
        },
        "state_machine": {
            "blocked": True,
            "original_intent": original.get("intent"),
            "reason": reason,
        },
    }
