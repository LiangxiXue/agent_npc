from __future__ import annotations

from typing import Any

from src.storage import database


NPC_HOME_LOCATIONS = {
    "lina": "tavern",
    "ron": "guard_post",
    "mira": "archive",
    "sable": "market",
}


def dispatch_world_event_to_inbox(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Create NPC inbox rows for a structured world event."""
    recipients = resolve_world_event_recipients(event)
    items = []
    for recipient in recipients:
        items.append(
            database.add_npc_event_inbox_item(
                npc_id=recipient["npc_id"],
                event_id=int(event["id"]),
                relevance_score=float(recipient["relevance_score"]),
                reason=str(recipient["reason"]),
            )
        )
    return items


def resolve_world_event_recipients(event: dict[str, Any]) -> list[dict[str, Any]]:
    visibility = str(event.get("visibility") or "public")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    npc_ids = [npc["npc_id"] for npc in database.list_npcs()]
    recipients: dict[str, dict[str, Any]] = {}

    def add(npc_id: str, reason: str, relevance_score: float) -> None:
        if npc_id not in npc_ids:
            return
        current = recipients.get(npc_id)
        if current is None or relevance_score > current["relevance_score"]:
            recipients[npc_id] = {
                "npc_id": npc_id,
                "reason": reason,
                "relevance_score": relevance_score,
            }

    if visibility == "public":
        for npc_id in npc_ids:
            add(npc_id, "public", 0.4)
    elif visibility == "location":
        location_id = event.get("location_id")
        for npc_id in npc_ids:
            if get_npc_location(npc_id) == location_id:
                add(npc_id, "same_location", 0.75)
    elif visibility in {"private", "npc_only"}:
        for npc_id in as_string_list(payload.get("target_npc_ids")):
            add(npc_id, "explicit_target", 1.0)
        if visibility == "private":
            for npc_id in as_string_list(payload.get("witnessed_by")):
                add(npc_id, "witnessed_by", 0.85)
    else:
        return []

    return sorted(recipients.values(), key=lambda item: (-item["relevance_score"], item["npc_id"]))


def get_visible_world_events(npc_id: str, limit: int = 10) -> list[dict[str, Any]]:
    inbox_items = database.get_npc_event_inbox(npc_id, include_seen=True, limit=limit)
    visible_events = []
    for item in inbox_items:
        event = dict(item["event"])
        event["inbox_id"] = item["id"]
        event["visibility_reason"] = item["reason"]
        event["relevance_score"] = item["relevance_score"]
        event["seen"] = item["seen"]
        visible_events.append(event)
    return visible_events[:limit]


def get_npc_location(npc_id: str) -> str:
    return NPC_HOME_LOCATIONS.get(npc_id, "unknown")


def as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
