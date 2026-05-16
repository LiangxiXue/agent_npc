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
    retrieved_lore: list[dict[str, Any]] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    recent_context: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Generate the NPC's final text from decision keywords, with deterministic fallback."""
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
                        "social_intent": decision.get("social_intent", "cooperate"),
                        "social_stance": decision.get("social_stance", {}),
                        "response_style": decision["response_style"],
                        "response_keywords": decision["response_keywords"],
                    },
                    "npc_state": npc_state,
                    "hidden_alignment": npc_state.get("hidden_alignment", "neutral"),
                    "player_state": player_state,
                    "quest_state": quest_state,
                    "state_snapshot": state_snapshot or {
                        "npc": npc_state,
                        "player": player_state,
                        "quest": quest_state,
                    },
                    "canonical_world_facts": CANONICAL_WORLD_FACTS,
                    "retrieved_lore": retrieved_lore or [],
                    "retrieved_memories": retrieved_memories,
                    "recent_context": recent_context or [],
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
    npc_id = npc_state.get("npc_id", "")
    name = npc_state.get("name", "NPC")
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
    if intent == "probe_for_evidence" and decision.get("state_machine", {}).get("blocked"):
        return (
            f"{name} 没有立刻接受这个说法：“先把事情说清楚一点。"
            "我不能只凭一句话就当作任务已经完成。”"
        )
    if intent == "start_gate_badge_quest":
        return "Ron 合上巡逻记录：“如果你要查守卫徽章，就给我时间、地点和能核对的人名。没有证据，我不会把传闻写进交接。”"
    if intent == "complete_gate_badge_quest":
        return f"Ron 核对完记录，语气缓和了一些：“这条徽章线索能对上。你的可信度现在是 {npc_state['trust']}，我会把夜巡交接补清楚。”"
    if intent == "probe_for_evidence" and npc_id == "ron":
        return "Ron 皱眉翻开巡逻记录：“我不会凭一句传闻放你过去。说清楚时间、地点，还有谁能证明。”"
    if intent == "start_ancient_notes_quest":
        return "Mira 把笔记本推近一些：“如果你真见过遗迹痕迹，就记下符号的位置、形状和门是否封闭。别急着把传闻当结论。”"
    if intent == "complete_ancient_notes_quest":
        return f"Mira 仔细核对你的描述，眼神亮了些：“这些观察有研究价值。我会把它们归入田野笔记；现在我对你的可信度是 {npc_state['trust']}。”"
    if intent == "probe_for_evidence" and npc_id == "mira":
        return "Mira 摇了摇头：“这听起来更像传闻。给我具体符号、位置和一手观察，我才会把它当成线索。”"
    if intent == "start_relic_tip_quest":
        return "Sable 微笑着压低声音：“Lina 太谨慎了。与其一直问她，不如先查守卫换岗记录，也许那里有人漏过口风。”"
    if intent == "complete_relic_tip_quest":
        return "Sable 若有所思地点头：“这条线索有价值。先别急着告诉守卫，换个角度查，古物消息往往会自己露出价格。”"
    if npc_id == "ron":
        return "Ron 扫了一眼巡逻记录，点头说：“我会把这件事记在城门值守日志旁边。”"
    if npc_id == "mira":
        return "Mira 合上笔记本，认真回答：“这条线索值得保留，我会和遗迹资料一起核对。”"
    if npc_id == "sable":
        return "Sable 笑了笑：“消息本身就有价格。先别急着表态，我们可以看看谁最想把它藏起来。”"
    return f"{name} 认真听完你的话：“我会记住这件事的。”"
