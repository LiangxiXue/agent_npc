from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.agent.llm_memory_candidate import generate_memory_candidates
from src.agent.memory_candidate_gate import player_helped_lina, validate_memory_candidate
from src.agent.memory_candidate_review import review_memory_candidates
from src.storage import database
from src.tools import sqlite_tools


@dataclass(frozen=True)
class MemoryPolicyInput:
    npc_id: str
    player_input: str
    npc_response: str
    retrieved_long_term_memories: list[dict[str, Any]]
    recent_short_term_context: list[dict[str, Any]]
    npc_before: dict[str, Any]
    npc_after: dict[str, Any]
    player_before: dict[str, Any]
    player_after: dict[str, Any]
    quest_before: dict[str, Any]
    quest_after: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    state_changes: list[dict[str, Any]]
    retrieved_lore: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MemoryCandidate:
    should_write: bool
    npc_id: str
    content: str
    memory_type: str
    importance: int
    tags: list[str]
    confidence: float
    reason: str
    evidence_text: str = ""
    source: str = "rule"


def apply_memory_policy(
    policy_input: MemoryPolicyInput,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate and persist long-term memories that pass policy checks."""
    candidates, llm_trace = build_memory_candidates_with_llm(policy_input)
    final_candidates: list[dict[str, Any]] = []
    memory_writes: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_dict = asdict(candidate)
        gate_result = validate_memory_candidate(candidate_dict, policy_input)
        candidate_dict["gate"] = gate_result
        if candidate.should_write and not gate_result["approved"]:
            candidate_dict["should_write"] = False
            candidate_dict["reason"] = gate_result["reason"]
            final_candidates.append(candidate_dict)
            continue
        if candidate.should_write:
            duplicate = database.find_similar_memory(
                npc_id=candidate.npc_id,
                content=candidate.content,
                memory_type=candidate.memory_type,
                tags=candidate.tags,
            )
            if duplicate is not None:
                candidate_dict["should_write"] = False
                candidate_dict["reason"] = "Similar memory already exists."
                candidate_dict["duplicate_memory_id"] = duplicate["id"]
                final_candidates.append(candidate_dict)
                continue

            execution = sqlite_tools.add_memory(
                npc_id=candidate.npc_id,
                content=candidate.content,
                importance=candidate.importance,
                tags=candidate.tags,
                memory_type=candidate.memory_type,
                confidence=candidate.confidence,
            )
            memory_writes.append(asdict(execution))

        final_candidates.append(candidate_dict)

    policy_result = {
        "candidates": final_candidates,
        "summary": summarize_policy_result(final_candidates, memory_writes),
        "llm_memory_policy": llm_trace,
    }
    return policy_result, memory_writes


def build_memory_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    candidates = build_rule_memory_candidates(policy_input)
    if candidates:
        return candidates
    return [
        MemoryCandidate(
            should_write=False,
            npc_id=policy_input.npc_id,
            content="",
            memory_type="none",
            importance=0,
            tags=[],
            confidence=0.0,
            reason="No long-term significant event detected.",
        )
    ]


def build_memory_candidates_with_llm(
    policy_input: MemoryPolicyInput,
) -> tuple[list[MemoryCandidate], dict[str, Any]]:
    rule_candidates = build_rule_memory_candidates(policy_input)
    rule_candidate_dicts = [asdict(candidate) for candidate in rule_candidates]
    llm_candidates, generation_trace = generate_memory_candidates(
        policy_input=policy_input,
        rule_candidates=rule_candidate_dicts,
    )
    combined = merge_candidate_dicts(rule_candidate_dicts, llm_candidates)
    if not combined:
        return build_memory_candidates(policy_input), {
            "candidate_generation": generation_trace,
            "candidate_review": {"enabled": False, "reason": "No write candidates to review."},
        }

    reviews, review_trace = review_memory_candidates(policy_input, combined)
    reviewed = apply_candidate_reviews(combined, reviews, policy_input.npc_id)
    if reviewed:
        return reviewed, {
            "candidate_generation": generation_trace,
            "candidate_review": review_trace,
        }

    return build_memory_candidates(policy_input), {
        "candidate_generation": generation_trace,
        "candidate_review": review_trace,
    }


def build_rule_memory_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    candidates.extend(build_quest_candidates(policy_input))
    candidates.extend(build_event_candidates(policy_input))
    candidates.extend(build_relationship_candidates(policy_input))
    candidates.extend(build_preference_candidates(policy_input))

    return candidates


def merge_candidate_dicts(
    rule_candidates: list[dict[str, Any]],
    llm_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in rule_candidates + llm_candidates:
        if not candidate.get("should_write"):
            continue
        key = (str(candidate.get("memory_type")), normalize_content(str(candidate.get("content", ""))))
        if key in seen:
            continue
        seen.add(key)
        merged.append(candidate)
    return merged


def apply_candidate_reviews(
    candidates: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    npc_id: str,
) -> list[MemoryCandidate]:
    reviewed: list[MemoryCandidate] = []
    for review in reviews:
        index = review.get("candidate_index")
        if not isinstance(index, int) or index < 0 or index >= len(candidates):
            continue
        original = candidates[index]
        if review.get("verdict") == "reject":
            rejected = dict(original)
            rejected["should_write"] = False
            rejected["reason"] = review.get("reason", "Rejected by memory review LLM.")
            rejected["review"] = review
            reviewed.append(dict_to_candidate(rejected, npc_id))
            continue

        revised = dict(original)
        revised.update(
            {
                "should_write": True,
                "npc_id": npc_id,
                "memory_type": review.get("approved_memory_type", original.get("memory_type")),
                "content": review.get("approved_content", original.get("content")),
                "importance": review.get("approved_importance", original.get("importance")),
                "confidence": review.get("approved_confidence", original.get("confidence")),
                "tags": review.get("approved_tags", original.get("tags", [])),
                "evidence_text": review.get("approved_evidence_text", original.get("evidence_text", "")),
                "reason": review.get("reason", "Approved by memory review LLM."),
                "source": f"{original.get('source', 'rule')}+llm_review",
                "review": review,
            }
        )
        reviewed.append(dict_to_candidate(revised, npc_id))
    return reviewed


def dict_to_candidate(candidate: dict[str, Any], npc_id: str) -> MemoryCandidate:
    tags = candidate.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return MemoryCandidate(
        should_write=bool(candidate.get("should_write", False)),
        npc_id=str(candidate.get("npc_id") or npc_id),
        content=str(candidate.get("content", "")).strip(),
        memory_type=str(candidate.get("memory_type", "event")).strip(),
        importance=clamp_int(candidate.get("importance", 5), 1, 10),
        tags=[str(tag).strip() for tag in tags if str(tag).strip()],
        confidence=clamp_float(candidate.get("confidence", 0.7), 0.0, 1.0),
        reason=str(candidate.get("reason", "")).strip(),
        evidence_text=str(candidate.get("evidence_text", "")).strip(),
        source=str(candidate.get("source", "rule")).strip(),
    )


def clamp_int(value: Any, lower: int, upper: int) -> int:
    try:
        return max(lower, min(upper, int(value)))
    except (TypeError, ValueError):
        return lower


def clamp_float(value: Any, lower: float, upper: float) -> float:
    try:
        return max(lower, min(upper, float(value)))
    except (TypeError, ValueError):
        return lower


def normalize_content(content: str) -> str:
    return " ".join(content.lower().strip().split())


def build_quest_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    if (
        policy_input.quest_before["status"] != "completed"
        and policy_input.quest_after["status"] == "completed"
    ):
        quest_id = policy_input.quest_after["quest_id"]
        npc_name = policy_input.npc_after.get("name", policy_input.npc_id)
        return [
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content=f"Player completed the {quest_id} quest for {npc_name}.",
                memory_type="quest",
                importance=9,
                tags=["quest", "completed", quest_id, policy_input.npc_id],
                confidence=1.0,
                reason="Quest status changed to completed.",
                evidence_text=str(policy_input.quest_after),
            )
        ]
    return []


def build_event_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    candidates = []
    tool_names = [tool["name"] for tool in policy_input.tool_calls]
    recorded_key_return = any(
        tool["name"] == "record_world_event"
        and "lost key" in str(tool["arguments"].get("content", "")).lower()
        for tool in policy_input.tool_calls
    )
    if (
        ("give_item" in tool_names or recorded_key_return)
        and policy_input.quest_after["quest_id"] == "lost_key"
    ):
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content="Player returned Lina's lost key.",
                memory_type="event",
                importance=8,
                tags=["event", "help", "lost_key"],
                confidence=1.0,
                reason="Tool execution granted the lost-key quest reward, indicating the key was returned.",
                evidence_text="Player returned Lina's lost key.",
            )
        )
    if "unlock_location" in tool_names:
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content="Lina revealed the underground ruins entrance to the player.",
                memory_type="event",
                importance=7,
                tags=["event", "ruins", "location"],
                confidence=1.0,
                reason="A sensitive location was unlocked.",
                evidence_text="unlock_location",
            )
        )
    recorded_events = [
        str(tool["arguments"].get("content", ""))
        for tool in policy_input.tool_calls
        if tool["name"] == "record_world_event"
    ]
    for event in recorded_events:
        normalized = event.lower()
        if "lost key" in normalized or "underground ruins entrance" in normalized:
            continue
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content=event,
                memory_type="event",
                importance=7,
                tags=["event", policy_input.npc_id, policy_input.quest_after["quest_id"]],
                confidence=0.95,
                reason="A world event was recorded for this NPC turn.",
                evidence_text=event,
            )
        )
    return candidates


def build_relationship_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    candidates = []
    trust_delta = policy_input.npc_after["trust"] - policy_input.npc_before["trust"]
    affection_delta = policy_input.npc_after["affection"] - policy_input.npc_before["affection"]
    helped_lina = player_helped_lina(policy_input)
    npc_name = policy_input.npc_after.get("name", policy_input.npc_id)

    if policy_input.npc_id == "lina" and trust_delta >= 5 and helped_lina:
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content="Lina trusts the player more because the player helped her.",
                memory_type="relationship",
                importance=7,
                tags=["relationship", "trust", "help"],
                confidence=0.95,
                reason=f"Trust increased by {trust_delta}.",
                evidence_text="Player returned Lina's lost key.",
            )
        )
    elif policy_input.npc_id != "lina" and trust_delta >= 5:
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content=f"{npc_name} trusts the player more after the player advanced the {policy_input.quest_after['quest_id']} task.",
                memory_type="relationship",
                importance=6,
                tags=["relationship", "trust", policy_input.npc_id, policy_input.quest_after["quest_id"]],
                confidence=0.9,
                reason=f"Trust increased by {trust_delta}.",
                evidence_text=str(policy_input.state_changes),
            )
        )
    if policy_input.npc_id == "lina" and affection_delta >= 5 and helped_lina:
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content="Lina feels more warmly toward the player after receiving help.",
                memory_type="relationship",
                importance=6,
                tags=["relationship", "affection", "help"],
                confidence=0.9,
                reason=f"Affection increased by {affection_delta}.",
                evidence_text="Player returned Lina's lost key.",
            )
        )
    elif policy_input.npc_id != "lina" and affection_delta >= 5:
        candidates.append(
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content=f"{npc_name} feels more positively toward the player after useful task progress.",
                memory_type="relationship",
                importance=5,
                tags=["relationship", "affection", policy_input.npc_id, policy_input.quest_after["quest_id"]],
                confidence=0.85,
                reason=f"Affection increased by {affection_delta}.",
                evidence_text=str(policy_input.state_changes),
            )
        )
    return candidates


def has_player_helped_lina(policy_input: MemoryPolicyInput) -> bool:
    return player_helped_lina(policy_input)


def build_preference_candidates(policy_input: MemoryPolicyInput) -> list[MemoryCandidate]:
    text = policy_input.player_input.lower()
    if any(phrase in text for phrase in ["直接告诉", "直接说", "不要绕弯", "别绕弯", "direct hints"]):
        return [
            MemoryCandidate(
                should_write=True,
                npc_id=policy_input.npc_id,
                content="Player prefers direct hints instead of vague clues.",
                memory_type="preference",
                importance=6,
                tags=["preference", "communication_style", "direct"],
                confidence=0.85,
                reason="Player explicitly expressed a stable communication preference.",
                evidence_text=policy_input.player_input,
            )
        ]
    return []


def summarize_policy_result(
    candidates: list[dict[str, Any]],
    memory_writes: list[dict[str, Any]],
) -> str:
    if memory_writes:
        return f"Wrote {len(memory_writes)} long-term memory record(s)."
    reasons = [candidate["reason"] for candidate in candidates if candidate.get("reason")]
    return reasons[0] if reasons else "No long-term memory written."
