from __future__ import annotations

from typing import Any

from src.agent.llm_client import call_openai_compatible_json
from src.agent.llm_memory_candidate import memory_llm_enabled


MEMORY_REVIEW_SYSTEM_PROMPT = """
You are the memory candidate review agent for a memory-driven NPC system.

You review proposed long-term memory candidates. You do not write to the database.

Return one JSON object:
{
  "reviews": [
    {
      "candidate_index": 0,
      "verdict": "approve|reject|revise",
      "approved_memory_type": "player_profile|preference|relationship|event|quest",
      "approved_content": "short factual memory in English",
      "approved_importance": 1,
      "approved_confidence": 0.0,
      "approved_tags": ["short_tag"],
      "approved_evidence_text": "exact quote from current turn evidence",
      "reason": "short reason",
      "risk": "low|medium|high"
    }
  ]
}

Review rules:
- Reject or revise subject confusion. "Player needs help" is not "player helped an NPC".
- player_profile and preference must be grounded in the player's own words.
- event, quest, and relationship must be supported by tool calls, state changes, or explicit current-turn evidence.
- Do not approve speculative psychology as fact.
- Prefer revise when a candidate is useful but has the wrong type or overreaches.
- The approved_evidence_text must be exact evidence from the current turn.
"""


def review_memory_candidates(
    policy_input: Any,
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not candidates:
        return [], {"enabled": False, "stage": "candidate_review", "reason": "No candidates to review."}
    if not memory_llm_enabled():
        return pass_through_reviews(candidates), {
            "enabled": False,
            "stage": "candidate_review",
            "reason": "Memory LLM disabled or not configured.",
        }

    payload = {
        "player_input": policy_input.player_input,
        "npc_response": policy_input.npc_response,
        "retrieved_lore": policy_input.retrieved_lore,
        "tool_calls": policy_input.tool_calls,
        "state_changes": policy_input.state_changes,
        "state_before": {
            "npc": policy_input.npc_before,
            "player": policy_input.player_before,
            "quest": policy_input.quest_before,
        },
        "state_after": {
            "npc": policy_input.npc_after,
            "player": policy_input.player_after,
            "quest": policy_input.quest_after,
        },
        "candidates": [
            {
                "candidate_index": index,
                **candidate,
            }
            for index, candidate in enumerate(candidates)
        ],
    }
    try:
        response = call_openai_compatible_json(
            system_prompt=MEMORY_REVIEW_SYSTEM_PROMPT,
            user_payload=payload,
        )
    except Exception as exc:
        return pass_through_reviews(candidates), {
            "enabled": True,
            "stage": "candidate_review",
            "status": "error",
            "reason": str(exc),
        }

    reviews = normalize_reviews(response.get("reviews", []), candidates)
    return reviews, {
        "enabled": True,
        "stage": "candidate_review",
        "status": "ok",
        "review_count": len(reviews),
    }


def pass_through_reviews(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_index": index,
            "verdict": "approve",
            "approved_memory_type": candidate.get("memory_type"),
            "approved_content": candidate.get("content"),
            "approved_importance": candidate.get("importance"),
            "approved_confidence": candidate.get("confidence"),
            "approved_tags": candidate.get("tags", []),
            "approved_evidence_text": candidate.get("evidence_text", ""),
            "reason": "Passed through because memory LLM review is disabled.",
            "risk": "low",
        }
        for index, candidate in enumerate(candidates)
    ]


def normalize_reviews(raw_reviews: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw_reviews, list):
        return pass_through_reviews(candidates)
    by_index: dict[int, dict[str, Any]] = {}
    for review in raw_reviews:
        if not isinstance(review, dict):
            continue
        try:
            index = int(review.get("candidate_index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(candidates):
            by_index[index] = normalize_review(review, index, candidates[index])
    return [
        by_index.get(index)
        or {
            "candidate_index": index,
            "verdict": "reject",
            "approved_memory_type": candidates[index].get("memory_type"),
            "approved_content": candidates[index].get("content"),
            "approved_importance": candidates[index].get("importance"),
            "approved_confidence": candidates[index].get("confidence"),
            "approved_tags": candidates[index].get("tags", []),
            "approved_evidence_text": candidates[index].get("evidence_text", ""),
            "reason": "Review agent did not return a review for this candidate.",
            "risk": "medium",
        }
        for index in range(len(candidates))
    ]


def normalize_review(review: dict[str, Any], index: int, candidate: dict[str, Any]) -> dict[str, Any]:
    verdict = str(review.get("verdict", "reject")).strip().lower()
    if verdict not in {"approve", "reject", "revise"}:
        verdict = "reject"
    tags = review.get("approved_tags", candidate.get("tags", []))
    if not isinstance(tags, list):
        tags = []
    return {
        "candidate_index": index,
        "verdict": verdict,
        "approved_memory_type": str(review.get("approved_memory_type", candidate.get("memory_type", ""))).strip(),
        "approved_content": str(review.get("approved_content", candidate.get("content", ""))).strip(),
        "approved_importance": review.get("approved_importance", candidate.get("importance", 5)),
        "approved_confidence": review.get("approved_confidence", candidate.get("confidence", 0.7)),
        "approved_tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        "approved_evidence_text": str(
            review.get("approved_evidence_text", candidate.get("evidence_text", ""))
        ).strip(),
        "reason": str(review.get("reason", "Reviewed by memory review LLM.")).strip(),
        "risk": str(review.get("risk", "medium")).strip().lower(),
    }
