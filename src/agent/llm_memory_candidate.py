from __future__ import annotations

import os
from typing import Any

from src.agent.llm_client import call_openai_compatible_json, get_llm_settings


MEMORY_CANDIDATE_SYSTEM_PROMPT = """
You generate long-term memory candidates for a memory-driven NPC agent.

You do not write to the database. You only propose candidates.

Return one JSON object:
{
  "candidates": [
    {
      "should_write": true,
      "memory_type": "semantic|episodic|relational|procedural",
      "content": "short factual memory in English",
      "importance": 1,
      "confidence": 0.0,
      "tags": ["short_tag"],
      "facets": ["short_facet"],
      "scope": "npc_specific|player_global",
      "evidence_text": "exact quote from player_input, npc_response, tool calls, or state_changes",
      "stability": 0.0,
      "future_usefulness": 0.0,
      "reason": "short reason"
    }
  ]
}

Rules:
- Use semantic for stable player facts, profile details, values, or player knowledge.
- Use episodic for concrete events supported by tool calls, state changes, or world event records.
- Use relational for selected-NPC/player relationship changes or evidence-backed relationship judgments.
- Use procedural for stable instructions about how NPCs should communicate or cooperate with the player.
- Use facets for specific retrieval/governance labels such as communication_style, quest_completed, trust, ruins_safety, player_profile.
- Use npc_specific when the memory belongs to the selected NPC; use player_global only for stable player-wide facts or interaction preferences.
- Do not turn "the player needs help" into "the player helped an NPC".
- Do not store stable world lore as player memory unless the candidate is about what the player knows or revealed.
- evidence_text must be an exact quote or exact serialized evidence fragment from the current turn.
- If nothing is worth long-term memory, return an empty candidates array.
"""


def memory_llm_enabled() -> bool:
    if os.environ.get("AGENT_NPC_MEMORY_LLM_ENABLED", "1").strip() in {"0", "false", "False"}:
        return False
    settings = get_llm_settings()
    if settings.provider == "mock":
        return True
    if settings.provider != "openai_compatible" or not settings.api_key:
        return False
    return True


