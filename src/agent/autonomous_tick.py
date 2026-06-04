from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.agent.action_catalog import (
    get_available_actions,
    get_unavailable_actions_with_reasons,
    serialize_actions_for_llm_prompt,
)
from src.agent.arc_director import run_arc_director
from src.agent.environment import NarrativeEnvironment
from src.agent.llm_client import call_openai_compatible_json
from src.storage import database


AUTONOMOUS_DECISION_SYSTEM_PROMPT = """
You are the constrained autonomous decision layer for a narrative NPC runtime.
Return only JSON. You may reason about belief, emotion, goal, and plan, but you
must select at most one action from available_actions. You cannot directly
modify world state; the program will validate and execute any side effect.
"""


@dataclass(frozen=True)
class AutonomousTickResult:
    npc_id: str
    mode: str
    outcome: str
    trigger_event: dict[str, Any] | None
    observation: dict[str, Any]
    retrieved_memories: list[dict[str, Any]]
    available_actions: list[dict[str, Any]]
    unavailable_actions: list[dict[str, Any]]
    llm_decision: dict[str, Any]
    proposed_action: dict[str, Any]
    validation: dict[str, Any]
    action_result: dict[str, Any]
    plan_update: dict[str, Any]
    memory_candidate: dict[str, Any]
    reflection: dict[str, Any]
    proactive_message: dict[str, Any] | None
    tick_log_id: int
    timeline: list[dict[str, Any]]


