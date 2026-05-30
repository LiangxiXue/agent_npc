from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from src.agent.context import build_context_inputs
from src.agent.decision import apply_task_state_machine, validate_decision
from src.storage import database
from src.tools import sqlite_tools


@dataclass(frozen=True)
class Observation:
    npc_id: str
    player_input: str
    npc_state: dict[str, Any]
    player_state: dict[str, Any]
    quest_state: dict[str, Any]
    recent_context: list[dict[str, Any]]
    retrieved_lore: list[dict[str, Any]]
    retrieved_memories: list[dict[str, Any]]
    visible_world_events: list[dict[str, Any]]
    memory_retrieval_mode: str


@dataclass(frozen=True)
class NPCAction:
    action_type: str
    intent: str
    target: str
    subject: str
    reason: str
    response_style: str
    response_keywords: list[str]
    social_intent: str
    social_stance: dict[str, Any]
    proposed_effects: list[dict[str, Any]]
    raw_decision: dict[str, Any]


@dataclass(frozen=True)
class ActionResult:
    accepted: bool
    blocked_reason: str
    executed_tools: list[dict[str, Any]]
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    state_changes: list[dict[str, Any]]
    events: list[dict[str, Any]]
    response_constraints: list[str]


class NarrativeEnvironment:
    def observe(
        self,
        player_input: str,
        npc_id: str,
        memory_retrieval_mode: str,
    ) -> Observation:
        context_inputs = build_context_inputs(
            player_input=player_input,
            npc_id=npc_id,
            memory_retrieval_mode=memory_retrieval_mode,
        )
        return Observation(
            npc_id=npc_id,
            player_input=player_input,
            npc_state=database.get_npc(npc_id),
            player_state=database.get_player_state(),
            quest_state=database.get_primary_quest_for_npc(npc_id),
            recent_context=context_inputs["recent_context"],
            retrieved_lore=context_inputs["retrieved_lore"],
            retrieved_memories=context_inputs["retrieved_memories"],
            visible_world_events=database.get_world_events(limit=10),
            memory_retrieval_mode=memory_retrieval_mode,
        )

    def propose_action_from_decision(
        self,
        decision: dict[str, Any],
        observation: Observation,
    ) -> NPCAction:
        normalized_decision = deepcopy(decision)
        tools = normalized_decision.get("tools", [])
        proposed_effects = [
            {
                "effect_type": tool.get("name", "unknown"),
                "args": deepcopy(tool.get("args", {})),
            }
            for tool in tools
        ]
        return NPCAction(
            action_type="dialogue",
            intent=str(normalized_decision["intent"]),
            target="player",
            subject=self._infer_subject(normalized_decision),
            reason=str(normalized_decision.get("reasoning", "")),
            response_style=str(normalized_decision["response_style"]),
            response_keywords=list(normalized_decision["response_keywords"]),
            social_intent=str(normalized_decision.get("social_intent", "cooperate")),
            social_stance=deepcopy(normalized_decision.get("social_stance", {})),
            proposed_effects=proposed_effects,
            raw_decision=normalized_decision,
        )

    def _infer_subject(self, decision: dict[str, Any]) -> str:
        intent = str(decision.get("intent", "general_conversation"))
        if "ruins" in intent:
            return "underground_ruins_entrance"
        if "lost_key" in intent:
            return "lost_key"
        if "gate_badge" in intent:
            return "gate_badge"
        if "ancient_notes" in intent:
            return "ancient_notes"
        if "relic_tip" in intent:
            return "relic_tip"
        return "conversation"

    def trace_payload(
        self,
        observation: Observation,
        action: NPCAction,
        result: ActionResult,
    ) -> dict[str, Any]:
        effective_action = self.validate(action, observation)
        return {
            "observation_summary": {
                "npc_id": observation.npc_id,
                "player_input": observation.player_input,
                "quest": observation.quest_state,
                "retrieved_lore_count": len(observation.retrieved_lore),
                "retrieved_memories_count": len(observation.retrieved_memories),
                "memory_retrieval_mode": observation.memory_retrieval_mode,
            },
            "npc_action": asdict(effective_action),
            "action_result": asdict(result),
        }

    def validate(self, action: NPCAction, observation: Observation) -> NPCAction:
        try:
            validated_decision = apply_task_state_machine(
                validate_decision(deepcopy(action.raw_decision)),
                player_input=observation.player_input,
                npc_state=observation.npc_state,
                quest_state=observation.quest_state,
            )
        except ValueError as exc:
            validated_decision = self._rejected_decision(action.raw_decision, str(exc))
        return self.propose_action_from_decision(validated_decision, observation)

    def execute(self, action: NPCAction, observation: Observation) -> ActionResult:
        action = self.validate(action, observation)
        state_before = build_environment_state_snapshot(
            observation.npc_state,
            observation.player_state,
            observation.quest_state,
        )
        blocked_reason = self._blocked_reason(action)
        if blocked_reason:
            state_after = build_environment_state_snapshot(
                database.get_npc(observation.npc_id),
                database.get_player_state(),
                database.get_primary_quest_for_npc(observation.npc_id),
            )
            return ActionResult(
                accepted=False,
                blocked_reason=blocked_reason,
                executed_tools=[],
                state_before=state_before,
                state_after=state_after,
                state_changes=[],
                events=[],
                response_constraints=self._response_constraints([], accepted=False),
            )

        tool_executions = self._execute_tools(action.raw_decision.get("tools", []))
        npc_after = database.get_npc(observation.npc_id)
        player_after = database.get_player_state()
        quest_after = database.get_primary_quest_for_npc(observation.npc_id)
        state_after = build_environment_state_snapshot(npc_after, player_after, quest_after)
        state_changes = collect_environment_state_changes(
            npc_before=observation.npc_state,
            npc_after=npc_after,
            player_before=observation.player_state,
            player_after=player_after,
            quest_before=observation.quest_state,
            quest_after=quest_after,
        )
        executed_tools = sqlite_tools.serialize_tool_executions(tool_executions)
        return ActionResult(
            accepted=True,
            blocked_reason="",
            executed_tools=executed_tools,
            state_before=state_before,
            state_after=state_after,
            state_changes=state_changes,
            events=[tool for tool in executed_tools if tool["name"] == "record_world_event"],
            response_constraints=self._response_constraints(executed_tools, accepted=True),
        )

    def _execute_tools(self, tools: list[dict[str, Any]]) -> list[sqlite_tools.ToolExecution]:
        tool_executions = []
        for tool in tools:
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

    def _blocked_reason(self, action: NPCAction) -> str:
        state_machine = action.raw_decision.get("state_machine", {})
        if state_machine.get("blocked"):
            return str(state_machine.get("reason", "Action blocked by task state machine."))
        return ""

    def _rejected_decision(
        self,
        original: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        return {
            "intent": "probe_for_evidence",
            "reasoning": f"Environment validation rejected the proposed action: {reason}",
            "memory_policy": "Do not write task progress memory because the environment rejected the action.",
            "response_style": "cautious_state_guard",
            "response_keywords": ["动作被环境拒绝", "需要更多证据", "不能改变状态"],
            "tools": [],
            "social_intent": "probe",
            "social_stance": {
                "target": "player",
                "attitude": "cautious",
                "intensity": 0.65,
                "reason": "The proposed action failed environment validation.",
            },
            "state_machine": {
                "blocked": True,
                "original_intent": original.get("intent"),
                "reason": reason,
            },
        }

    def _response_constraints(
        self,
        executed_tools: list[dict[str, Any]],
        accepted: bool,
    ) -> list[str]:
        tool_names = {tool["name"] for tool in executed_tools}
        constraints = []
        if not accepted:
            constraints.append(
                "Do not claim quest completion, location unlocks, item rewards, trust changes, or affection changes."
            )
        if "unlock_location" not in tool_names:
            constraints.append("Do not claim the underground ruins entrance is unlocked or available.")
        if "give_item" not in tool_names:
            constraints.append("Do not claim the player received an item reward.")
        return constraints


def build_environment_state_snapshot(
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
            "inventory": list(player_state["inventory"]),
            "unlocked_locations": list(player_state["unlocked_locations"]),
        },
        "quest": {
            "quest_id": quest_state["quest_id"],
            "title": quest_state["title"],
            "status": quest_state["status"],
        },
    }


def collect_environment_state_changes(
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
