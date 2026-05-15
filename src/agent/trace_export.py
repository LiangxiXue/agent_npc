from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.embedding_client import get_embedding_settings
from src.storage import database


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_EXPORT_PATH = PROJECT_ROOT / "data" / "agent_trace_export.json"


def build_trace_export_payload(limit: int = 10) -> dict[str, Any]:
    """Build the same trace payload used by the Streamlit download button."""
    database.initialize_database()
    npcs = database.list_npcs()
    return {
        "npcs": npcs,
        "quests": [database.get_primary_quest_for_npc(npc["npc_id"]) for npc in npcs],
        "player": database.get_player_state(),
        "memories_by_npc": {
            npc["npc_id"]: database.get_recent_memories(npc["npc_id"], limit=100)
            for npc in npcs
        },
        "lore_documents": database.get_lore_documents(limit=100),
        "recent_interactions_by_npc": {
            npc["npc_id"]: database.get_recent_interactions(npc["npc_id"], limit=100)
            for npc in npcs
        },
        "world_events": database.get_world_events(limit=100),
        "interaction_logs": database.get_interaction_logs(limit=limit),
        "embedding_settings": get_embedding_settings(),
    }


def write_trace_export(
    output_path: str | Path = DEFAULT_TRACE_EXPORT_PATH,
    limit: int = 10,
) -> Path:
    payload = build_trace_export_payload(limit=limit)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
