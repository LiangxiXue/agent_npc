from __future__ import annotations

from typing import Any


ALLOWED_MEMORY_TYPES = {"quest", "event", "relationship", "preference", "player_profile"}


def validate_memory_candidate(
    candidate: dict[str, Any],
    policy_input: Any,
) -> dict[str, Any]:
    """Apply non-negotiable checks before a memory candidate can be persisted."""
    if not candidate.get("should_write"):
        return {"approved": False, "reason": candidate.get("reason", "Candidate does not request a write.")}

    memory_type = candidate.get("memory_type")
    if memory_type not in ALLOWED_MEMORY_TYPES:
        return {"approved": False, "reason": f"Unsupported memory_type: {memory_type}."}

    content = str(candidate.get("content", "")).strip()
    if not content:
        return {"approved": False, "reason": "Memory content is empty."}
    if len(content) > 320:
        return {"approved": False, "reason": "Memory content is too long."}

    try:
        importance = int(candidate.get("importance", 0))
        confidence = float(candidate.get("confidence", 0.0))
    except (TypeError, ValueError):
        return {"approved": False, "reason": "Importance or confidence has an invalid type."}
    if not 1 <= importance <= 10:
        return {"approved": False, "reason": "Importance must be between 1 and 10."}
    if not 0.0 <= confidence <= 1.0:
        return {"approved": False, "reason": "Confidence must be between 0 and 1."}

    tags = candidate.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        return {"approved": False, "reason": "Tags must be an array of strings."}

    source = candidate.get("source", "rule")
    evidence_text = str(candidate.get("evidence_text", "")).strip()
    if source.startswith("llm") and not evidence_is_supported(evidence_text, policy_input):
        return {
            "approved": False,
            "reason": "LLM candidate evidence_text is missing or not found in this turn's evidence.",
        }

    if memory_type in {"player_profile", "preference"}:
        if not evidence_is_from_player(evidence_text or content, policy_input):
            return {
                "approved": False,
                "reason": f"{memory_type} memories must be grounded in the player's own words.",
            }
        return {"approved": True, "reason": "Candidate passed player-grounded memory checks."}

    if memory_type == "quest":
        if quest_completed_this_turn(policy_input):
            return {"approved": True, "reason": "Quest memory is supported by quest state transition."}
        return {"approved": False, "reason": "Quest memory lacks a supporting quest state transition."}

    if memory_type == "event":
        if event_supported_by_tools(candidate, policy_input):
            return {"approved": True, "reason": "Event memory is supported by tool execution."}
        return {"approved": False, "reason": "Event memory lacks supporting tool execution."}

    if memory_type == "relationship":
        if not relationship_state_changed(policy_input):
            return {"approved": False, "reason": "Relationship memory lacks trust or affection state change."}
        if mentions_help(candidate) and not player_helped_lina(policy_input):
            return {"approved": False, "reason": "Help-based relationship memory lacks player-helped-Lina evidence."}
        return {"approved": True, "reason": "Relationship memory is supported by relationship state change."}

    return {"approved": False, "reason": "Unhandled memory candidate type."}


def evidence_is_supported(evidence_text: str, policy_input: Any) -> bool:
    if not evidence_text:
        return False
    needle = normalize(evidence_text)
    return needle in normalize(build_evidence_corpus(policy_input))


def evidence_is_from_player(evidence_text: str, policy_input: Any) -> bool:
    if not evidence_text:
        return False
    return normalize(evidence_text) in normalize(policy_input.player_input)


def build_evidence_corpus(policy_input: Any) -> str:
    tool_text = " ".join(
        [
            str(tool.get("name", ""))
            + " "
            + str(tool.get("arguments", ""))
            + " "
            + str(tool.get("result", ""))
            for tool in policy_input.tool_calls
        ]
    )
    state_text = " ".join(str(change) for change in policy_input.state_changes)
    return " ".join(
        [
            policy_input.player_input,
            policy_input.npc_response,
            tool_text,
            state_text,
        ]
    )


def quest_completed_this_turn(policy_input: Any) -> bool:
    return (
        policy_input.quest_before["status"] != "completed"
        and policy_input.quest_after["status"] == "completed"
    )


def event_supported_by_tools(candidate: dict[str, Any], policy_input: Any) -> bool:
    tool_names = [tool["name"] for tool in policy_input.tool_calls]
    content = normalize(candidate.get("content", ""))
    if "lost key" in content or "lost_key" in content:
        return player_helped_lina(policy_input)
    if any(token in content for token in ["redirect", "suspicious relic", "relic lead", "unofficial ruins"]):
        return "record_world_event" in tool_names
    if "ruins" in content or "entrance" in content or "遗迹" in content or "入口" in content:
        return "unlock_location" in tool_names
    return any(name in tool_names for name in ["record_world_event", "give_item", "unlock_location"])


def relationship_state_changed(policy_input: Any) -> bool:
    return any(
        change.get("scope") == "npc" and change.get("field") in {"trust", "affection"}
        for change in policy_input.state_changes
    )


def mentions_help(candidate: dict[str, Any]) -> bool:
    searchable = normalize(
        " ".join(
            [
                str(candidate.get("content", "")),
                " ".join(str(tag) for tag in candidate.get("tags", [])),
            ]
        )
    )
    return any(token in searchable for token in ["help", "helped", "receiving help", "lost key", "lost_key", "帮助"])


def player_helped_lina(policy_input: Any) -> bool:
    tool_names = [tool["name"] for tool in policy_input.tool_calls]
    if "give_item" in tool_names and policy_input.quest_after["quest_id"] == "lost_key":
        return True
    if quest_completed_this_turn(policy_input):
        return True
    return any(
        tool["name"] == "record_world_event"
        and "player returned lina's lost key" in normalize(tool["arguments"].get("content", ""))
        for tool in policy_input.tool_calls
    )


def normalize(text: Any) -> str:
    return " ".join(str(text).lower().strip().split())
