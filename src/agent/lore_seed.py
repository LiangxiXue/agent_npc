from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


LORE_DOCUMENTS = [
    {
        "lore_id": "world:grayhaven_overview",
        "scope": "global",
        "npc_id": None,
        "title": "Grayhaven Town Overview",
        "source_path": "data/lore/world_overview.md",
        "importance": 9,
        "tags": ["world", "town", "grayhaven", "tavern", "ruins", "social_rules"],
    },
    {
        "lore_id": "world:underground_ruins",
        "scope": "global",
        "npc_id": None,
        "title": "Underground Ruins and Sensitive Information Rules",
        "source_path": "data/lore/underground_ruins.md",
        "importance": 10,
        "tags": ["world", "ruins", "entrance", "trust_gate", "sensitive_location"],
    },
    {
        "lore_id": "world:social_deduction_rules",
        "scope": "global",
        "npc_id": None,
        "title": "Avalon-Like Social Deduction Rules",
        "source_path": "data/lore/social_deduction_rules.md",
        "importance": 9,
        "tags": ["world", "social_deduction", "deception", "stance", "hidden_alignment"],
    },
    {
        "lore_id": "npc:lina:profile",
        "scope": "npc",
        "npc_id": "lina",
        "title": "Lina Character and Tavern Operations",
        "source_path": "data/lore/npc_lina.md",
        "importance": 10,
        "tags": ["npc", "lina", "tavern", "lost_key", "rumors", "trust"],
    },
    {
        "lore_id": "npc:ron:profile",
        "scope": "npc",
        "npc_id": "ron",
        "title": "Ron Character and Town Guard Protocols",
        "source_path": "data/lore/npc_ron.md",
        "importance": 8,
        "tags": ["npc", "ron", "guard", "gate", "patrol", "badge"],
    },
    {
        "lore_id": "npc:mira:profile",
        "scope": "npc",
        "npc_id": "mira",
        "title": "Mira Character and Ruins Research Notes",
        "source_path": "data/lore/npc_mira.md",
        "importance": 8,
        "tags": ["npc", "mira", "scholar", "ruins", "inscriptions", "field_notes"],
    },
    {
        "lore_id": "npc:sable:profile",
        "scope": "npc",
        "npc_id": "sable",
        "title": "Sable Character and Relic Broker Manipulation",
        "source_path": "data/lore/npc_sable.md",
        "importance": 9,
        "tags": ["npc", "sable", "relic_broker", "deception", "ruins", "exploit_ruins"],
    },
]


def load_lore_documents() -> list[dict[str, Any]]:
    documents = []
    for metadata in LORE_DOCUMENTS:
        source_path = PROJECT_ROOT / metadata["source_path"]
        content = source_path.read_text(encoding="utf-8").strip()
        documents.append({**metadata, "content": content})
    return documents
