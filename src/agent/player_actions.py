from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agent.event_visibility import dispatch_world_event_to_inbox
from src.storage import database


SUPPORTED_PLAYER_ACTIONS = {"investigate_scene", "submit_evidence", "share_rumor", "wait"}


@dataclass(frozen=True)
class PlayerActionResult:
    status: str
    action_type: str
    target_id: str
    state_changes: list[dict[str, Any]]
    message: str


def run_player_action(
    action_type: str,
    target_id: str = "",
    content: str = "",
    arc_id: str = "ruins_chapter_1",
) -> dict[str, Any]:
    if action_type not in SUPPORTED_PLAYER_ACTIONS:
        raise ValueError(f"Unsupported player action: {action_type}")
    if action_type == "wait":
        return run_wait_action(content=content, arc_id=arc_id)
    scene_object = database.get_scene_object(target_id)
    if action_type == "investigate_scene":
        return run_scene_action(
            action_type=action_type,
            scene_object=scene_object,
            content=content,
            event_type="player_investigated_scene",
            arc_signal=arc_signal_for_object(target_id),
            arc_id=arc_id,
        )
    if action_type == "submit_evidence":
        return run_scene_action(
            action_type=action_type,
            scene_object=scene_object,
            content=content,
            event_type="player_submitted_evidence",
            arc_signal=arc_signal_for_object(target_id),
            arc_id=arc_id,
        )
    return run_scene_action(
        action_type=action_type,
        scene_object=scene_object,
        content=content,
        event_type="player_shared_rumor",
        arc_signal="sable" if target_id == "sable_rumor_stall" else "chaos",
        arc_id=arc_id,
    )


def run_scene_action(
    action_type: str,
    scene_object: dict[str, Any],
    content: str,
    event_type: str,
    arc_signal: str,
    arc_id: str,
) -> dict[str, Any]:
    before = dict(scene_object["state"])
    state = dict(before)
    state["observed"] = True
    state["last_player_action"] = action_type
    evidence = list(state.get("evidence", []))
    if content.strip():
        evidence.append(content.strip())
    state["evidence"] = evidence[-5:]
    after_object = database.update_scene_object_state(scene_object["object_id"], state)
    event = database.create_world_event(
        event_type=event_type,
        content=content.strip() or default_event_content(action_type, scene_object),
        source_type="player_action",
        source_id="player",
        location_id=scene_object["location_id"],
        visibility="location",
        payload={
            "arc_id": arc_id,
            "arc_signal": arc_signal,
            "target_id": scene_object["object_id"],
            "action_type": action_type,
        },
    )
    inbox_items = dispatch_world_event_to_inbox(event)
    return {
        "action_result": PlayerActionResult(
            status="accepted",
            action_type=action_type,
            target_id=scene_object["object_id"],
            state_changes=[
                {
                    "scope": "scene_object",
                    "object_id": scene_object["object_id"],
                    "before": before,
                    "after": after_object["state"],
                }
            ],
            message="Player action created a world event.",
        ),
        "created_events": [event],
        "inbox_items": inbox_items,
        "arc_state": database.get_world_arc_state(arc_id),
    }


def run_wait_action(content: str, arc_id: str) -> dict[str, Any]:
    created_events = []
    inbox_items = []
    for routine in database.list_npc_routines(enabled_only=True):
        event = database.create_world_event(
            event_type=routine["event_type"],
            content=routine["event_content"],
            source_type="npc_routine",
            source_id=routine["npc_id"],
            location_id=routine["location_id"],
            visibility="location",
            payload={
                "arc_id": arc_id,
                "arc_signal": arc_signal_for_npc(routine["npc_id"]),
                "routine_type": routine["routine_type"],
                "player_wait_content": content.strip(),
            },
        )
        created_events.append(event)
        inbox_items.extend(dispatch_world_event_to_inbox(event))
    return {
        "action_result": PlayerActionResult(
            status="accepted",
            action_type="wait",
            target_id="",
            state_changes=[],
            message="Routine events advanced while the player waited.",
        ),
        "created_events": created_events,
        "inbox_items": inbox_items,
        "arc_state": database.get_world_arc_state(arc_id),
    }


def default_event_content(action_type: str, scene_object: dict[str, Any]) -> str:
    return f"Player used {action_type} at {scene_object['name']}."


def arc_signal_for_object(object_id: str) -> str:
    if object_id in {"tavern_back_alley", "guard_ledger"}:
        return "guardian"
    if object_id == "mira_field_notes":
        return "research"
    if object_id == "sable_rumor_stall":
        return "sable"
    return "chaos"


def arc_signal_for_npc(npc_id: str) -> str:
    return {
        "lina": "guardian",
        "ron": "guardian",
        "mira": "research",
        "sable": "sable",
    }.get(npc_id, "chaos")
