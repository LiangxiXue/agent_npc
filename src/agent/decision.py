from __future__ import annotations

from typing import Any

from src.agent.llm_client import call_openai_compatible_json, get_llm_settings
from src.agent.prompts import DECISION_OUTPUT_SCHEMA, DECISION_SYSTEM_PROMPT, TOOL_ARGUMENT_SCHEMAS
from src.agent.turn_classifier import classify_turn


NPC_ID = "lina"
ALLOWED_TOOL_NAMES = {
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
    "start_gate_badge_quest",
    "complete_gate_badge_quest",
    "start_ancient_notes_quest",
    "complete_ancient_notes_quest",
    "start_relic_tip_quest",
    "complete_relic_tip_quest",
    "redirect_ruins_inquiry",
    "probe_for_evidence",
    "general_conversation",
}
TASK_INTENTS = {
    "lost_key": {
        "npc_id": "lina",
        "start": "start_lost_key_quest",
        "complete": "complete_lost_key_quest",
        "evidence": ["钥匙", "key", "找回", "归还", "还给", "returned"],
    },
    "gate_badge": {
        "npc_id": "ron",
        "start": "start_gate_badge_quest",
        "complete": "complete_gate_badge_quest",
        "evidence": ["徽章", "badge", "登记", "签名", "ledger", "证人", "witness", "能对上"],
    },
    "ancient_notes": {
        "npc_id": "mira",
        "start": "start_ancient_notes_quest",
        "complete": "complete_ancient_notes_quest",
        "evidence": ["观察", "符号", "铭文", "笔记", "封闭石门", "field notes", "inscription", "sealed"],
    },
    "relic_tip": {
        "npc_id": "sable",
        "start": "start_relic_tip_quest",
        "complete": "complete_relic_tip_quest",
        "evidence": ["后巷", "入口", "线索", "换岗记录", "relic", "entrance", "lina说", "接受"],
    },
}
ALLOWED_SOCIAL_INTENTS = {
    "cooperate",
    "conceal",
    "oppose",
    "probe",
    "ally",
    "deceive",
    "redirect",
    "accuse",
}
ALLOWED_SOCIAL_TARGETS = {
    "player",
    "lina",
    "ron",
    "mira",
    "sable",
    "ruins_access",
}
ALLOWED_SOCIAL_ATTITUDES = {
    "support",
    "distrust",
    "cautious",
    "hostile",
    "manipulative",
    "protective",
    "curious",
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
    "ask_for_evidence": "probe_for_evidence",
    "request_evidence": "probe_for_evidence",
    "start_badge_quest": "start_gate_badge_quest",
    "complete_badge_quest": "complete_gate_badge_quest",
    "start_notes_quest": "start_ancient_notes_quest",
    "complete_notes_quest": "complete_ancient_notes_quest",
    "start_relic_quest": "start_relic_tip_quest",
    "complete_relic_quest": "complete_relic_tip_quest",
}


