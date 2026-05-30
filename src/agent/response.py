from __future__ import annotations

from dataclasses import asdict, is_dataclass
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
    observation: Any | None = None,
    npc_action: Any | None = None,
    action_result: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    """Generate the NPC's final text from decision keywords through the configured LLM."""
    settings = get_llm_settings()
    if settings.provider != "openai_compatible" or not settings.is_configured:
        raise RuntimeError("A configured LLM is required for response generation.")
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
                "observation": serialize_optional_dataclass(observation),
                "npc_action": serialize_optional_dataclass(npc_action),
                "action_result": serialize_optional_dataclass(action_result),
                "response_constraints": get_response_constraints(action_result),
                "expected_output_schema": RESPONSE_OUTPUT_SCHEMA,
            },
            settings=settings,
        )
    except Exception as exc:
        raise RuntimeError(f"LLM response generation failed: {exc}") from exc
    try:
        response = validate_response_payload(payload)
    except Exception as exc:
        return safe_constraint_response(decision, npc_state, action_result), {
            "provider": settings.provider,
            "mode": "constraint_guard",
            "reason": str(exc),
        }
    if violates_action_result_constraints(response, action_result):
        return safe_constraint_response(decision, npc_state, action_result), {
            "provider": settings.provider,
            "mode": "constraint_guard",
            "reason": "LLM response violated ActionResult constraints.",
        }
    return response, {"provider": settings.provider, "mode": "llm_polish"}


def safe_constraint_response(
    decision: dict[str, Any],
    npc_state: dict[str, Any],
    action_result: Any | None,
) -> str:
    name = npc_state.get("name", "NPC")
    if action_result is not None and not action_result_accepted(action_result):
        blocked_reason = getattr(action_result, "blocked_reason", "")
        if isinstance(action_result, dict):
            blocked_reason = action_result.get("blocked_reason", blocked_reason)
        detail = f"原因是：{blocked_reason}" if blocked_reason else "还需要更多证据。"
        return f"{name} 没有立刻接受这个说法：“现在还不能确认这件事，{detail}”"
    if decision.get("intent") == "withhold_ruins_entrance":
        return f"{name} 语气谨慎：“这件事我暂时不能说得更具体。”"
    return f"{name} 认真听完你的话：“我明白了，但现在还不能确认会发生任何改变。”"


def serialize_optional_dataclass(value: Any | None) -> Any | None:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    return value


def get_response_constraints(action_result: Any | None) -> list[str]:
    if action_result is None:
        return []
    constraints = getattr(action_result, "response_constraints", None)
    if constraints is None and isinstance(action_result, dict):
        constraints = action_result.get("response_constraints")
    if isinstance(constraints, list):
        return constraints
    return []


def get_executed_tool_names(action_result: Any | None) -> set[str]:
    if action_result is None:
        return set()
    executed_tools = getattr(action_result, "executed_tools", None)
    if executed_tools is None and isinstance(action_result, dict):
        executed_tools = action_result.get("executed_tools")
    if not isinstance(executed_tools, list):
        return set()
    return {
        str(tool.get("name"))
        for tool in executed_tools
        if isinstance(tool, dict) and tool.get("name")
    }


def action_result_accepted(action_result: Any | None) -> bool:
    if action_result is None:
        return True
    accepted = getattr(action_result, "accepted", None)
    if accepted is None and isinstance(action_result, dict):
        accepted = action_result.get("accepted")
    return bool(accepted)


def violates_action_result_constraints(response: str, action_result: Any | None) -> bool:
    if action_result is None:
        return False
    executed_names = get_executed_tool_names(action_result)
    unlock_claims = ["入口已经开放", "入口已开放", "可以直接过去", "已经解锁", "可以进入遗迹"]
    reward_claims = ["给你", "收下", "折扣券", "奖励"]
    completion_claims = ["任务完成", "已经完成", "完成了"]
    trust_claims = ["更信任你", "信任你更多", "可信度"]
    affection_claims = ["更喜欢你", "更亲近你", "好感"]
    if "unlock_location" not in executed_names and any(term in response for term in unlock_claims):
        return True
    if "give_item" not in executed_names and any(term in response for term in reward_claims):
        return True
    if "update_quest_status" not in executed_names and any(term in response for term in completion_claims):
        return True
    if "update_trust" not in executed_names and any(term in response for term in trust_claims):
        return True
    if "update_affection" not in executed_names and any(term in response for term in affection_claims):
        return True
    if not action_result_accepted(action_result):
        blocked_claims = unlock_claims + reward_claims + completion_claims + trust_claims + affection_claims
        return any(term in response for term in blocked_claims)
    return False


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
    return f"{name} 认真听完你的话：“我明白你的意思了。先让我再想想。”"
