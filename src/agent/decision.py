from __future__ import annotations

from typing import Any

from src.agent.llm_client import call_openai_compatible_json, get_llm_settings
from src.agent.prompts import DECISION_OUTPUT_SCHEMA, DECISION_SYSTEM_PROMPT, TOOL_ARGUMENT_SCHEMAS


NPC_ID = "lina"
ALLOWED_TOOL_NAMES = {
    "add_memory",
    "update_trust",
    "update_affection",
    "give_item",
    "update_quest_status",
    "unlock_location",
    "record_world_event",
}
ALLOWED_INTENTS = {
    "start_lost_key_quest",
    "complete_lost_key_quest",
    "reveal_ruins_entrance",
    "withhold_ruins_entrance",
    "general_conversation",
}
INTENT_ALIASES = {
    "start_key_quest": "start_lost_key_quest",
    "ask_lost_key_details": "start_lost_key_quest",
    "offer_find_lost_key": "start_lost_key_quest",
    "complete_quest_return_key": "complete_lost_key_quest",
    "complete_lost_key": "complete_lost_key_quest",
    "return_lost_key": "complete_lost_key_quest",
    "returned_lost_key": "complete_lost_key_quest",
    "unlock_ruins_entrance": "reveal_ruins_entrance",
    "reveal_underground_ruins": "reveal_ruins_entrance",
    "deny_ruins_entrance": "withhold_ruins_entrance",
    "refuse_ruins_entrance": "withhold_ruins_entrance",
}