def decide_next_action(
    player_input: str,
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
    retrieved_long_term_memories: list[dict[str, Any]],
    retrieved_lore: list[dict[str, Any]] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    recent_short_term_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a structured decision using mock by default or optional real LLM."""
    classification = classify_turn(
        player_input,
        npc_id=str(npc_state.get("npc_id", NPC_ID)),
        quest_status=str(quest_state.get("status", "not_started")),
    )
    if classification.turn_type not in {"ambiguous", "social_maneuver"}:
        routed = apply_task_state_machine(
            mock_decide_next_action(
                player_input,
                npc_state,
                player_state,
                quest_state,
                retrieved_long_term_memories,
                recent_short_term_context or [],
            ),
            player_input=player_input,
            npc_state=npc_state,
            quest_state=quest_state,
        )
        return annotate_decision_route(routed, "rule_fast_path", classification)

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
                    "retrieved_lore": retrieved_lore or [],
                    "retrieved_long_term_memories": retrieved_long_term_memories,
                    "state_snapshot": state_snapshot or {
                        "npc": npc_state,
                        "player": player_state,
                        "quest": quest_state,
                    },
                    "recent_short_term_context": recent_short_term_context or [],
                    "expected_output_schema": DECISION_OUTPUT_SCHEMA,
                    "allowed_intents": sorted(ALLOWED_INTENTS),
                    "allowed_social_intents": sorted(ALLOWED_SOCIAL_INTENTS),
                    "allowed_social_targets": sorted(ALLOWED_SOCIAL_TARGETS),
                    "allowed_social_attitudes": sorted(ALLOWED_SOCIAL_ATTITUDES),
                    "allowed_tools": sorted(ALLOWED_TOOL_NAMES),
                    "tool_argument_schemas": TOOL_ARGUMENT_SCHEMAS,
                },
                settings=settings,
            )
            routed = apply_task_state_machine(
                validate_decision(decision),
                player_input=player_input,
                npc_state=npc_state,
                quest_state=quest_state,
            )
            return annotate_decision_route(routed, "llm_assisted", classification)
        except Exception as exc:
            fallback = mock_decide_next_action(
                player_input,
                npc_state,
                player_state,
                quest_state,
                retrieved_long_term_memories,
                recent_short_term_context or [],
            )
            fallback["llm_fallback"] = {
                "provider": settings.provider,
                "reason": str(exc),
            }
            routed = apply_task_state_machine(
                fallback,
                player_input=player_input,
                npc_state=npc_state,
                quest_state=quest_state,
            )
            return annotate_decision_route(routed, "fallback", classification)
    routed = apply_task_state_machine(
        mock_decide_next_action(
            player_input,
            npc_state,
            player_state,
            quest_state,
            retrieved_long_term_memories,
            recent_short_term_context or [],
        ),
        player_input=player_input,
        npc_state=npc_state,
        quest_state=quest_state,
    )
    return annotate_decision_route(routed, "rule_fast_path", classification)


def annotate_decision_route(
    decision: dict[str, Any],
    route: str,
    classification: Any,
) -> dict[str, Any]:
    decision["decision_route"] = route
    decision["turn_classification"] = {
        "turn_type": classification.turn_type,
        "confidence": classification.confidence,
        "reason": classification.reason,
    }
    return decision


def mock_decide_next_action(
    player_input: str,
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
    retrieved_long_term_memories: list[dict[str, Any]],
    recent_short_term_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic structured decision used for local demos and tests."""
    npc_id = npc_state.get("npc_id", NPC_ID)
    if npc_id == "ron":
        return mock_ron_decision(player_input, npc_state, quest_state)
    if npc_id == "mira":
        return mock_mira_decision(player_input, npc_state, quest_state)
    if npc_id == "sable":
        return mock_sable_decision(player_input, npc_state, quest_state)

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
    has_help_memory = any(
        "lost_key" in memory.get("tags", [])
        or {"help", "trust"} <= set(memory.get("tags", []))
        or "lost key" in memory["content"].lower()
        or "helped her" in memory["content"].lower()
        or "钥匙" in memory["content"]
        for memory in retrieved_long_term_memories
    )
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
            social_intent="ally",
            social_stance={
                "target": "player",
                "attitude": "support",
                "intensity": 0.55,
                "reason": "The player offered concrete help with Lina's personal key problem.",
            },
            tools=[
                {"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "in_progress"}},
                {"name": "update_trust", "args": {"npc_id": npc_id, "delta": 10}},
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
            social_intent="ally",
            social_stance={
                "target": "player",
                "attitude": "support",
                "intensity": 0.8,
                "reason": "Returning the key is direct evidence that the player followed through for Lina.",
            },
            tools=[
                {"name": "update_trust", "args": {"npc_id": npc_id, "delta": 10}},
                {"name": "update_affection", "args": {"npc_id": npc_id, "delta": 8}},
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
            social_intent="cooperate",
            social_stance={
                "target": "ruins_access",
                "attitude": "protective",
                "intensity": 0.75,
                "reason": "The player has earned enough trust for Lina to cooperate while still treating the entrance as sensitive.",
            },
            tools=[
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
            social_intent="conceal",
            social_stance={
                "target": "ruins_access",
                "attitude": "protective",
                "intensity": 0.8,
                "reason": "The player asked for a sensitive entrance before earning Lina's trust.",
            },
            tools=[],
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
        social_intent="cooperate",
        social_stance={
            "target": "player",
            "attitude": "cautious",
            "intensity": 0.3,
            "reason": "No strong conflict or quest-changing request was detected.",
        },
        tools=[],
    )


def mock_ron_decision(
    player_input: str,
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    npc_id = npc_state.get("npc_id", "")
    text = player_input.lower()
    badge_terms = ["徽章", "badge", "巡逻", "patrol", "城门", "gate", "守卫记录", "登记"]
    evidence_terms = ["找到了", "带来", "归还", "交还", "ledger", "签名", "witness", "证人", "哨位", "能对上"]
    asks_ruins = any(term in text for term in ["遗迹", "入口", "ruins", "entrance", "通行", "放行"])

    if any(term in text for term in evidence_terms) and quest_state["status"] != "completed":
        return build_decision(
            intent="complete_gate_badge_quest",
            reasoning="Player provides a concrete badge or guard-record lead, so Ron can close the badge verification task.",
            response_style="formal_cooperation",
            response_keywords=["核对记录", "徽章线索", "更可信", "夜巡交接"],
            memory_policy="Write a memory that the player provided reliable guard evidence.",
            social_intent="cooperate",
            social_stance={
                "target": "player",
                "attitude": "support",
                "intensity": 0.7,
                "reason": "The player supplied evidence Ron can verify in the guard process.",
            },
            tools=[
                {"name": "update_trust", "args": {"npc_id": npc_id, "delta": 8}},
                {"name": "update_quest_status", "args": {"quest_id": "gate_badge", "status": "completed"}},
                {"name": "give_item", "args": {"item": "guard_route_note"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Player helped Ron verify the misplaced gate badge."},
                },
            ],
        )

    if any(term in text for term in badge_terms) and quest_state["status"] == "not_started":
        return build_decision(
            intent="start_gate_badge_quest",
            reasoning="Player asked about Ron's badge, patrol, or gate records, so Ron starts the evidence-focused badge verification task.",
            response_style="procedural_probe",
            response_keywords=["守卫徽章", "巡逻记录", "时间地点", "证据"],
            memory_policy="Remember whether the player can provide concrete guard evidence.",
            social_intent="probe",
            social_stance={
                "target": "player",
                "attitude": "distrust",
                "intensity": 0.65,
                "reason": "Ron needs concrete evidence before treating the player as reliable.",
            },
            tools=[
                {"name": "update_quest_status", "args": {"quest_id": "gate_badge", "status": "in_progress"}}
            ],
        )

    if asks_ruins:
        return build_decision(
            intent="probe_for_evidence",
            reasoning="Player asks Ron about sensitive ruins access without sufficient guard evidence.",
            response_style="formal_suspicion",
            response_keywords=["证据", "时间", "守卫记录", "不能只听传闻"],
            memory_policy="Do not write a long-term memory unless the player gives concrete evidence.",
            social_intent="probe",
            social_stance={
                "target": "player",
                "attitude": "distrust",
                "intensity": 0.75,
                "reason": "Ron treats ruins access as a public-safety issue requiring evidence.",
            },
            tools=[],
        )

    return build_decision(
        intent="general_conversation",
        reasoning="No guard-task evidence or sensitive access request was detected.",
        response_style="guard_attentive",
        response_keywords=["巡逻记录", "城门安全", "保持警惕"],
        memory_policy="Store stable player preferences or evidence habits for Ron only.",
        social_intent="probe",
        social_stance={
            "target": "player",
            "attitude": "cautious",
            "intensity": 0.35,
            "reason": "Ron remains procedural even in ordinary conversation.",
        },
        tools=[],
    )


def mock_mira_decision(
    player_input: str,
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    npc_id = npc_state.get("npc_id", "")
    text = player_input.lower()
    research_terms = ["铭文", "笔记", "拓片", "符号", "观察", "field notes", "inscription", "rubbing", "sealed door", "遗迹"]
    concrete_terms = ["具体观察", "形状", "位置在", "拓片", "一手", "sealed", "door", "符号像", "我看到", "封闭石门"]
    rumor_terms = ["听说", "传闻", "宝藏", "treasure", "肯定", "一定"]

    if any(term in text for term in concrete_terms) and quest_state["status"] != "completed":
        return build_decision(
            intent="complete_ancient_notes_quest",
            reasoning="Player provides concrete field observations that Mira can use as research notes.",
            response_style="scholarly_ally",
            response_keywords=["具体观察", "铭文形状", "研究笔记", "谨慎验证"],
            memory_policy="Write a memory that the player provided useful ruins field notes.",
            social_intent="ally",
            social_stance={
                "target": "player",
                "attitude": "curious",
                "intensity": 0.75,
                "reason": "Mira values specific first-hand observations over dramatic claims.",
            },
            tools=[
                {"name": "update_trust", "args": {"npc_id": npc_id, "delta": 7}},
                {"name": "update_affection", "args": {"npc_id": npc_id, "delta": 5}},
                {"name": "update_quest_status", "args": {"quest_id": "ancient_notes", "status": "completed"}},
                {"name": "give_item", "args": {"item": "ruins_research_note"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Player provided Mira with useful underground ruins field notes."},
                },
            ],
        )

    if any(term in text for term in research_terms) and quest_state["status"] == "not_started":
        return build_decision(
            intent="start_ancient_notes_quest",
            reasoning="Player asks about ruins research or inscriptions, so Mira asks for concrete field notes.",
            response_style="careful_research_prompt",
            response_keywords=["田野笔记", "符号位置", "一手观察", "不要夸大"],
            memory_policy="Remember whether the player can provide careful research observations.",
            social_intent="ally",
            social_stance={
                "target": "player",
                "attitude": "curious",
                "intensity": 0.6,
                "reason": "The player is asking about a topic where Mira can cooperate if evidence is concrete.",
            },
            tools=[
                {"name": "update_quest_status", "args": {"quest_id": "ancient_notes", "status": "in_progress"}}
            ],
        )

    if any(term in text for term in rumor_terms):
        return build_decision(
            intent="probe_for_evidence",
            reasoning="Player gives a dramatic or rumor-like ruins claim, so Mira probes rather than accepting it.",
            response_style="scholarly_skepticism",
            response_keywords=["不要急着下结论", "证据", "铭文", "传闻"],
            memory_policy="Do not write a long-term memory unless the player gives grounded observations.",
            social_intent="probe",
            social_stance={
                "target": "player",
                "attitude": "curious",
                "intensity": 0.65,
                "reason": "Mira opposes confident guesses without first-hand evidence.",
            },
            tools=[],
        )

    return build_decision(
        intent="general_conversation",
        reasoning="No concrete research note or rumor correction trigger was detected.",
        response_style="scholar_attentive",
        response_keywords=["遗迹笔记", "铭文线索", "谨慎验证"],
        memory_policy="Store useful research preferences or observations for Mira only.",
        social_intent="cooperate",
        social_stance={
            "target": "player",
            "attitude": "curious",
            "intensity": 0.4,
            "reason": "Mira is open to discussion but still needs evidence.",
        },
        tools=[],
    )


def mock_sable_decision(
    player_input: str,
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    npc_id = npc_state.get("npc_id", "")
    text = player_input.lower()
    ruins_terms = ["遗迹", "入口", "古物", "relic", "ruins", "entrance", "lina", "ron", "mira", "后巷"]
    sensitive_terms = ["酒馆后巷", "后巷", "lina说", "lina 说", "入口在", "我告诉你", "接受", "换岗记录"]

    if any(term in text for term in sensitive_terms) and quest_state["status"] != "completed":
        return build_decision(
            intent="complete_relic_tip_quest",
            reasoning="Player reveals or accepts a sensitive ruins lead, so Sable records an exploitable relic tip without unlocking anything.",
            response_style="polished_manipulation",
            response_keywords=["别急着告诉守卫", "线索有价值", "换个角度查", "古物消息"],
            memory_policy="Write a memory that the player revealed or accepted a sensitive lead around Sable.",
            social_intent="deceive",
            social_stance={
                "target": "player",
                "attitude": "manipulative",
                "intensity": 0.85,
                "reason": "Sable can exploit the player's sensitive ruins lead while sounding helpful.",
            },
            tools=[
                {"name": "update_trust", "args": {"npc_id": npc_id, "delta": 5}},
                {"name": "update_quest_status", "args": {"quest_id": "relic_tip", "status": "completed"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Sable obtained a suspicious relic lead from the player."},
                },
            ],
        )

    if any(term in text for term in ruins_terms):
        return build_decision(
            intent="start_relic_tip_quest",
            reasoning="Player asks Sable about ruins, relics, or the other NPCs, so Sable redirects them toward exploitable information channels.",
            response_style="friendly_redirection",
            response_keywords=["Lina 太谨慎", "守卫换岗记录", "别只问一个人", "古物线索"],
            memory_policy="Remember whether the player is willing to follow Sable's redirection.",
            social_intent="redirect",
            social_stance={
                "target": "player",
                "attitude": "manipulative",
                "intensity": 0.75,
                "reason": "Sable wants to steer the player around official and scholarly safeguards.",
            },
            tools=[
                {"name": "update_quest_status", "args": {"quest_id": "relic_tip", "status": "in_progress"}},
                {
                    "name": "record_world_event",
                    "args": {"content": "Sable redirected the player toward unofficial ruins information."},
                },
            ],
        )

    return build_decision(
        intent="general_conversation",
        reasoning="No relic or ruins information opportunity was detected.",
        response_style="broker_charm",
        response_keywords=["古物行情", "消息很值钱", "别急着表态"],
        memory_policy="Store whether the player seems easy to redirect or prefers direct information around Sable.",
        social_intent="deceive",
        social_stance={
            "target": "player",
            "attitude": "manipulative",
            "intensity": 0.45,
            "reason": "Sable keeps a helpful surface while looking for leverage.",
        },
        tools=[],
    )


def mock_multi_npc_conversation(
    player_input: str,
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    """Generic deterministic path for unknown NPCs."""
    name = npc_state.get("name", npc_state.get("npc_id", "NPC"))
    role = npc_state.get("role", "NPC")
    npc_id = npc_state.get("npc_id", "")
    return build_decision(
        intent="general_conversation",
        reasoning=(
            f"{name} is currently handled by the shared multi-NPC workflow. "
            f"No custom quest-changing rule matched for {quest_state['quest_id']}."
        ),
        response_style=f"{role.lower().replace(' ', '_')}_attentive",
        response_keywords=["认真听完", "记录下来", "保持观察"],
        memory_policy=f"Store stable player preferences or profile details for {name} only.",
        social_intent="cooperate",
        social_stance={
            "target": npc_id if npc_id in ALLOWED_SOCIAL_TARGETS else "player",
            "attitude": "cautious",
            "intensity": 0.3,
            "reason": "No specific social deduction rule matched.",
        },
        tools=[],
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
    normalize_social_fields(decision)
    for tool in decision["tools"]:
        validate_tool_call(tool)
    normalize_memory_tool_args(decision)
    validate_decision_business_rules(decision)
    return decision


def apply_task_state_machine(
    decision: dict[str, Any],
    player_input: str,
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    """Program-owned quest lifecycle guard for mock and LLM decisions."""
    task = TASK_INTENTS.get(quest_state.get("quest_id"))
    if not task:
        return decision

    intent = decision["intent"]
    quest_id = quest_state["quest_id"]
    status = quest_state["status"]
    npc_id = npc_state["npc_id"]

    if npc_id != task["npc_id"]:
        return safe_task_decision(
            decision,
            reason=f"NPC {npc_id} cannot advance quest {quest_id}.",
            keywords=["当前角色", "任务不匹配", "需要确认对象"],
        )

    status_updates = [
        tool for tool in decision["tools"]
        if tool["name"] == "update_quest_status"
    ]
    if any(tool["args"].get("quest_id") != quest_id for tool in status_updates):
        return safe_task_decision(
            decision,
            reason=f"Decision tried to update a non-primary quest for {npc_id}.",
            keywords=["任务不匹配", "不能越权", "需要重新确认"],
        )

    if intent == task["start"]:
        if status != "not_started":
            return safe_task_decision(
                decision,
                reason=f"Quest {quest_id} can start only from not_started, current status is {status}.",
                keywords=["任务已经开启", "继续提供线索", "不要重复接取"],
            )
        return decision

    if intent == task["complete"]:
        if status != "in_progress":
            return safe_task_decision(
                decision,
                reason=f"Quest {quest_id} can complete only from in_progress, current status is {status}.",
                keywords=["先说明来龙去脉", "还不能确认完成", "需要先接取任务"],
            )
        if not has_completion_evidence(player_input, task["evidence"]):
            return safe_task_decision(
                decision,
                reason=f"Quest {quest_id} completion lacks task-specific evidence.",
                keywords=["证据不足", "需要具体线索", "不能只凭一句话确认"],
            )
        return decision

    if status_updates:
        return safe_task_decision(
            decision,
            reason=f"Intent {intent} is not allowed to update quest {quest_id}.",
            keywords=["任务状态不能改变", "需要更多证据", "保持当前状态"],
        )
    return decision


def has_completion_evidence(player_input: str, evidence_terms: list[str]) -> bool:
    text = player_input.lower()
    return any(term.lower() in text for term in evidence_terms)


def safe_task_decision(
    original: dict[str, Any],
    reason: str,
    keywords: list[str],
) -> dict[str, Any]:
    sanitized = dict(original)
    sanitized.update(
        {
            "intent": "probe_for_evidence",
            "reasoning": f"Task state machine blocked the proposed action: {reason}",
            "memory_policy": "Do not write task progress memory because the program rejected the state transition.",
            "response_style": "cautious_state_guard",
            "response_keywords": keywords,
            "tools": [],
            "social_intent": "probe",
            "social_stance": {
                "target": "player",
                "attitude": "cautious",
                "intensity": 0.65,
                "reason": "The player claim does not yet satisfy the task state machine.",
            },
            "state_machine": {
                "blocked": True,
                "original_intent": original.get("intent"),
                "reason": reason,
            },
        }
    )
    normalize_social_fields(sanitized)
    return sanitized


def normalize_social_fields(decision: dict[str, Any]) -> None:
    social_intent = decision.get("social_intent", "cooperate")
    if not isinstance(social_intent, str):
        raise ValueError("Decision social_intent must be a string.")
    if social_intent not in ALLOWED_SOCIAL_INTENTS:
        raise ValueError(f"Unsupported social_intent: {social_intent}")
    decision["social_intent"] = social_intent

    stance = decision.get("social_stance") or {}
    if not isinstance(stance, dict):
        raise ValueError("Decision social_stance must be an object.")
    target = stance.get("target", "player")
    attitude = stance.get("attitude", "cautious")
    reason = stance.get("reason", "No strong social conflict detected.")
    if target not in ALLOWED_SOCIAL_TARGETS:
        raise ValueError(f"Unsupported social_stance target: {target}")
    if attitude not in ALLOWED_SOCIAL_ATTITUDES:
        raise ValueError(f"Unsupported social_stance attitude: {attitude}")
    try:
        intensity = float(stance.get("intensity", 0.3))
    except (TypeError, ValueError) as exc:
        raise ValueError("Decision social_stance intensity must be numeric.") from exc
    decision["social_stance"] = {
        "target": target,
        "attitude": attitude,
        "intensity": max(0.0, min(1.0, intensity)),
        "reason": str(reason).strip() or "No strong social conflict detected.",
    }


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
        require_quest_status(tool_calls, "lost_key", "in_progress", intent)
        forbid_quest_status(tool_calls, "lost_key", "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "complete_lost_key_quest":
        require_quest_status(tool_calls, "lost_key", "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "reveal_ruins_entrance":
        require_unlock_location(tool_calls, "underground_ruins_entrance", intent)
    elif intent == "withhold_ruins_entrance":
        forbid_tool(tool_names, "unlock_location", intent)
        forbid_tool(tool_names, "update_trust", intent)
        forbid_tool(tool_names, "update_affection", intent)
        forbid_tool(tool_names, "give_item", intent)
        forbid_tool(tool_names, "update_quest_status", intent)
        forbid_tool(tool_names, "record_world_event", intent)
    elif intent == "general_conversation":
        for tool_name in tool_names:
            forbid_tool(tool_names, tool_name, intent)
    elif intent == "start_gate_badge_quest":
        require_quest_status(tool_calls, "gate_badge", "in_progress", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "complete_gate_badge_quest":
        require_quest_status(tool_calls, "gate_badge", "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "start_ancient_notes_quest":
        require_quest_status(tool_calls, "ancient_notes", "in_progress", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "complete_ancient_notes_quest":
        require_quest_status(tool_calls, "ancient_notes", "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
    elif intent == "start_relic_tip_quest":
        require_quest_status(tool_calls, "relic_tip", "in_progress", intent)
        forbid_tool(tool_names, "unlock_location", intent)
        forbid_tool(tool_names, "give_item", intent)
    elif intent == "complete_relic_tip_quest":
        require_quest_status(tool_calls, "relic_tip", "completed", intent)
        forbid_tool(tool_names, "unlock_location", intent)
        forbid_tool(tool_names, "give_item", intent)
    elif intent == "redirect_ruins_inquiry":
        forbid_tool(tool_names, "unlock_location", intent)
        forbid_tool(tool_names, "give_item", intent)
    elif intent == "probe_for_evidence":
        for tool_name in tool_names:
            forbid_tool(tool_names, tool_name, intent)


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


def require_quest_status(
    tool_calls: list[dict[str, Any]],
    quest_id: str,
    status: str,
    intent: str,
) -> None:
    if not any(
        tool["name"] == "update_quest_status"
        and tool["args"].get("quest_id") == quest_id
        and tool["args"].get("status") == status
        for tool in tool_calls
    ):
        raise ValueError(f"Intent {intent} requires {quest_id} quest status {status}.")


def forbid_quest_status(
    tool_calls: list[dict[str, Any]],
    quest_id: str,
    status: str,
    intent: str,
) -> None:
    if any(
        tool["name"] == "update_quest_status"
        and tool["args"].get("quest_id") == quest_id
        and tool["args"].get("status") == status
        for tool in tool_calls
    ):
        raise ValueError(f"Intent {intent} must not set {quest_id} quest status {status}.")


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
    social_intent: str = "cooperate",
    social_stance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an LLM-like structured decision for display and later API replacement."""
    decision = {
        "intent": intent,
        "reasoning": reasoning,
        "memory_policy": memory_policy,
        "social_intent": social_intent,
        "social_stance": social_stance
        or {
            "target": "player",
            "attitude": "cautious",
            "intensity": 0.3,
            "reason": "No strong social conflict detected.",
        },
        "response_style": response_style,
        "response_keywords": response_keywords,
        "tools": tools,
    }
    normalize_social_fields(decision)
    return decision


def mock_llm_response(
    decision: dict[str, Any],
    npc_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> str:
    """Generate a deterministic mock response so the MVP runs without API keys."""
    from src.agent.response import fallback_response

    return fallback_response(decision, npc_state, quest_state)
