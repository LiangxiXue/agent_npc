from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.storage import database


@dataclass(frozen=True)
class ToolExecution:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


def add_memory(
    npc_id: str,
    content: str,
    importance: int,
    tags: list[str] | None = None,
    memory_type: str = "event",
    confidence: float = 1.0,
) -> ToolExecution:
    result = database.add_memory(
        npc_id=npc_id,
        content=content,
        importance=importance,
        tags=tags,
        memory_type=memory_type,
        confidence=confidence,
    )
    return ToolExecution(
        name="add_memory",
        arguments={
            "npc_id": npc_id,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "memory_type": memory_type,
            "confidence": confidence,
        },
        result=result,
    )


def update_trust(npc_id: str, delta: int) -> ToolExecution:
    result = database.update_npc_number(npc_id, "trust", delta)
    return ToolExecution(
        name="update_trust",
        arguments={"npc_id": npc_id, "delta": delta},
        result=result,
    )


def update_affection(npc_id: str, delta: int) -> ToolExecution:
    result = database.update_npc_number(npc_id, "affection", delta)
    return ToolExecution(
        name="update_affection",
        arguments={"npc_id": npc_id, "delta": delta},
        result=result,
    )


def give_item(item: str) -> ToolExecution:
    result = database.give_item(item)
    return ToolExecution(
        name="give_item",
        arguments={"item": item},
        result=result,
    )


def update_quest_status(quest_id: str, status: str) -> ToolExecution:
    result = database.update_quest_status(quest_id, status)
    return ToolExecution(
        name="update_quest_status",
        arguments={"quest_id": quest_id, "status": status},
        result=result,
    )


def unlock_location(location: str) -> ToolExecution:
    result = database.unlock_location(location)
    return ToolExecution(
        name="unlock_location",
        arguments={"location": location},
        result=result,
    )


def record_world_event(content: str) -> ToolExecution:
    result = database.record_world_event(content)
    return ToolExecution(
        name="record_world_event",
        arguments={"content": content},
        result=result,
    )


def serialize_tool_executions(tool_executions: list[ToolExecution]) -> list[dict[str, Any]]:
    return [asdict(execution) for execution in tool_executions]