def decide_next_action(
    player_input: str,
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
    memories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a structured decision using mock by default or optional real LLM."""
    settings = get_llm_settings()
    if settings.provider == "openai_compatible" and settings.is_configured:
        try:
            decision = call_openai_compatible_json(
                system_prompt=DECISION_SYSTEM_PROMPT,
                user_payload={
                    "player_input": player_input,
                    "npc_state": npc_state,
                    "player_state": player_state,
                    "quest_state": quest_state,
                    "retrieved_memories": memories,
                    "expected_output_schema": DECISION_OUTPUT_SCHEMA,
                    "allowed_intents": sorted(ALLOWED_INTENTS),
                    "allowed_tools": sorted(ALLOWED_TOOL_NAMES),
                    "tool_argument_schemas": TOOL_ARGUMENT_SCHEMAS,
                },
                settings=settings,
            )
            return validate_decision(decision)
        except Exception as exc:
            fallback = mock_decide_next_action(player_input, npc_state, player_state, quest_state, memories)
            fallback["llm_fallback"] = {
                "provider": settings.provider,
                "reason": str(exc),
            }
            return fallback
    return mock_decide_next_action(player_input, npc_state, player_state, quest_state, memories)


def mock_decide_next_action(
    player_input: str,
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
    memories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministic structured decision used for local demos and tests."""
    text = player_input.lower()
    has_key_signal = any(word in text for word in ["钥匙", "key", "找回", "归还", "returned"])
    has_key_start_signal = any(
        phrase in text
        for phrase in [
            "什么样的钥匙",
            "我这就去帮你找",
            "帮你找找",
            "去找钥匙",
            "帮你找钥匙",
            "find your key",
            "look for your key",
        ]
    )
    has_key_return_signal = any(word in text for word in ["找回", "归还", "还给", "给你钥匙", "returned"])
    asks_ruins = any(word in text for word in ["遗迹", "入口", "ruins", "entrance", "underground"])
    has_help_memory = any("lost key" in memory["content"].lower() or "钥匙" in memory["content"] for memory in memories)
    trusted = npc_state["trust"] >= 30 or quest_state["status"] == "completed" or has_help_memory

    if has_key_start_signal or (has_key_signal and not has_key_return_signal):
        return build_decision(
            intent="start_lost_key_quest",
            reasoning="Player asks about Lina's lost key or offers to help find it, so Lina should start the quest and give key details.",
            response_style="grateful_cautious",
            response_keywords=[
                "后屋储藏室",
                "小铜钥匙",
                "镇广场附近",
                "谢谢帮忙",
            ],
            memory_policy="Write a memory that the player offered to help find Lina's lost key.",
            tools=[
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "in_progress"}},
                {"name": "update_trust", "args": {"npc_id": NPC_ID, "delta": 10}},
                {
                    "name": "add_memory",
                    "args": {
                        "npc_id": NPC_ID,
                        "content": "玩家询问 Lina 丢失钥匙的细节，并表示愿意帮忙寻找。",
                        "importance": 6,
                        "tags": ["key", "help", "quest_start"],
                    },
                },
            ],
        )

    if has_key_signal and has_key_return_signal and quest_state["status"] != "completed":
        return build_decision(
            intent="complete_lost_key_quest",
            reasoning="Player claims to return Lina's lost key, so Lina should remember it and update relationship state.",
            response_style="grateful_and_more_trusting",
            response_keywords=[
                "接过钥匙",
                "松了一口气",
                "更信任玩家",
                "任务完成",
                "酒馆折扣券",
            ],
            memory_policy="Write a high-importance memory because this changes Lina's trust and quest state.",
            tools=[
                {
                    "name": "add_memory",
                    "args": {
                        "npc_id": NPC_ID,
                        "content": "Player returned Lina's lost key.",
                        "importance": 8,
                        "tags": ["help", "trust", "lost_key"],
                    },
                },
                {"name": "update_trust", "args": {"npc_id": NPC_ID, "delta": 10}},
                {"name": "update_affection", "args": {"npc_id": NPC_ID, "delta": 8}},
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "completed"}},
                {"name": "give_item", "args": {"item": "tavern_discount_coupon"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Player returned Lina's lost key."},
                },
            ],
        )

    if asks_ruins and trusted:
        return build_decision(
            intent="reveal_ruins_entrance",
            reasoning="Player has enough trust or relevant memory, so Lina can reveal the entrance and unlock it.",
            response_style="secretive_but_helpful",
            response_keywords=[
                "压低声音",
                "相信玩家",
                "地下遗迹",
                "酒馆后巷",
                "隐秘入口",
            ],
            memory_policy="Write a memory that Lina revealed a sensitive location.",
            tools=[
                {
                    "name": "add_memory",
                    "args": {
                        "npc_id": NPC_ID,
                        "content": "Lina revealed the underground ruins entrance to the player.",
                        "importance": 7,
                        "tags": ["ruins", "trust", "location"],
                    },
                },
                {"name": "unlock_location", "args": {"location": "underground_ruins_entrance"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Lina revealed the underground ruins entrance."},
                },
            ],
        )

    if asks_ruins:
        return build_decision(
            intent="withhold_ruins_entrance",
            reasoning="Player asks about a sensitive location, but Lina does not trust the player enough yet.",
            response_style="cautious_refusal",
            response_keywords=[
                "谨慎",
                "暂不透露",
                "地下遗迹",
                "需要更多信任",
            ],
            memory_policy="Write a low-importance memory that the player asked too early.",
            tools=[
                {
                    "name": "add_memory",
                    "args": {
                        "npc_id": NPC_ID,
                        "content": "Player asked Lina about the underground ruins before earning enough trust.",
                        "importance": 4,
                        "tags": ["ruins", "low_trust"],
                    },
                }
            ],
        )

    return build_decision(
        intent="general_conversation",
        reasoning="No quest-changing intent detected, so Lina keeps the conversation in memory without changing major state.",
        response_style="attentive_neutral",
        response_keywords=[
            "认真听完",
            "会记住",
            "保持观察",
        ],
        memory_policy="Store the conversation as low-importance context.",
        tools=[
            {
                "name": "add_memory",
                "args": {
                    "npc_id": NPC_ID,
                    "content": f"Player said to Lina: {player_input}",
                    "importance": 3,
                    "tags": ["conversation"],
                },
            }
        ],
    )


def validate_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Validate a model-produced decision before tools can execute it."""
    required_fields = {
        "intent",
        "reasoning",
        "memory_policy",
        "response_style",
        "response_keywords",
        "tools",
    }
    missing_fields = required_fields - set(decision)
    if missing_fields:
        raise ValueError(f"Decision missing fields: {sorted(missing_fields)}")
    decision["intent"] = normalize_intent(decision["intent"])
    if not isinstance(decision["response_keywords"], list) or not all(
        isinstance(keyword, str) for keyword in decision["response_keywords"]
    ):
        raise ValueError("Decision response_keywords must be an array of strings.")
    if not isinstance(decision["tools"], list):
        raise ValueError("Decision tools must be a list.")
    for tool in decision["tools"]:
        validate_tool_call(tool)
    normalize_memory_tool_args(decision)
    validate_decision_business_rules(decision)
    return decision


def normalize_intent(intent: Any) -> str:
    if not isinstance(intent, str):
        raise ValueError("Decision intent must be a string.")
    normalized = INTENT_ALIASES.get(intent, intent)
    if normalized not in ALLOWED_INTENTS:
        raise ValueError(f"Unsupported decision intent: {intent}")
    return normalized


def validate_tool_call(tool: dict[str, Any]) -> None:
    name = tool.get("name")
    if name not in ALLOWED_TOOL_NAMES:
        raise ValueError(f"Unsupported tool in LLM decision: {name}")
    if not isinstance(tool.get("args"), dict):
        raise ValueError(f"Tool args must be an object: {name}")

    args = tool["args"]
    required_args = set(TOOL_ARGUMENT_SCHEMAS[name]["required_args"])
    optional_args = set(TOOL_ARGUMENT_SCHEMAS[name].get("optional_args", {}))
    allowed_args = required_args | optional_args
    missing_args = required_args - set(args)
    extra_args = set(args) - allowed_args
    if missing_args:
        raise ValueError(f"Tool {name} missing required args: {sorted(missing_args)}")
    if extra_args:
        raise ValueError(f"Tool {name} has unsupported args: {sorted(extra_args)}")

    for arg_name in required_args | (optional_args & set(args)):
        expected_type = TOOL_ARGUMENT_SCHEMAS[name].get("required_args", {}).get(
            arg_name
        ) or TOOL_ARGUMENT_SCHEMAS[name].get("optional_args", {}).get(arg_name)
        validate_tool_arg_type(name, arg_name, args[arg_name], expected_type)


def validate_tool_arg_type(tool_name: str, arg_name: str, value: Any, expected_type: str) -> None:
    if expected_type == "string" and not isinstance(value, str):
        raise ValueError(f"Tool {tool_name} arg {arg_name} must be a string.")
    if expected_type == "integer" and not isinstance(value, int):
        raise ValueError(f"Tool {tool_name} arg {arg_name} must be an integer.")
    if expected_type == "array of strings":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Tool {tool_name} arg {arg_name} must be an array of strings.")


def validate_decision_business_rules(decision: dict[str, Any]) -> None:
    intent = decision["intent"]
    tool_calls = decision["tools"]
    tool_names = [tool["name"] for tool in tool_calls]

    if intent == "start_lost_key_quest":
        require_quest_status(tool_calls, "in_progress", intent)
        forbid_quest_status(tool_calls, "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "complete_lost_key_quest":
        require_quest_status(tool_calls, "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "reveal_ruins_entrance":
        require_unlock_location(tool_calls, "underground_ruins_entrance", intent)
    elif intent == "withhold_ruins_entrance":
        forbid_tool(tool_names, "unlock_location", intent)


def normalize_memory_tool_args(decision: dict[str, Any]) -> None:
    """Keep memory records factual while leaving response wording flexible."""
    intent = decision["intent"]
    for tool in decision["tools"]:
        if tool["name"] != "add_memory":
            continue
        args = tool["args"]
        if intent == "reveal_ruins_entrance":
            args["content"] = (
                "Lina revealed the underground ruins entrance to the player "
                "after the player earned her trust."
            )
            args["tags"] = sorted(set(args.get("tags", []) + ["ruins", "trust", "location"]))
        elif intent == "start_lost_key_quest":
            args["content"] = "Player asked Lina for lost-key details and offered to help find it."
            args["tags"] = sorted(set(args.get("tags", []) + ["key", "help", "quest_start"]))
        elif intent == "complete_lost_key_quest":
            args["content"] = "Player returned Lina's lost key."
            args["tags"] = sorted(set(args.get("tags", []) + ["help", "trust", "lost_key"]))


def require_quest_status(tool_calls: list[dict[str, Any]], status: str, intent: str) -> None:
    if not any(
        tool["name"] == "update_quest_status"
        and tool["args"].get("quest_id") == "lost_key"
        and tool["args"].get("status") == status
        for tool in tool_calls
    ):
        raise ValueError(f"Intent {intent} requires lost_key quest status {status}.")


def forbid_quest_status(tool_calls: list[dict[str, Any]], status: str, intent: str) -> None:
    if any(
        tool["name"] == "update_quest_status"
        and tool["args"].get("quest_id") == "lost_key"
        and tool["args"].get("status") == status
        for tool in tool_calls
    ):
        raise ValueError(f"Intent {intent} must not set lost_key quest status {status}.")


def require_unlock_location(tool_calls: list[dict[str, Any]], location: str, intent: str) -> None:
    if not any(
        tool["name"] == "unlock_location" and tool["args"].get("location") == location
        for tool in tool_calls
    ):
        raise ValueError(f"Intent {intent} requires unlocking {location}.")


def forbid_tool(tool_names: list[str], tool_name: str, intent: str) -> None:
    if tool_name in tool_names:
        raise ValueError(f"Intent {intent} must not call {tool_name}.")


def build_decision(
    intent: str,
    reasoning: str,
    response_style: str,
    response_keywords: list[str],
    memory_policy: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return an LLM-like structured decision for display and later API replacement."""
    return {
        "intent": intent,
        "reasoning": reasoning,
        "memory_policy": memory_policy,
        "response_style": response_style,
        "response_keywords": response_keywords,
        "tools": tools,
    }


def mock_llm_response(
    decision: dict[str, Any],
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> str:
    """Generate a deterministic mock response so the MVP runs without API keys."""
    from src.agent.response import fallback_response

    return fallback_response(decision, npc_state, quest_state)
