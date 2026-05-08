from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent_state.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("AGENT_NPC_DB_PATH", DEFAULT_DB_PATH))


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with dict-like rows."""
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path | None = None) -> None:
    """Create tables and seed the Lina MVP if needed."""
    with connect(db_path) as connection:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
        ensure_schema_migrations(connection)
        seed_initial_data(connection)


def ensure_schema_migrations(connection: sqlite3.Connection) -> None:
    """Apply lightweight migrations for existing local demo databases."""
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(interaction_logs)").fetchall()
    }
    if "workflow_steps" not in columns:
        connection.execute(
            "ALTER TABLE interaction_logs ADD COLUMN workflow_steps TEXT NOT NULL DEFAULT '[]'"
        )


def reset_database(db_path: str | Path | None = None) -> None:
    """Clear all demo tables and recreate the MVP seed data."""
    with connect(db_path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS interaction_logs;
            DROP TABLE IF EXISTS world_events;
            DROP TABLE IF EXISTS memories;
            DROP TABLE IF EXISTS quests;
            DROP TABLE IF EXISTS unlocked_locations;
            DROP TABLE IF EXISTS player_items;
            DROP TABLE IF EXISTS player_state;
            DROP TABLE IF EXISTS npcs;
            """
        )
    initialize_database(db_path)


