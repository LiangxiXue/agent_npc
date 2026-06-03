from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.event_visibility import dispatch_world_event_to_inbox  # noqa: E402
from src.storage import database  # noqa: E402


DEMO_EVENTS = [
    {
        "event_type": "player_asked_ruins_too_early",
        "content": "Player asked Lina about the ruins entrance before earning trust.",
        "source_type": "player",
        "source_id": "demo",
        "location_id": "tavern",
        "visibility": "npc_only",
        "payload": {"target_npc_ids": ["lina"]},
    },
    {
        "event_type": "badge_evidence_verified",
        "content": "Ron verified the guard badge evidence against the patrol ledger.",
        "source_type": "system",
        "source_id": "demo",
        "location_id": "guard_post",
        "visibility": "npc_only",
        "payload": {"target_npc_ids": ["ron"], "badge_evidence_verified": True},
    },
    {
        "event_type": "player_interested_in_ruins",
        "content": "Player showed interest in ruins access around Sable.",
        "source_type": "player",
        "source_id": "demo",
        "location_id": "market",
        "visibility": "npc_only",
        "payload": {"target_npc_ids": ["sable"]},
    },
]


def seed_events() -> list[dict[str, object]]:
    events = []
    database.add_memory(
        npc_id="lina",
        content="Player previously hid the source of a badge rumor.",
        importance=6,
        memory_type="episodic",
        tags=["trust", "badge"],
    )
    for event_spec in DEMO_EVENTS:
        event = database.create_world_event(**event_spec)
        inbox_items = dispatch_world_event_to_inbox(event)
        events.append({"event": event, "inbox_items": inbox_items})
    return events


def main() -> None:
    database.initialize_database()
    events = seed_events()
    for item in events:
        event = item["event"]
        print(f"Seeded event {event['id']}: {event['event_type']}")
        print(f"  inbox: {[inbox['npc_id'] for inbox in item['inbox_items']]}")


if __name__ == "__main__":
    main()