def generate_memory_candidates(
    policy_input: Any,
    rule_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not memory_llm_enabled():
        return [], {"enabled": False, "stage": "candidate_generation", "reason": "Memory LLM disabled or not configured."}
    settings = get_llm_settings()
    if settings.provider == "mock":
        candidates = generate_mock_memory_candidates(policy_input)
        return candidates, {
            "enabled": True,
            "stage": "candidate_generation",
            "status": "ok",
            "mode": "mock_memory_candidate",
            "candidate_count": len(candidates),
        }

    payload = {
        "player_input": policy_input.player_input,
        "npc_response": policy_input.npc_response,
        "recent_short_term_context": policy_input.recent_short_term_context,
        "retrieved_lore": policy_input.retrieved_lore,
        "retrieved_long_term_memories": policy_input.retrieved_long_term_memories,
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
        "tool_calls": policy_input.tool_calls,
        "state_changes": policy_input.state_changes,
        "rule_candidates": rule_candidates,
        "allowed_memory_types": ["semantic", "episodic", "relational", "procedural"],
        "allowed_scopes": ["npc_specific", "player_global"],
    }
    try:
        response = call_openai_compatible_json(
            system_prompt=MEMORY_CANDIDATE_SYSTEM_PROMPT,
            user_payload=payload,
        )
    except Exception as exc:
        return [], {
            "enabled": True,
            "stage": "candidate_generation",
            "status": "error",
            "reason": str(exc),
        }

    raw_candidates = response.get("candidates", [])
    candidates = []
    for candidate in raw_candidates if isinstance(raw_candidates, list) else []:
        normalized = normalize_llm_candidate(candidate)
        if normalized is not None:
            candidates.append(normalized)
    return candidates, {
        "enabled": True,
        "stage": "candidate_generation",
        "status": "ok",
        "candidate_count": len(candidates),
    }


def normalize_llm_candidate(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    tags = candidate.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    facets = candidate.get("facets", tags)
    if not isinstance(facets, list):
        facets = []
    return {
        "should_write": bool(candidate.get("should_write", False)),
        "npc_id": str(candidate.get("npc_id") or "lina"),
        "content": str(candidate.get("content", "")).strip(),
        "memory_type": normalize_memory_type(candidate.get("memory_type", "episodic")),
        "importance": clamp_int(candidate.get("importance", 5), 1, 10),
        "tags": [str(tag).strip() for tag in (tags or facets) if str(tag).strip()],
        "facets": [str(facet).strip() for facet in facets if str(facet).strip()],
        "scope": normalize_scope(candidate.get("scope", "npc_specific")),
        "confidence": clamp_float(candidate.get("confidence", 0.7), 0.0, 1.0),
        "stability": clamp_float(candidate.get("stability", 0.5), 0.0, 1.0),
        "future_usefulness": clamp_float(candidate.get("future_usefulness", 0.5), 0.0, 1.0),
        "reason": str(candidate.get("reason", "Generated by memory candidate LLM.")).strip(),
        "evidence_text": str(candidate.get("evidence_text", "")).strip(),
        "source": "llm_candidate",
    }


def generate_mock_memory_candidates(policy_input: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    player_text = policy_input.player_input.lower()
    tool_names = [tool.get("name") for tool in policy_input.tool_calls]
    quest_before = policy_input.quest_before
    quest_after = policy_input.quest_after
    npc_name = policy_input.npc_after.get("name", policy_input.npc_id)

    if any(phrase in player_text for phrase in ["直接告诉", "直接说", "不要绕弯", "别绕弯", "direct hints"]):
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="procedural",
                content="Player prefers direct hints instead of vague clues.",
                importance=6,
                confidence=0.9,
                facets=["communication_style", "direct_hints"],
                scope="player_global",
                evidence_text=policy_input.player_input,
                stability=0.85,
                future_usefulness=0.9,
                reason="The player explicitly stated a stable communication preference.",
            )
        )

    if any(phrase in player_text for phrase in ["我是新手", "新手", "不太熟悉", "i am new", "i'm new"]):
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="semantic",
                content="Player described themselves as new and may need extra context.",
                importance=5,
                confidence=0.85,
                facets=["player_profile", "experience_level"],
                scope="player_global",
                evidence_text=policy_input.player_input,
                stability=0.75,
                future_usefulness=0.8,
                reason="The player explicitly described their experience level.",
            )
        )

    if any(phrase in player_text for phrase in ["孤独", "无人会帮助", "lonely"]):
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="semantic",
                content="Player described themselves as lonely and worried nobody would help them.",
                importance=5,
                confidence=0.85,
                facets=["player_profile", "needs_support"],
                scope="player_global",
                evidence_text=policy_input.player_input,
                stability=0.55,
                future_usefulness=0.65,
                reason="The player explicitly described their emotional state.",
            )
        )

    if quest_before.get("status") != "completed" and quest_after.get("status") == "completed":
        quest_id = quest_after.get("quest_id", "quest")
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="episodic",
                content=f"Player completed the {quest_id} quest for {npc_name}.",
                importance=9,
                confidence=1.0,
                facets=["quest_completed", quest_id, policy_input.npc_id],
                scope="npc_specific",
                evidence_text=str(quest_after),
                stability=1.0,
                future_usefulness=0.9,
                reason="Quest status changed to completed.",
            )
        )

    if ("give_item" in tool_names or recorded_key_return(policy_input)) and quest_after.get("quest_id") == "lost_key":
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="episodic",
                content="Player returned Lina's lost key.",
                importance=8,
                confidence=1.0,
                facets=["helped_npc", "lost_key", "lina"],
                scope="npc_specific",
                evidence_text="Player returned Lina's lost key.",
                stability=1.0,
                future_usefulness=0.85,
                reason="Tool execution indicates the key was returned.",
            )
        )

    if "unlock_location" in tool_names:
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="episodic",
                content="Lina revealed the underground ruins entrance to the player.",
                importance=7,
                confidence=1.0,
                facets=["sensitive_location", "ruins", "player_knowledge"],
                scope="npc_specific",
                evidence_text="unlock_location",
                stability=1.0,
                future_usefulness=0.8,
                reason="A sensitive location was unlocked.",
            )
        )

    for event in recorded_events(policy_input):
        normalized = event.lower()
        if "lost key" in normalized or "underground ruins entrance" in normalized:
            continue
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="episodic",
                content=event,
                importance=7,
                confidence=0.95,
                facets=["world_event", policy_input.npc_id, quest_after.get("quest_id", "quest")],
                scope="npc_specific",
                evidence_text=event,
                stability=0.9,
                future_usefulness=0.75,
                reason="A world event was recorded for this NPC turn.",
            )
        )

    trust_delta = policy_input.npc_after.get("trust", 0) - policy_input.npc_before.get("trust", 0)
    affection_delta = policy_input.npc_after.get("affection", 0) - policy_input.npc_before.get("affection", 0)
    helped_lina = policy_input.npc_id != "lina" or any(
        candidate.get("content") == "Player returned Lina's lost key." for candidate in candidates
    )
    if trust_delta >= 5 and helped_lina:
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="relational",
                content=f"{npc_name} trusts the player more after evidence-backed task progress.",
                importance=7,
                confidence=0.9,
                facets=["trust", policy_input.npc_id],
                scope="npc_specific",
                evidence_text=str(policy_input.state_changes),
                stability=0.85,
                future_usefulness=0.85,
                reason=f"Trust increased by {trust_delta}.",
            )
        )
    if affection_delta >= 5 and helped_lina:
        candidates.append(
            build_mock_candidate(
                policy_input,
                memory_type="relational",
                content=f"{npc_name} feels more positively toward the player after evidence-backed task progress.",
                importance=6,
                confidence=0.85,
                facets=["affection", policy_input.npc_id],
                scope="npc_specific",
                evidence_text=str(policy_input.state_changes),
                stability=0.75,
                future_usefulness=0.75,
                reason=f"Affection increased by {affection_delta}.",
            )
        )

    return candidates


def build_mock_candidate(
    policy_input: Any,
    memory_type: str,
    content: str,
    importance: int,
    confidence: float,
    facets: list[str],
    scope: str,
    evidence_text: str,
    stability: float,
    future_usefulness: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "should_write": True,
        "npc_id": policy_input.npc_id,
        "memory_type": memory_type,
        "content": content,
        "importance": importance,
        "confidence": confidence,
        "tags": facets,
        "facets": facets,
        "scope": scope,
        "evidence_text": evidence_text,
        "stability": stability,
        "future_usefulness": future_usefulness,
        "reason": reason,
        "source": "llm_candidate_mock",
    }


def recorded_key_return(policy_input: Any) -> bool:
    return any(
        tool.get("name") == "record_world_event"
        and "lost key" in str(tool.get("arguments", {}).get("content", "")).lower()
        for tool in policy_input.tool_calls
    )


def recorded_events(policy_input: Any) -> list[str]:
    return [
        str(tool.get("arguments", {}).get("content", ""))
        for tool in policy_input.tool_calls
        if tool.get("name") == "record_world_event"
    ]


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
    return normalized if normalized in {"semantic", "episodic", "relational", "procedural"} else "episodic"


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