def seed_initial_data(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO npcs
            (npc_id, name, role, description, mood, trust, affection)
        VALUES
            (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "lina",
            "Lina",
            "Tavern Owner",
            "A cautious and practical tavern owner who knows local rumors.",
            "neutral",
            20,
            30,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO player_state (id, location) VALUES (1, ?)",
        ("tavern",),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO unlocked_locations (location) VALUES (?)",
        [("tavern",), ("town_square",)],
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO quests
            (quest_id, npc_id, title, description, status)
        VALUES
            (?, ?, ?, ?, ?)
        """,
        (
            "lost_key",
            "lina",
            "Lost Key",
            "Return Lina's missing key to earn her trust.",
            "not_started",
        ),
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_npc(npc_id: str = "lina") -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM npcs WHERE npc_id = ?", (npc_id,)).fetchone()
    npc = row_to_dict(row)
    if npc is None:
        raise KeyError(f"NPC not found: {npc_id}")
    return npc


def get_player_state() -> dict[str, Any]:
    with connect() as connection:
        player = row_to_dict(connection.execute("SELECT * FROM player_state WHERE id = 1").fetchone())
        items = [row["item"] for row in connection.execute("SELECT item FROM player_items ORDER BY item")]
        locations = [
            row["location"]
            for row in connection.execute("SELECT location FROM unlocked_locations ORDER BY location")
        ]
    return {
        "location": player["location"] if player else "unknown",
        "inventory": items,
        "unlocked_locations": locations,
    }


def get_quest(quest_id: str = "lost_key") -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM quests WHERE quest_id = ?", (quest_id,)).fetchone()
    quest = row_to_dict(row)
    if quest is None:
        raise KeyError(f"Quest not found: {quest_id}")
    return quest


def get_recent_memories(npc_id: str = "lina", limit: int = 5) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM memories
            WHERE npc_id = ?
            ORDER BY importance DESC, id DESC
            LIMIT ?
            """,
            (npc_id, limit),
        ).fetchall()
    memories = [dict(row) for row in rows]
    for memory in memories:
        memory["tags"] = json.loads(memory["tags"])
    return memories


def search_memories(player_input: str, npc_id: str = "lina", limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve memories with lightweight keyword scoring, then fall back to important memories."""
    keywords = extract_memory_keywords(player_input)
    memories = get_recent_memories(npc_id=npc_id, limit=20)
    scored_memories = []
    for memory in memories:
        searchable = f"{memory['content']} {' '.join(memory['tags'])}".lower()
        score = sum(1 for keyword in keywords if keyword and keyword in searchable)
        if score > 0:
            scored_memories.append((score, memory["importance"], memory["id"], memory))
    scored_memories.sort(reverse=True)
    matched = [memory for _, _, _, memory in scored_memories]
    return (matched or memories)[:limit]


def extract_memory_keywords(player_input: str) -> list[str]:
    """Extract a small bilingual keyword set without adding NLP dependencies."""
    text = player_input.lower()
    aliases = {
        "lost_key": ["钥匙", "找回", "归还", "key", "returned", "lost key"],
        "ruins": ["遗迹", "地下", "入口", "ruins", "underground", "entrance"],
        "trust": ["信任", "相信", "帮", "帮助", "trust", "help"],
        "discount": ["便宜", "折扣", "优惠", "discount", "coupon"],
        "conversation": ["聊天", "对话", "说", "conversation"],
    }
    keywords = [word.strip("，。！？,.!? ") for word in text.split() if word.strip("，。！？,.!? ")]
    for canonical, words in aliases.items():
        if any(word in text for word in words):
            keywords.append(canonical)
            keywords.extend(words)
    return sorted(set(keyword for keyword in keywords if keyword))


def add_memory(npc_id: str, content: str, importance: int, tags: list[str] | None = None) -> dict[str, Any]:
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO memories (npc_id, content, importance, tags)
            VALUES (?, ?, ?, ?)
            """,
            (npc_id, content, importance, tags_json),
        )
        memory_id = cursor.lastrowid
    return {
        "id": memory_id,
        "npc_id": npc_id,
        "content": content,
        "importance": importance,
        "tags": tags or [],
    }


def update_npc_number(npc_id: str, field: str, delta: int) -> dict[str, Any]:
    if field not in {"trust", "affection"}:
        raise ValueError(f"Unsupported numeric NPC field: {field}")
    with connect() as connection:
        before = connection.execute(f"SELECT {field} FROM npcs WHERE npc_id = ?", (npc_id,)).fetchone()[field]
        after = before + delta
        connection.execute(f"UPDATE npcs SET {field} = ? WHERE npc_id = ?", (after, npc_id))
    return {"npc_id": npc_id, "field": field, "before": before, "after": after}


def give_item(item: str) -> dict[str, Any]:
    before = get_player_state()["inventory"]
    with connect() as connection:
        connection.execute("INSERT OR IGNORE INTO player_items (item) VALUES (?)", (item,))
    after = get_player_state()["inventory"]
    return {"field": "player_inventory", "before": before, "after": after}


def update_quest_status(quest_id: str, status: str) -> dict[str, Any]:
    with connect() as connection:
        before = connection.execute(
            "SELECT status FROM quests WHERE quest_id = ?",
            (quest_id,),
        ).fetchone()["status"]
        connection.execute("UPDATE quests SET status = ? WHERE quest_id = ?", (status, quest_id))
    return {"quest_id": quest_id, "field": "status", "before": before, "after": status}


def unlock_location(location: str) -> dict[str, Any]:
    before = get_player_state()["unlocked_locations"]
    with connect() as connection:
        connection.execute("INSERT OR IGNORE INTO unlocked_locations (location) VALUES (?)", (location,))
    after = get_player_state()["unlocked_locations"]
    return {"field": "unlocked_locations", "before": before, "after": after}


def record_world_event(content: str) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute("INSERT INTO world_events (content) VALUES (?)", (content,))
        event_id = cursor.lastrowid
    return {"id": event_id, "content": content}


def get_world_events(limit: int = 10) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM world_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def log_interaction(
    npc_id: str,
    player_input: str,
    npc_response: str,
    retrieved_memories: list[dict[str, Any]],
    decision: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
    workflow_steps: list[dict[str, Any]],
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO interaction_logs
                (
                    npc_id,
                    player_input,
                    npc_response,
                    retrieved_memories,
                    decision,
                    tool_calls,
                    state_changes,
                    workflow_steps
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                npc_id,
                player_input,
                npc_response,
                json.dumps(retrieved_memories, ensure_ascii=False),
                json.dumps(decision, ensure_ascii=False),
                json.dumps(tool_calls, ensure_ascii=False),
                json.dumps(state_changes, ensure_ascii=False),
                json.dumps(workflow_steps, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def get_interaction_logs(limit: int = 10) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM interaction_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    logs = [dict(row) for row in rows]
    for log in logs:
        log["retrieved_memories"] = json.loads(log["retrieved_memories"])
        log["decision"] = json.loads(log["decision"])
        log["tool_calls"] = json.loads(log["tool_calls"])
        log["state_changes"] = json.loads(log["state_changes"])
        log["workflow_steps"] = json.loads(log["workflow_steps"])
    return logs
