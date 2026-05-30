from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.agent.decision import decide_next_action
from src.agent.environment import NarrativeEnvironment
from src.agent.memory_jobs import enqueue_memory_job
from src.agent.response import generate_npc_response
from src.storage import database
from src.tools import sqlite_tools


NPC_ID = "lina"


@dataclass(frozen=True)
class AgentRun:
    npc_id: str
    player_input: str
    npc_response: str
    npc_state: dict[str, Any]
    player_state: dict[str, Any]
    quest_state: dict[str, Any]
    recent_context: list[dict[str, Any]]
    retrieved_lore: list[dict[str, Any]]
    retrieved_memories: list[dict[str, Any]]
    state_snapshot: dict[str, Any]
    decision: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    memory_policy: dict[str, Any]
    memory_writes: list[dict[str, Any]]
    state_changes: list[dict[str, Any]]
    workflow_steps: list[dict[str, str]]
    timings: dict[str, float]
    log_id: int
    memory_job_status: dict[str, Any]


def run_agent_turn(
    player_input: str,
    npc_id: str = NPC_ID,
    memory_retrieval_mode: str = "typed",
    memory_policy_enabled: bool = True,
) -> AgentRun:
    """Run the MVP agent workflow from input to trace logging."""
    total_started = perf_counter()
    timings: dict[str, float] = {}
    database.initialize_database()

    environment = NarrativeEnvironment()
    context_started = perf_counter()
    observation = environment.observe(
        player_input=player_input,
        npc_id=npc_id,
        memory_retrieval_mode=memory_retrieval_mode,
    )
    timings["context_retrieval_ms"] = elapsed_ms(context_started)
    recent_context = observation.recent_context
    retrieved_lore = observation.retrieved_lore
    retrieved_memories = observation.retrieved_memories
    npc_before = observation.npc_state
    player_before = observation.player_state
    quest_before = observation.quest_state
    state_snapshot = build_state_snapshot(npc_before, player_before, quest_before)

    decision_started = perf_counter()
    decision = decide_next_action(
        player_input=player_input,
        npc_state=observation.npc_state,
        player_state=observation.player_state,
        quest_state=observation.quest_state,
        retrieved_lore=observation.retrieved_lore,
        retrieved_long_term_memories=observation.retrieved_memories,
        state_snapshot=state_snapshot,
        recent_short_term_context=observation.recent_context,
    )
    timings["decision_ms"] = elapsed_ms(decision_started)
    state_before = build_state_snapshot(npc_before, player_before, quest_before)
    decision["memory_retrieval_mode"] = memory_retrieval_mode
    decision["state_before"] = state_before

    npc_action = environment.propose_action_from_decision(decision, observation)
    npc_action = environment.validate(npc_action, observation)
    decision = dict(npc_action.raw_decision)
    decision["memory_retrieval_mode"] = memory_retrieval_mode
    decision["state_before"] = state_before

    tools_started = perf_counter()
    action_result = environment.execute(npc_action, observation)
    timings["tool_execution_ms"] = elapsed_ms(tools_started)

    npc_after = database.get_npc(npc_id)
    player_after = database.get_player_state()
    quest_after = database.get_primary_quest_for_npc(npc_id)
    tool_calls = action_result.executed_tools
    state_changes = action_result.state_changes
    decision["state_after"] = action_result.state_after
    decision["environment"] = environment.trace_payload(observation, npc_action, action_result)
    decision["context_inputs"] = {
        "retrieved_lore": retrieved_lore,
        "retrieved_memories": retrieved_memories,
        "state_snapshot": decision["state_after"],
        "recent_context": recent_context,
    }

    response_started = perf_counter()
    npc_response, response_generation = generate_npc_response(
        player_input=player_input,
        decision=decision,
        npc_state=npc_after,
        player_state=player_after,
        quest_state=quest_after,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        state_snapshot=decision["state_after"],
        recent_context=recent_context,
        tool_calls=tool_calls,
        state_changes=state_changes,
        observation=observation,
        npc_action=npc_action,
        action_result=action_result,
    )
    timings["response_ms"] = elapsed_ms(response_started)
    decision["response_generation"] = response_generation

    memory_job_status: dict[str, Any]
    if memory_policy_enabled:
        memory_started = perf_counter()
        memory_job = enqueue_memory_job(
            npc_id=npc_id,
            player_input=player_input,
            npc_response=npc_response,
            recent_context=recent_context,
            retrieved_lore=retrieved_lore,
            retrieved_memories=retrieved_memories,
            state_before=state_before,
            state_after=decision["state_after"],
            tool_calls=tool_calls,
            state_changes=state_changes,
        )
        timings["memory_realtime_ms"] = elapsed_ms(memory_started)
        timings["memory_policy_ms"] = 0.0
        timings["embedding_write_ms"] = 0.0
        memory_job_status = {
            "id": memory_job["id"],
            "status": memory_job["status"],
            "background_memory_enabled": True,
        }
        memory_policy = {
            "candidates": [
                {
                    "should_write": False,
                    "npc_id": npc_id,
                    "content": "",
                    "memory_type": "queued",
                    "importance": 0,
                    "tags": [],
                    "confidence": 0.0,
                    "reason": "Long-term memory policy queued for background processing.",
                }
            ],
            "summary": "Long-term memory queued for background processing.",
            "embedding_updates": [],
            "background_memory_enabled": True,
            "memory_job_status": memory_job_status,
        }
        memory_writes = []
    else:
        memory_policy = {
            "candidates": [
                {
                    "should_write": False,
                    "npc_id": npc_id,
                    "content": "",
                    "memory_type": "none",
                    "importance": 0,
                    "tags": [],
                    "confidence": 0.0,
                    "reason": "Long-term memory policy disabled for ablation.",
                }
            ],
            "summary": "Long-term memory policy disabled for ablation.",
            "embedding_updates": [],
            "background_memory_enabled": False,
        }
        memory_writes = []
        timings["memory_policy_ms"] = 0.0
        timings["embedding_write_ms"] = 0.0
        timings["memory_realtime_ms"] = 0.0
        memory_job_status = {
            "id": None,
            "status": "disabled",
            "background_memory_enabled": False,
        }
    decision["memory_job_status"] = memory_job_status
    decision["background_memory_enabled"] = memory_job_status["background_memory_enabled"]
    logging_started = perf_counter()
    workflow_steps = build_workflow_steps(
        recent_context=recent_context,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        decision=decision,
        tool_calls=tool_calls,
        memory_writes=memory_writes,
        state_changes=state_changes,
    )
    timings["pre_logging_total_ms"] = elapsed_ms(total_started)
    decision["timings"] = dict(timings)
    log_id = database.log_interaction(
        npc_id=npc_id,
        player_input=player_input,
        npc_response=npc_response,
        recent_context=recent_context,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        state_snapshot=decision["state_after"],
        memory_policy=memory_policy,
        memory_writes=memory_writes,
        decision=decision,
        tool_calls=tool_calls,
        state_changes=state_changes,
        workflow_steps=workflow_steps,
    )
    timings["logging_ms"] = elapsed_ms(logging_started)
    timings["total_ms"] = elapsed_ms(total_started)
    database.add_recent_interaction(
        npc_id=npc_id,
        player_input=player_input,
        npc_response=npc_response,
        metadata={
            "intent": decision["intent"],
            "log_id": log_id,
            "timings": timings,
        },
    )

    return AgentRun(
        npc_id=npc_id,
        player_input=player_input,
        npc_response=npc_response,
        npc_state=npc_after,
        player_state=player_after,
        quest_state=quest_after,
        recent_context=recent_context,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        state_snapshot=decision["state_after"],
        decision=decision,
        tool_calls=tool_calls,
        memory_policy=memory_policy,
        memory_writes=memory_writes,
        state_changes=state_changes,
        workflow_steps=workflow_steps,
        timings=timings,
        log_id=log_id,
        memory_job_status=memory_job_status,
    )


def elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def execute_tools(decision: dict[str, Any]) -> list[sqlite_tools.ToolExecution]:
    # Compatibility wrapper for older tests/imports; runtime execution goes through NarrativeEnvironment.
    return NarrativeEnvironment()._execute_tools(decision["tools"])


def build_state_snapshot(
    npc_state: dict[str, Any],
    player_state: dict[str, Any],
    quest_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "npc": {
            "npc_id": npc_state["npc_id"],
            "name": npc_state["name"],
            "role": npc_state["role"],
            "hidden_alignment": npc_state.get("hidden_alignment", "neutral"),
            "mood": npc_state["mood"],
            "trust": npc_state["trust"],
            "affection": npc_state["affection"],
        },
        "player": {
            "location": player_state["location"],
            "inventory": player_state["inventory"],
            "unlocked_locations": player_state["unlocked_locations"],
        },
        "quest": {
            "quest_id": quest_state["quest_id"],
            "title": quest_state["title"],
            "status": quest_state["status"],
        },
    }


def build_workflow_steps(
    recent_context: list[dict[str, Any]],
    retrieved_lore: list[dict[str, Any]],
    retrieved_memories: list[dict[str, Any]],
    decision: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    memory_writes: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Summarize the fixed Agent workflow for the UI trace panel."""
    return [
        {"stage": "Player Input", "result": "Received natural language input."},
        {"stage": "Short-Term Context", "result": f"Loaded {len(recent_context)} recent interaction(s)."},
        {"stage": "Lore Retrieval", "result": f"Retrieved {len(retrieved_lore)} world/NPC lore document(s)."},
        {
            "stage": "Long-Term Memory Retrieval",
            "result": (
                f"Mode: {decision.get('memory_retrieval_mode', 'typed')}; "
                f"retrieved {len(retrieved_memories)} relevant memories."
            ),
        },
        {"stage": "State Load", "result": "Loaded NPC, player, and quest state from SQLite."},
        {
            "stage": "Structured Decision",
            "result": f"Intent: {decision['intent']}; route: {decision.get('decision_route', 'unknown')}.",
        },
        {
            "stage": "Social Strategy",
            "result": (
                f"Intent: {decision.get('social_intent', 'cooperate')}; "
                f"stance: {decision.get('social_stance', {}).get('attitude', 'cautious')}."
            ),
        },
        {"stage": "Observation", "result": "Environment observed input, context, lore, memory, and SQLite state."},
        {
            "stage": "NPC Action",
            "result": f"Action intent: {decision.get('environment', {}).get('npc_action', {}).get('intent', decision['intent'])}.",
        },
        {
            "stage": "Action Validation",
            "result": (
                "Accepted."
                if decision.get("environment", {}).get("action_result", {}).get("accepted", True)
                else f"Blocked: {decision.get('environment', {}).get('action_result', {}).get('blocked_reason', 'unknown')}"
            ),
        },
        {"stage": "Environment Execution", "result": f"Executed {len(tool_calls)} environment-approved tool call(s)."},
        {"stage": "Action Result", "result": f"Recorded {len(state_changes)} state change(s)."},
        {
            "stage": "Response Generation",
            "result": (
                f"Style: {decision['response_style']}; "
                f"mode: {decision.get('response_generation', {}).get('mode', 'unknown')}."
            ),
        },
        {
            "stage": "Memory Policy",
            "result": (
                "Queued long-term memory for background processing."
                if decision.get("background_memory_enabled")
                else f"Wrote {len(memory_writes)} long-term memory record(s)."
            ),
        },
        {"stage": "Trace Logging", "result": f"Recorded {len(state_changes)} state changes."},
    ]


def collect_state_changes(
    npc_before: dict[str, Any],
    npc_after: dict[str, Any],
    player_before: dict[str, Any],
    player_after: dict[str, Any],
    quest_before: dict[str, Any],
    quest_after: dict[str, Any],
) -> list[dict[str, Any]]:
    changes = []
    for field in ["mood", "trust", "affection"]:
        if npc_before[field] != npc_after[field]:
            changes.append(
                {
                    "scope": "npc",
                    "field": field,
                    "before": npc_before[field],
                    "after": npc_after[field],
                }
            )
    for field in ["location", "inventory", "unlocked_locations"]:
        if player_before[field] != player_after[field]:
            changes.append(
                {
                    "scope": "player",
                    "field": field,
                    "before": player_before[field],
                    "after": player_after[field],
                }
            )
    if quest_before["status"] != quest_after["status"]:
        changes.append(
            {
                "scope": "quest",
                "field": "status",
                "before": quest_before["status"],
                "after": quest_after["status"],
            }
        )
    return changes