def run_autonomous_tick(
    npc_id: str,
    mode: str = "llm_constrained",
    trigger_event_id: int | None = None,
    memory_retrieval_mode: str = "hybrid",
    run_director: bool = True,
) -> AutonomousTickResult:
    database.initialize_database()
    timeline = [timeline_event("tick_started", {"npc_id": npc_id, "mode": mode})]
    runtime = database.get_npc_runtime_state(npc_id)
    if runtime["lifecycle_status"] == "disabled" or not runtime["tick_enabled"]:
        return log_no_op_tick(
            npc_id=npc_id,
            mode=mode,
            validation={"status": "no_op", "reason": "npc_disabled"},
            timeline=timeline,
        )
    trigger_item = select_trigger_item(npc_id, trigger_event_id)
    if trigger_item is None:
        return log_no_op_tick(
            npc_id=npc_id,
            mode=mode,
            validation={"status": "no_op", "reason": "no_unseen_inbox_item"},
            timeline=timeline,
        )

    trigger_event = trigger_item["event"]
    environment = NarrativeEnvironment()
    observation = environment.observe(
        player_input="",
        npc_id=npc_id,
        memory_retrieval_mode=memory_retrieval_mode,
    )
    timeline.append(timeline_event("observation_built", {"trigger_event_id": trigger_event["id"]}))
    retrieved_memories = database.search_memories(
        trigger_event["content"],
        npc_id=npc_id,
        mode=memory_retrieval_mode,
    )
    scene_objects = database.list_scene_objects()
    npc_location = database.get_npc_location_state(npc_id)
    available_actions = get_available_actions(npc_id, trigger_event=trigger_event, observation=observation)
    unavailable_actions = get_unavailable_actions_with_reasons(
        npc_id,
        trigger_event=trigger_event,
        observation=observation,
    )
    timeline.append(
        timeline_event(
            "action_surface_built",
            {"available": len(available_actions), "unavailable": len(unavailable_actions)},
        )
    )
    if is_offline_autonomous_mode(mode):
        llm_decision = deterministic_fallback_decision(
            available_actions,
            trigger_event,
            f"mode={mode}",
        )
        timeline.append(timeline_event("deterministic_decision_selected", {"goal": llm_decision.get("goal", "")}))
    else:
        llm_decision = call_autonomous_llm(
            npc_id=npc_id,
            observation=observation,
            trigger_event=trigger_event,
            retrieved_memories=retrieved_memories,
            available_actions=available_actions,
            unavailable_actions=unavailable_actions,
        )
        timeline.append(timeline_event("llm_decision_received", {"goal": llm_decision.get("goal", "")}))
    proposed_action = normalize_selected_action(llm_decision.get("selected_action"))
    if not proposed_action.get("action_type") and proposed_action.get("raw_selected_action") is None and available_actions:
        llm_decision = deterministic_fallback_decision(
            available_actions,
            trigger_event,
            "LLM returned no valid selected_action.",
        )
        proposed_action = normalize_selected_action(llm_decision.get("selected_action"))
    validation = validate_selected_action(proposed_action, available_actions)
    validation = enrich_validation_with_unavailable_reason(validation, proposed_action, unavailable_actions)
    if validation["status"] == "allowed":
        cooldown_validation = validate_cooldown(npc_id, trigger_event, proposed_action)
        if cooldown_validation:
            validation = cooldown_validation
    if validation["status"] == "allowed" and has_pending_proactive_message(npc_id) and wants_proactive_message(llm_decision):
        validation = {
            "status": "skipped_by_budget",
            "reason": "npc already has an undelivered proactive message",
        }
    timeline.append(timeline_event("action_validated", {"status": validation["status"]}))

    action_result = empty_action_result(validation["status"])
    if validation["status"] == "allowed" and runtime["lifecycle_status"] == "active":
        action_result = execute_selected_action(
            selected_action=proposed_action,
            llm_decision=llm_decision,
            observation=observation,
            environment=environment,
        )
    elif runtime["lifecycle_status"] == "paused":
        validation = {
            "status": "paused_memory_only",
            "reason": "npc_paused",
        }
        action_result = empty_action_result("npc_paused")
    memory_candidate = normalize_memory_candidate(llm_decision.get("memory_candidate"))
    reflection = {
        "summary": str(llm_decision.get("reflection_summary", "")),
        "belief_update": str(llm_decision.get("belief_update", "")),
        "emotion": str(llm_decision.get("emotion", "")),
    }
    plan_update = {
        "goal": str(llm_decision.get("goal", "")),
        "current_step": str(llm_decision.get("plan_step", "")),
        "status": "active" if validation["status"] == "allowed" else "blocked",
        "blocker": "" if validation["status"] == "allowed" else validation.get("reason", validation["status"]),
    }
    persisted_plan = database.upsert_npc_plan(
        npc_id=npc_id,
        goal=plan_update["goal"],
        steps=[{"step": plan_update["current_step"], "status": plan_update["status"]}],
        current_step=plan_update["current_step"],
        status=plan_update["status"],
        blocker=plan_update["blocker"],
        source_event_id=int(trigger_event["id"]),
    )
    plan_update.update(
        {
            "id": persisted_plan["id"],
            "source_event_id": persisted_plan["source_event_id"],
        }
    )
    proactive_message = create_tick_message(
        npc_id=npc_id,
        trigger_event_id=int(trigger_event["id"]),
        llm_decision=llm_decision,
        validation=validation,
    )
    if validation["status"] == "allowed" and proactive_message:
        set_action_cooldown(npc_id, trigger_event, proposed_action)
    outcome = determine_outcome(validation, proactive_message, memory_candidate)
    timeline.append(timeline_event("tick_finished", {"outcome": outcome}))
    arc_director = (
        run_arc_director(use_llm=False)
        if run_director
        else {"skipped": True, "reason": "managed_by_living_world_scheduler"}
    )
    observation_payload = {
        "npc_id": observation.npc_id,
        "trigger_event": trigger_event,
        "visible_events": observation.visible_world_events,
        "quest_state": observation.quest_state,
        "arc_state": database.get_world_arc_state("ruins_chapter_1"),
        "scene_objects": scene_objects,
        "npc_location": npc_location,
        "arc_director": arc_director,
        "timeline": timeline,
    }
    tick_log = database.log_autonomous_tick(
        npc_id=npc_id,
        trigger_event_id=int(trigger_event["id"]),
        mode=mode,
        observation=observation_payload,
        retrieved_memories=retrieved_memories,
        available_actions=available_actions,
        unavailable_actions=unavailable_actions,
        llm_decision=llm_decision,
        proposed_action=proposed_action,
        validation=validation,
        action_result=action_result,
        plan_update=plan_update,
        memory_candidate=memory_candidate,
        reflection=reflection,
        proactive_message_id=proactive_message["id"] if proactive_message else None,
    )
    if proactive_message:
        proactive_message = database.update_proactive_message_tick_log(proactive_message["id"], int(tick_log["id"]))
    database.mark_npc_event_seen(int(trigger_item["id"]))
    return AutonomousTickResult(
        npc_id=npc_id,
        mode=mode,
        outcome=outcome,
        trigger_event=trigger_event,
        observation=observation_payload,
        retrieved_memories=retrieved_memories,
        available_actions=available_actions,
        unavailable_actions=unavailable_actions,
        llm_decision=llm_decision,
        proposed_action=proposed_action,
        validation=validation,
        action_result=action_result,
        plan_update=plan_update,
        memory_candidate=memory_candidate,
        reflection=reflection,
        proactive_message=proactive_message,
        tick_log_id=int(tick_log["id"]),
        timeline=timeline,
    )


