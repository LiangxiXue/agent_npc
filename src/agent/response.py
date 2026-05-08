from __future__ import annotations

from typing import Any

from src.agent.llm_client import call_openai_compatible_json, get_llm_settings
from src.agent.prompts import RESPONSE_OUTPUT_SCHEMA, RESPONSE_SYSTEM_PROMPT
from src.agent.world_facts import CANONICAL_WORLD_FACTS, MAJOR_FACT_CONFLICT_TERMS


def generate_npc_response(
    player_input: str,
    decision: dict[str, Any],
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
    retrieved_memories: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Generate Lina's final text from decision keywords, with deterministic fallback."""
    settings = get_llm_settings()
    if settings.provider == "openai_compatible" and settings.is_configured:
        try:
            payload = call_openai_compatible_json(
                system_prompt=RESPONSE_SYSTEM_PROMPT,
                user_payload={
                    "player_input": player_input,
                    "decision": {
                        "intent": decision["intent"],
                        "reasoning": decision["reasoning"],
                        "response_style": decision["response_style"],
                        "response_keywords": decision["response_keywords"],
                    },
                    "npc_state": npc_state,
                    "player_state": player_state,
                    "quest_state": quest_state,
                    "canonical_world_facts": CANONICAL_WORLD_FACTS,
                    "retrieved_memories": retrieved_memories,
                    "tool_calls": tool_calls,
                    "state_changes": state_changes,
                    "expected_output_schema": RESPONSE_OUTPUT_SCHEMA,
                },
                settings=settings,
            )
            response = validate_response_payload(payload)
            return response, {"provider": settings.provider, "mode": "llm_polish"}
        except Exception as exc:
            return fallback_response(decision, npc_state, quest_state), {
                "provider": settings.provider,
                "mode": "fallback_template",
                "reason": str(exc),
            }

    return fallback_response(decision, npc_state, quest_state), {
        "provider": settings.provider,
        "mode": "fallback_template",
    }


def validate_response_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Response payload must be a JSON object.")
    response = payload.get("npc_response")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Response payload must include a non-empty npc_response string.")
    response = response.strip()
    validate_major_fact_consistency(response)
    return response


def validate_major_fact_consistency(response: str) -> None:
    for fact_key, conflict_terms in MAJOR_FACT_CONFLICT_TERMS.items():
        if any(term in response for term in conflict_terms):
            raise ValueError(f"Response conflicts with canonical world fact: {fact_key}.")


def fallback_response(
    decision: dict[str, Any],
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> str:
    """Deterministic response for tests and demos without API keys."""
    intent = decision["intent"]
    if intent == "complete_lost_key_quest":
        return (
            "Lina 接过钥匙，明显松了一口气。"
            f"“看来我可以更信任你一些了。现在我的信任度是 {npc_state['trust']}，"
            f"任务状态也已经变为 {quest_state['status']}。”"
        )
    if intent == "reveal_ruins_entrance":
        return "Lina 压低声音说：“好吧，我相信你。地下遗迹的隐秘入口就在酒馆后巷。”"
    if intent == "start_lost_key_quest":
        return "Lina 停下擦杯子的手：“是后屋储藏室铁箱的小铜钥匙，我大概是在镇广场附近弄丢的。你肯帮忙，我会记着这份人情。”"
    if intent == "withhold_ruins_entrance":
        return "Lina 皱了皱眉：“这种地方不是随便能打听的。等我更了解你之后再说吧。”"
    return "Lina 擦了擦杯子，认真听完你的话：“我会记住这件事的。”"
