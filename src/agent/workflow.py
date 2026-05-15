from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agent.context import build_context_inputs
from src.agent.decision import decide_next_action
from src.agent.memory_policy import MemoryPolicyInput, apply_memory_policy
from src.agent.response import generate_npc_response
from src.agent.semantic_retrieval import ensure_embeddings_for_memory_writes
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
    log_id: int


def run_agent_turn(
    player_input: str,
    npc_id: str = NPC_ID,
    memory_retrieval_mode: str = "typed",
    memory_policy_enabled: bool = True,
) -> AgentRun:
    """Run the MVP agent workflow from input to trace logging."""
    database.initialize_database()

    context_inputs = build_context_inputs(
        player_input=player_input,
        npc_id=npc_id,
        memory_retrieval_mode=memory_retrieval_mode,
    )
    recent_context = context_inputs["recent_context"]
    retrieved_lore = context_inputs["retrieved_lore"]
    retrieved_memories = context_inputs["retrieved_memories"]
    state_snapshot = context_inputs["state_snapshot"]
    npc_before = database.get_npc(npc_id)
    player_before = database.get_player_state()
    quest_before = database.get_primary_quest_for_npc(npc_id)

    decision = decide_next_action(
        player_input=player_input,
        npc_state=npc_before,
        player_state=player_before,
        quest_state=quest_before,
        retrieved_lore=retrieved_lore,
        retrieved_long_term_memories=retrieved_memories,
        state_snapshot=state_snapshot,
        recent_short_term_context=recent_context,
    )
    decision["memory_retrieval_mode"] = memory_retrieval_mode
    decision["state_before"] = build_state_snapshot(npc_before, player_before, quest_before)
    tool_executions = execute_tools(decision)

    npc_after = database.get_npc(npc_id)
    player_after = database.get_player_state()
    quest_after = database.get_primary_quest_for_npc(npc_id)
    state_changes = collect_state_changes(
        npc_before=npc_before,
        npc_after=npc_after,
        player_before=player_before,
        player_after=player_after,
        quest_before=quest_before,
        quest_after=quest_after,
    )
    decision["state_after"] = build_state_snapshot(npc_after, player_after, quest_after)
    decision["context_inputs"] = {
        "retrieved_lore": retrieved_lore,
        "retrieved_memories": retrieved_memories,
        "state_snapshot": decision["state_after"],
        "recent_context": recent_context,
    }

    tool_calls = sqlite_tools.serialize_tool_executions(tool_executions)
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
    )
    decision["response_generation"] = response_generation
    if memory_policy_enabled:
        memory_policy, memory_writes = apply_memory_policy(
            MemoryPolicyInput(
                npc_id=npc_id,
                player_input=player_input,
                npc_response=npc_response,
                retrieved_lore=retrieved_lore,
                retrieved_long_term_memories=retrieved_memories,
                recent_short_term_context=recent_context,
                npc_before=npc_before,
                npc_after=npc_after,
                player_before=player_before,
                player_after=player_after,
                quest_before=quest_before,
                quest_after=quest_after,
                tool_calls=tool_calls,
                state_changes=state_changes,
            )
        )
        embedding_updates = ensure_embeddings_for_memory_writes(memory_writes)
        memory_policy["embedding_updates"] = embedding_updates
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
        }
        memory_writes = []
    database.add_recent_interaction(
        npc_id=npc_id,
        player_input=player_input,
        npc_response=npc_response,
        metadata={
            "intent": decision["intent"],
            "log_pending": True,
        },
    )
    workflow_steps = build_workflow_steps(
        recent_context=recent_context,
        retrieved_lore=retrieved_lore,
        retrieved_memories=retrieved_memories,
        decision=decision,
        tool_calls=tool_calls,
        memory_writes=memory_writes,
        state_changes=state_changes,
    )
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
        log_id=log_id,
    )


def execute_tools(decision: dict[str, Any]) -> list[sqlite_tools.ToolExecution]:
    tool_executions = []
    for tool in decision["tools"]:
        name = tool["name"]
        args = tool["args"]
        if name == "add_memory":
            tool_executions.append(sqlite_tools.add_memory(**args))
        elif name == "update_trust":
            tool_executions.append(sqlite_tools.update_trust(**args))
        elif name == "update_affection":
            tool_executions.append(sqlite_tools.update_affection(**args))
        elif name == "give_item":
            tool_executions.append(sqlite_tools.give_item(**args))
        elif name == "update_quest_status":
            tool_executions.append(sqlite_tools.update_quest_status(**args))
        elif name == "unlock_location":
            tool_executions.append(sqlite_tools.unlock_location(**args))
        elif name == "record_world_event":
            tool_executions.append(sqlite_tools.record_world_event(**args))
        else:
            raise ValueError(f"Unknown tool: {name}")
    return tool_executions


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
        {"stage": "Structured Decision", "result": f"Intent: {decision['intent']}."},
        {
            "stage": "Social Strategy",
            "result": (
                f"Intent: {decision.get('social_intent', 'cooperate')}; "
                f"stance: {decision.get('social_stance', {}).get('attitude', 'cautious')}."
            ),
        },
        {"stage": "Tool Execution", "result": f"Executed {len(tool_calls)} tool calls."},
        {
            "stage": "Response Generation",
            "result": (
                f"Style: {decision['response_style']}; "
                f"mode: {decision.get('response_generation', {}).get('mode', 'unknown')}."
            ),
        },
        {"stage": "Memory Policy", "result": f"Wrote {len(memory_writes)} long-term memory record(s)."},
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
