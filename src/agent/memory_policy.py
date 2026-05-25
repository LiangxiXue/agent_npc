from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.agent.llm_memory_candidate import generate_memory_candidates
from src.agent.memory_candidate_gate import validate_memory_candidate
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
    facets: list[str]
    scope: str
    confidence: float
    stability: float
    future_usefulness: float
    reason: str
    evidence_text: str = ""
    source: str = "llm_candidate"


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
                facets=candidate.facets,
                scope=candidate.scope,
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
                facets=candidate.facets,
                scope=candidate.scope,
                evidence_text=candidate.evidence_text,
                stability=candidate.stability,
                future_usefulness=candidate.future_usefulness,
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
    return [
        MemoryCandidate(
            should_write=False,
            npc_id=policy_input.npc_id,
            content="",
            memory_type="none",
            importance=0,
            tags=[],
            facets=[],
            scope="npc_specific",
            confidence=0.0,
            stability=0.0,
            future_usefulness=0.0,
            reason="No long-term significant event detected.",
        )
    ]


def build_memory_candidates_with_llm(
    policy_input: MemoryPolicyInput,
) -> tuple[list[MemoryCandidate], dict[str, Any]]:
    llm_candidates, generation_trace = generate_memory_candidates(
        policy_input=policy_input,
        rule_candidates=[],
    )
    combined = merge_candidate_dicts([], llm_candidates)
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
    """Rules no longer author memory candidates; they only live in gate validation."""
    return []


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
                "facets": review.get("approved_facets", original.get("facets", original.get("tags", []))),
                "scope": review.get("approved_scope", original.get("scope", "npc_specific")),
                "evidence_text": review.get("approved_evidence_text", original.get("evidence_text", "")),
                "stability": review.get("approved_stability", original.get("stability", 0.5)),
                "future_usefulness": review.get(
                    "approved_future_usefulness", original.get("future_usefulness", 0.5)
                ),
                "reason": review.get("reason", "Approved by memory review LLM."),
                "source": f"{original.get('source', 'llm_candidate')}+llm_review",
                "review": review,
            }
        )
        reviewed.append(dict_to_candidate(revised, npc_id))
    return reviewed


def dict_to_candidate(candidate: dict[str, Any], npc_id: str) -> MemoryCandidate:
    tags = candidate.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    facets = candidate.get("facets", tags)
    if not isinstance(facets, list):
        facets = []
    return MemoryCandidate(
        should_write=bool(candidate.get("should_write", False)),
        npc_id=str(candidate.get("npc_id") or npc_id),
        content=str(candidate.get("content", "")).strip(),
        memory_type=normalize_memory_type(candidate.get("memory_type", "episodic")),
        importance=clamp_int(candidate.get("importance", 5), 1, 10),
        tags=[str(tag).strip() for tag in tags if str(tag).strip()],
        facets=[str(facet).strip() for facet in facets if str(facet).strip()],
        scope=normalize_scope(candidate.get("scope", "npc_specific")),
        confidence=clamp_float(candidate.get("confidence", 0.7), 0.0, 1.0),
        stability=clamp_float(candidate.get("stability", 0.5), 0.0, 1.0),
        future_usefulness=clamp_float(candidate.get("future_usefulness", 0.5), 0.0, 1.0),
        reason=str(candidate.get("reason", "")).strip(),
        evidence_text=str(candidate.get("evidence_text", "")).strip(),
        source=str(candidate.get("source", "llm_candidate")).strip(),
    )


def normalize_memory_type(value: Any) -> str:
    mapping = {
        "quest": "episodic",
        "event": "episodic",
        "relationship": "relational",
        "preference": "procedural",
        "player_profile": "semantic",
    }
    memory_type = str(value).strip()
    normalized = mapping.get(memory_type, memory_type)
    return normalized if normalized in {"semantic", "episodic", "relational", "procedural", "none"} else "episodic"


def normalize_scope(value: Any) -> str:
    scope = str(value).strip()
    return scope if scope in {"npc_specific", "player_global"} else "npc_specific"


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


def summarize_policy_result(
    candidates: list[dict[str, Any]],
    memory_writes: list[dict[str, Any]],
) -> str:
    if memory_writes:
        return f"Wrote {len(memory_writes)} long-term memory record(s)."
    reasons = [candidate["reason"] for candidate in candidates if candidate.get("reason")]
    return reasons[0] if reasons else "No long-term memory written."