def log_no_op_tick(
    npc_id: str,
    mode: str,
    validation: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> AutonomousTickResult:
    action_result = empty_action_result(validation["reason"])
    timeline.append(timeline_event("tick_finished", {"outcome": "no_op"}))
    observation = {"timeline": timeline}
    tick_log = database.log_autonomous_tick(
        npc_id=npc_id,
        trigger_event_id=None,
        mode=mode,
        observation=observation,
        retrieved_memories=[],
        available_actions=[],
        unavailable_actions=[],
        llm_decision={},
        proposed_action={},
        validation=validation,
        action_result=action_result,
        plan_update={},
        memory_candidate={},
        reflection={},
        proactive_message_id=None,
    )
    return AutonomousTickResult(
        npc_id=npc_id,
        mode=mode,
        outcome="no_op",
        trigger_event=None,
        observation=observation,
        retrieved_memories=[],
        available_actions=[],
        unavailable_actions=[],
        llm_decision={},
        proposed_action={},
        validation=validation,
        action_result=action_result,
        plan_update={},
        memory_candidate={},
        reflection={},
        proactive_message=None,
        tick_log_id=int(tick_log["id"]),
        timeline=timeline,
    )


def select_trigger_item(npc_id: str, trigger_event_id: int | None) -> dict[str, Any] | None:
    inbox = database.get_npc_event_inbox(npc_id, include_seen=False, limit=50)
    if trigger_event_id is None:
        return inbox[0] if inbox else None
    for item in inbox:
        if int(item["event_id"]) == int(trigger_event_id):
            return item
    return None


def call_autonomous_llm(
    npc_id: str,
    observation: Any,
    trigger_event: dict[str, Any],
    retrieved_memories: list[dict[str, Any]],
    available_actions: list[dict[str, Any]],
    unavailable_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "npc_profile": {
            "npc_id": observation.npc_id,
            "name": observation.npc_state.get("name"),
            "role": observation.npc_state.get("role"),
            "hidden_alignment": observation.npc_state.get("hidden_alignment"),
        },
        "npc_state": observation.npc_state,
        "player_state": observation.player_state,
        "quest_state": observation.quest_state,
        "trigger_event": trigger_event,
        "visible_events": observation.visible_world_events,
        "arc_state": database.get_world_arc_state("ruins_chapter_1"),
        "scene_objects": database.list_scene_objects(),
        "npc_location": database.get_npc_location_state(npc_id),
        "retrieved_memories": retrieved_memories,
        "active_plan": database.get_npc_plan(npc_id) or {},
        "available_actions": serialize_actions_for_llm_prompt(available_actions),
        "unavailable_actions": unavailable_actions,
    }
    try:
        return call_openai_compatible_json(
            system_prompt=AUTONOMOUS_DECISION_SYSTEM_PROMPT,
            user_payload=payload,
        )
    except Exception as exc:
        return deterministic_fallback_decision(available_actions, trigger_event, str(exc))


def is_offline_autonomous_mode(mode: str) -> bool:
    return mode in {"deterministic_fallback", "offline", "mock"}


def deterministic_fallback_decision(
    available_actions: list[dict[str, Any]],
    trigger_event: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    selected = available_actions[0] if available_actions else {}
    return {
        "belief_update": f"Fallback used because LLM failed: {reason}",
        "emotion": "cautious",
        "goal": f"respond_to_{trigger_event.get('event_type', 'event')}",
        "plan_step": selected.get("action_type", "no_available_action"),
        "selected_action": {
            "action_type": selected.get("action_type", "no_op"),
            "args": fallback_args_for_action(selected),
        },
        "proactive_message": "",
        "memory_candidate": "",
        "reflection_summary": reason,
        "fallback_reason": reason,
    }


def fallback_args_for_action(action: dict[str, Any]) -> dict[str, Any]:
    schema = action.get("args_schema") if isinstance(action, dict) else {}
    if not isinstance(schema, dict):
        return {}
    args = {}
    for field, expected_type in schema.items():
        args[field] = 0 if expected_type == "integer" else ""
    return args


def normalize_selected_action(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "action_type": str(value.get("action_type", "")),
            "args": value.get("args") if isinstance(value.get("args"), dict) else {},
        }
    return {"action_type": "", "args": {}, "raw_selected_action": value}


def validate_selected_action(
    selected_action: dict[str, Any],
    available_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_selected = selected_action.get("raw_selected_action")
    if raw_selected is not None:
        return {
            "status": "rejected_one_command_at_a_time",
            "reason": "selected_action must be one object, not multiple commands",
            "raw_selected_action": raw_selected,
        }
    action_type = selected_action.get("action_type")
    by_type = {action["action_type"]: action for action in available_actions}
    if action_type not in by_type:
        return {
            "status": "rejected_by_available_actions",
            "reason": f"selected action {action_type} is not in available_actions",
        }
    arg_error = validate_action_args(selected_action.get("args", {}), by_type[action_type].get("args_schema", {}))
    if arg_error:
        return {
            "status": "rejected_invalid_args",
            "reason": f"selected action {action_type} has invalid args",
            "arg_error": arg_error,
        }
    return {"status": "allowed", "reason": "selected action is available and args match schema"}


def enrich_validation_with_unavailable_reason(
    validation: dict[str, Any],
    proposed_action: dict[str, Any],
    unavailable_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    if validation["status"] != "rejected_by_available_actions":
        return validation
    action_type = proposed_action.get("action_type")
    for action in unavailable_actions:
        if action.get("action_type") == action_type:
            enriched = dict(validation)
            enriched["reason"] = str(action.get("reason") or validation["reason"])
            enriched["failed_preconditions"] = action.get("failed_preconditions", [])
            return enriched
    return validation


def validate_action_args(args: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
    for field, expected_type in schema.items():
        if field not in args:
            return {"field": field, "expected": expected_type, "actual": "missing"}
        value = args[field]
        if expected_type == "string" and not isinstance(value, str):
            return {"field": field, "expected": expected_type, "actual": type(value).__name__}
        if expected_type == "integer" and not isinstance(value, int):
            return {"field": field, "expected": expected_type, "actual": type(value).__name__}
    return None


def execute_selected_action(
    selected_action: dict[str, Any],
    llm_decision: dict[str, Any],
    observation: Any,
    environment: NarrativeEnvironment,
) -> dict[str, Any]:
    decision = decision_from_selected_action(selected_action, llm_decision)
    npc_action = environment.propose_action_from_decision(decision, observation)
    action_result = environment.execute(npc_action, observation)
    return asdict(action_result)


def decision_from_selected_action(selected_action: dict[str, Any], llm_decision: dict[str, Any]) -> dict[str, Any]:
    action_type = str(selected_action.get("action_type", ""))
    intent = "general_conversation"
    social_intent = "cooperate"
    tools: list[dict[str, Any]] = []
    if action_type in {
        "offer_minor_task",
        "ask_clarifying_question",
        "refuse_restricted_info",
        "reveal_partial_lore",
        "secure_tavern_back_alley",
        "warn_quietly",
    }:
        intent = "withhold_ruins_entrance"
        social_intent = "probe" if action_type != "refuse_restricted_info" else "conceal"
        if action_type == "offer_minor_task":
            intent = "start_lost_key_quest"
            tools = [{"name": "update_quest_status", "args": {"quest_id": "lost_key", "status": "in_progress"}}]
        elif action_type == "secure_tavern_back_alley":
            tools = [
                {
                    "name": "record_world_event",
                    "args": {"content": "Lina quietly secured the tavern back alley after ruins attention."},
                }
            ]
    elif action_type in {
        "mislead_player",
        "redirect_to_false_clue",
        "ask_leading_question",
        "probe_player_secret",
        "trade_rumor",
        "plant_misleading_tip",
    }:
        intent = "redirect_ruins_inquiry"
        social_intent = "deceive"
        tools = [
            {
                "name": "record_world_event",
                "args": {"content": f"Sable pursued a deceptive autonomous action: {action_type}."},
            }
        ]
    elif action_type in {
        "verify_badge",
        "block_gate_access",
        "grant_conditional_access",
        "warn_player",
        "request_evidence",
        "patrol_sensitive_route",
        "escalate_lockdown",
    }:
        intent = "probe_for_evidence"
        social_intent = "probe"
        if action_type == "grant_conditional_access":
            intent = "start_gate_badge_quest"
            tools = [{"name": "update_quest_status", "args": {"quest_id": "gate_badge", "status": "in_progress"}}]
        elif action_type in {"patrol_sensitive_route", "escalate_lockdown"}:
            tools = [
                {
                    "name": "record_world_event",
                    "args": {"content": f"Ron took a procedural safety action: {action_type}."},
                }
            ]
    elif action_type == "request_field_notes":
        intent = "start_ancient_notes_quest"
        social_intent = "cooperate"
        tools = [{"name": "update_quest_status", "args": {"quest_id": "ancient_notes", "status": "in_progress"}}]
    elif action_type in {
        "preserve_research_record",
        "inspect_clue",
        "connect_evidence",
        "archive_memory",
        "suggest_next_investigation",
    }:
        intent = "general_conversation"
        social_intent = "cooperate"
    return {
        "intent": intent,
        "reasoning": str(llm_decision.get("reflection_summary") or llm_decision.get("belief_update") or action_type),
        "memory_policy": "Autonomous tick memory handled by autonomous trace.",
        "response_style": "autonomous_proactive",
        "response_keywords": [action_type, str(llm_decision.get("goal", ""))],
        "tools": tools,
        "social_intent": social_intent,
        "social_stance": {
            "target": "player",
            "attitude": "manipulative" if social_intent == "deceive" else "cautious",
            "intensity": 0.6,
            "reason": str(llm_decision.get("goal", "autonomous tick")),
        },
    }


def create_tick_message(
    npc_id: str,
    trigger_event_id: int,
    llm_decision: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any] | None:
    content = str(llm_decision.get("proactive_message", "")).strip()
    if validation["status"] == "rejected_by_available_actions":
        content = safe_rejection_message(npc_id)
    elif validation["status"] != "allowed":
        content = ""
    if not content:
        return None
    return database.create_proactive_message(
        npc_id=npc_id,
        content=content,
        trigger_event_id=trigger_event_id,
        tick_log_id=None,
        priority=8 if validation["status"] == "allowed" else 4,
    )


def has_pending_proactive_message(npc_id: str) -> bool:
    return bool(database.get_proactive_messages(npc_id=npc_id, delivered=False, limit=1))


def wants_proactive_message(llm_decision: dict[str, Any]) -> bool:
    return bool(str(llm_decision.get("proactive_message", "")).strip())


def validate_cooldown(
    npc_id: str,
    trigger_event: dict[str, Any],
    proposed_action: dict[str, Any],
) -> dict[str, Any] | None:
    cooldown_key = build_cooldown_key(npc_id, trigger_event, proposed_action)
    cooldown = database.get_npc_cooldown(npc_id, cooldown_key)
    if not cooldown:
        return None
    if str(cooldown["until_turn_or_timestamp"]) > datetime.now(timezone.utc).isoformat():
        return {
            "status": "skipped_by_cooldown",
            "reason": cooldown["reason"],
            "cooldown_key": cooldown_key,
            "until_turn_or_timestamp": cooldown["until_turn_or_timestamp"],
        }
    return None


def set_action_cooldown(
    npc_id: str,
    trigger_event: dict[str, Any],
    proposed_action: dict[str, Any],
) -> dict[str, Any]:
    return database.set_npc_cooldown(
        npc_id=npc_id,
        cooldown_key=build_cooldown_key(npc_id, trigger_event, proposed_action),
        until_turn_or_timestamp=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        reason=f"cooldown for {trigger_event.get('event_type')} -> {proposed_action.get('action_type')}",
    )


def build_cooldown_key(
    npc_id: str,
    trigger_event: dict[str, Any],
    proposed_action: dict[str, Any],
) -> str:
    return f"{npc_id}:{trigger_event.get('event_type', 'event')}:{proposed_action.get('action_type', 'action')}"


def safe_rejection_message(npc_id: str) -> str:
    npc = database.get_npc(npc_id)
    return f"{npc.get('name', npc_id)} 暂时只留下含糊的提醒，没有改变任何世界状态。"


def determine_outcome(
    validation: dict[str, Any],
    proactive_message: dict[str, Any] | None,
    memory_candidate: dict[str, Any],
) -> str:
    if validation["status"] == "paused_memory_only":
        return "memory_only"
    if validation["status"] == "skipped_by_cooldown":
        return "no_op"
    if validation["status"] == "skipped_by_budget":
        return "no_op"
    if validation["status"] == "rejected_by_available_actions":
        return "safe_message" if proactive_message else "blocked"
    if validation["status"] != "allowed":
        return "blocked"
    if proactive_message:
        return "proactive_message"
    if memory_candidate.get("content"):
        return "memory_only"
    return "no_op"


def normalize_memory_candidate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    content = str(value or "").strip()
    return {"content": content} if content else {}


def empty_action_result(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "blocked_reason": reason,
        "executed_tools": [],
        "state_before": {},
        "state_after": {},
        "state_changes": [],
        "events": [],
        "response_constraints": ["Do not claim world-state changes."],
    }


def timeline_event(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": stage,
        "payload": payload,
        "at": datetime.now(timezone.utc).isoformat(),
    }
