from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
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
    npc_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(npcs)").fetchall()
    }
    if "hidden_alignment" not in npc_columns:
        connection.execute(
            "ALTER TABLE npcs ADD COLUMN hidden_alignment TEXT NOT NULL DEFAULT 'neutral'"
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id INTEGER PRIMARY KEY,
            embedding TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_provider TEXT NOT NULL DEFAULT 'mock_hash',
            embedding_dim INTEGER NOT NULL,
            source_text_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories (id) ON DELETE CASCADE
        )
        """
    )

    embedding_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(memory_embeddings)").fetchall()
    }
    embedding_migrations = {
        "embedding_provider": "ALTER TABLE memory_embeddings ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'mock_hash'",
        "source_text_hash": "ALTER TABLE memory_embeddings ADD COLUMN source_text_hash TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in embedding_migrations.items():
        if column not in embedding_columns:
            connection.execute(statement)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id TEXT NOT NULL,
            player_input TEXT NOT NULL,
            npc_response TEXT NOT NULL,
            recent_context TEXT NOT NULL DEFAULT '[]',
            retrieved_lore TEXT NOT NULL DEFAULT '[]',
            retrieved_memories TEXT NOT NULL DEFAULT '[]',
            state_before TEXT NOT NULL DEFAULT '{}',
            state_after TEXT NOT NULL DEFAULT '{}',
            tool_calls TEXT NOT NULL DEFAULT '[]',
            state_changes TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            memory_policy TEXT NOT NULL DEFAULT '{}',
            memory_writes TEXT NOT NULL DEFAULT '[]',
            embedding_updates TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT,
            FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
        )
        """
    )
    memory_job_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(memory_jobs)").fetchall()
    }
    memory_job_migrations = {
        "recent_context": "ALTER TABLE memory_jobs ADD COLUMN recent_context TEXT NOT NULL DEFAULT '[]'",
        "state_before": "ALTER TABLE memory_jobs ADD COLUMN state_before TEXT NOT NULL DEFAULT '{}'",
        "state_after": "ALTER TABLE memory_jobs ADD COLUMN state_after TEXT NOT NULL DEFAULT '{}'",
        "memory_policy": "ALTER TABLE memory_jobs ADD COLUMN memory_policy TEXT NOT NULL DEFAULT '{}'",
        "memory_writes": "ALTER TABLE memory_jobs ADD COLUMN memory_writes TEXT NOT NULL DEFAULT '[]'",
        "embedding_updates": "ALTER TABLE memory_jobs ADD COLUMN embedding_updates TEXT NOT NULL DEFAULT '[]'",
        "processed_at": "ALTER TABLE memory_jobs ADD COLUMN processed_at TEXT",
    }
    for column, statement in memory_job_migrations.items():
        if column not in memory_job_columns:
            connection.execute(statement)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS lore_documents (
            lore_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            npc_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            importance INTEGER NOT NULL DEFAULT 5,
            tags TEXT NOT NULL DEFAULT '[]',
            source_path TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS lore_embeddings (
            lore_id TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_provider TEXT NOT NULL DEFAULT 'mock_hash',
            embedding_dim INTEGER NOT NULL,
            source_text_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lore_id) REFERENCES lore_documents (lore_id) ON DELETE CASCADE
        )
        """
    )
    lore_embedding_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(lore_embeddings)").fetchall()
    }
    lore_embedding_migrations = {
        "embedding_provider": "ALTER TABLE lore_embeddings ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'mock_hash'",
        "source_text_hash": "ALTER TABLE lore_embeddings ADD COLUMN source_text_hash TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in lore_embedding_migrations.items():
        if column not in lore_embedding_columns:
            connection.execute(statement)

    memory_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(memories)").fetchall()
    }
    memory_migrations = {
        "memory_type": "ALTER TABLE memories ADD COLUMN memory_type TEXT NOT NULL DEFAULT 'episodic'",
        "confidence": "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0",
        "last_accessed_at": "ALTER TABLE memories ADD COLUMN last_accessed_at TEXT",
        "access_count": "ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0",
        "facets": "ALTER TABLE memories ADD COLUMN facets TEXT NOT NULL DEFAULT '[]'",
        "scope": "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'npc_specific'",
        "evidence_text": "ALTER TABLE memories ADD COLUMN evidence_text TEXT NOT NULL DEFAULT ''",
        "stability": "ALTER TABLE memories ADD COLUMN stability REAL NOT NULL DEFAULT 0.5",
        "future_usefulness": "ALTER TABLE memories ADD COLUMN future_usefulness REAL NOT NULL DEFAULT 0.5",
    }
    for column, statement in memory_migrations.items():
        if column not in memory_columns:
            connection.execute(statement)
    connection.execute(
        """
        UPDATE memories
        SET memory_type = CASE memory_type
            WHEN 'quest' THEN 'episodic'
            WHEN 'event' THEN 'episodic'
            WHEN 'relationship' THEN 'relational'
            WHEN 'preference' THEN 'procedural'
            WHEN 'player_profile' THEN 'semantic'
            ELSE memory_type
        END
        WHERE memory_type IN ('quest', 'event', 'relationship', 'preference', 'player_profile')
        """
    )
    connection.execute(
        """
        UPDATE memories
        SET facets = tags
        WHERE (facets = '[]' OR facets = '') AND tags IS NOT NULL AND tags != '[]'
        """
    )

    log_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(interaction_logs)").fetchall()
    }
    log_migrations = {
        "recent_context": "ALTER TABLE interaction_logs ADD COLUMN recent_context TEXT NOT NULL DEFAULT '[]'",
        "retrieved_lore": "ALTER TABLE interaction_logs ADD COLUMN retrieved_lore TEXT NOT NULL DEFAULT '[]'",
        "state_snapshot": "ALTER TABLE interaction_logs ADD COLUMN state_snapshot TEXT NOT NULL DEFAULT '{}'",
        "memory_policy": "ALTER TABLE interaction_logs ADD COLUMN memory_policy TEXT NOT NULL DEFAULT '{}'",
        "memory_writes": "ALTER TABLE interaction_logs ADD COLUMN memory_writes TEXT NOT NULL DEFAULT '[]'",
        "workflow_steps": "ALTER TABLE interaction_logs ADD COLUMN workflow_steps TEXT NOT NULL DEFAULT '[]'",
    }
    for column, statement in log_migrations.items():
        if column not in log_columns:
            connection.execute(statement)


def reset_database(db_path: str | Path | None = None) -> None:
    """Clear all demo tables and recreate the MVP seed data."""
    with connect(db_path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS interaction_logs;
            DROP TABLE IF EXISTS world_events;
            DROP TABLE IF EXISTS recent_interactions;
            DROP TABLE IF EXISTS lore_embeddings;
            DROP TABLE IF EXISTS lore_documents;
            DROP TABLE IF EXISTS memory_jobs;
            DROP TABLE IF EXISTS memory_embeddings;
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
    connection.executemany(
        """
        INSERT OR IGNORE INTO npcs
            (npc_id, name, role, description, hidden_alignment, mood, trust, affection)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "lina",
                "Lina",
                "Tavern Owner",
                "A cautious and practical tavern owner who knows local rumors.",
                "protect_ruins",
                "neutral",
                20,
                30,
            ),
            (
                "ron",
                "Ron",
                "Town Guard",
                "A disciplined town guard who tracks patrol reports and gate incidents.",
                "enforce_order",
                "alert",
                18,
                20,
            ),
            (
                "mira",
                "Mira",
                "Ruins Scholar",
                "A careful scholar who studies old ruins, inscriptions, and local myths.",
                "research_truth",
                "curious",
                22,
                24,
            ),
            (
                "sable",
                "Sable",
                "Traveling Relic Broker",
                "A polished relic broker who offers useful rumors while steering people toward exploitable ruin secrets.",
                "exploit_ruins",
                "pleasant",
                16,
                18,
            ),
        ],
    )
    connection.executemany(
        "UPDATE npcs SET hidden_alignment = ? WHERE npc_id = ?",
        [
            ("protect_ruins", "lina"),
            ("enforce_order", "ron"),
            ("research_truth", "mira"),
            ("exploit_ruins", "sable"),
        ],
    )
    seed_lore_documents(connection)


def seed_lore_documents(connection: sqlite3.Connection) -> None:
    from src.agent.lore_seed import load_lore_documents

    for document in load_lore_documents():
        connection.execute(
            """
            INSERT INTO lore_documents
                (lore_id, scope, npc_id, title, content, importance, tags, source_path, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lore_id) DO UPDATE SET
                scope = excluded.scope,
                npc_id = excluded.npc_id,
                title = excluded.title,
                content = excluded.content,
                importance = excluded.importance,
                tags = excluded.tags,
                source_path = excluded.source_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                document["lore_id"],
                document["scope"],
                document.get("npc_id"),
                document["title"],
                document["content"],
                document["importance"],
                json.dumps(document["tags"], ensure_ascii=False),
                document["source_path"],
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
    connection.executemany(
        """
        INSERT OR IGNORE INTO quests
            (quest_id, npc_id, title, description, status)
        VALUES
            (?, ?, ?, ?, ?)
        """,
        [
            (
                "lost_key",
                "lina",
                "Lost Key",
                "Return Lina's missing key to earn her trust.",
                "not_started",
            ),
            (
                "gate_badge",
                "ron",
                "Gate Badge",
                "Help Ron verify a misplaced guard badge before the night patrol.",
                "not_started",
            ),
            (
                "ancient_notes",
                "mira",
                "Ancient Notes",
                "Bring Mira useful field notes about the underground ruins.",
                "not_started",
            ),
            (
                "relic_tip",
                "sable",
                "Relic Tip",
                "Notice how Sable redirects ruin inquiries toward exploitable relic information.",
                "not_started",
            ),
        ],
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


def list_npcs() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM npcs
            ORDER BY CASE npc_id
                WHEN 'lina' THEN 0
                WHEN 'ron' THEN 1
                WHEN 'mira' THEN 2
                WHEN 'sable' THEN 3
                ELSE 4
            END, npc_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


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


def get_primary_quest_for_npc(npc_id: str = "lina") -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM quests
            WHERE npc_id = ?
            ORDER BY quest_id
            LIMIT 1
            """,
            (npc_id,),
        ).fetchone()
    quest = row_to_dict(row)
    if quest is None:
        raise KeyError(f"Primary quest not found for NPC: {npc_id}")
    return quest


def get_lore_documents(npc_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    where_clause = "WHERE npc_id IS NULL OR npc_id = ?" if npc_id else ""
    params: tuple[Any, ...] = (npc_id, limit) if npc_id else (limit,)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM lore_documents
            {where_clause}
            ORDER BY importance DESC, lore_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    documents = [dict(row) for row in rows]
    for document in documents:
        document["tags"] = json.loads(document["tags"])
    return documents


def get_lore_document(lore_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM lore_documents WHERE lore_id = ?",
            (lore_id,),
        ).fetchone()
    document = row_to_dict(row)
    if document:
        document["tags"] = json.loads(document["tags"])
    return document


def upsert_lore_embedding(
    lore_id: str,
    embedding: list[float],
    model: str,
    provider: str = "mock_hash",
    source_text_hash: str = "",
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO lore_embeddings
                (
                    lore_id,
                    embedding,
                    embedding_model,
                    embedding_provider,
                    embedding_dim,
                    source_text_hash,
                    updated_at
                )
            VALUES
                (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lore_id) DO UPDATE SET
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                embedding_provider = excluded.embedding_provider,
                embedding_dim = excluded.embedding_dim,
                source_text_hash = excluded.source_text_hash,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                lore_id,
                json.dumps(embedding),
                model,
                provider,
                len(embedding),
                source_text_hash,
            ),
        )


def get_lore_embeddings(npc_id: str | None = None) -> list[dict[str, Any]]:
    where_clause = "WHERE lore_documents.npc_id IS NULL OR lore_documents.npc_id = ?" if npc_id else ""
    params: tuple[Any, ...] = (npc_id,) if npc_id else ()
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                lore_embeddings.lore_id,
                lore_embeddings.embedding,
                lore_embeddings.embedding_model,
                lore_embeddings.embedding_provider,
                lore_embeddings.embedding_dim,
                lore_embeddings.source_text_hash,
                lore_embeddings.created_at,
                lore_embeddings.updated_at
            FROM lore_embeddings
            JOIN lore_documents ON lore_documents.lore_id = lore_embeddings.lore_id
            {where_clause}
            ORDER BY lore_documents.importance DESC, lore_documents.lore_id
            """,
            params,
        ).fetchall()
    embeddings = [dict(row) for row in rows]
    for embedding in embeddings:
        embedding["embedding"] = [float(value) for value in json.loads(embedding["embedding"])]
    return embeddings


def get_lore_embedding_metadata(npc_id: str | None = None) -> dict[str, dict[str, Any]]:
    where_clause = "WHERE lore_documents.npc_id IS NULL OR lore_documents.npc_id = ?" if npc_id else ""
    params: tuple[Any, ...] = (npc_id,) if npc_id else ()
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                lore_embeddings.lore_id,
                lore_embeddings.embedding_model,
                lore_embeddings.embedding_provider,
                lore_embeddings.embedding_dim,
                lore_embeddings.source_text_hash,
                lore_embeddings.created_at,
                lore_embeddings.updated_at
            FROM lore_embeddings
            JOIN lore_documents ON lore_documents.lore_id = lore_embeddings.lore_id
            {where_clause}
            """,
            params,
        ).fetchall()
    return {str(row["lore_id"]): dict(row) for row in rows}


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
        memory["tags"] = json.loads(memory.get("tags") or "[]")
        memory["facets"] = json.loads(memory.get("facets") or "[]")
        if not memory["facets"]:
            memory["facets"] = list(memory["tags"])
    return memories


def search_memories(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 5,
    mode: str = "typed",
) -> list[dict[str, Any]]:
    """Retrieve long-term memories with rule, semantic, or hybrid scoring."""
    if mode == "off":
        return []
    if mode == "semantic":
        matched = search_memories_semantic(player_input, npc_id=npc_id, limit=limit)
        update_memory_access_stats([memory["id"] for memory in matched])
        return matched
    if mode == "hybrid":
        matched = search_memories_hybrid(player_input, npc_id=npc_id, limit=limit)
        update_memory_access_stats([memory["id"] for memory in matched])
        return matched

    keywords = extract_memory_keywords(player_input)
    query_types = infer_memory_query_types(player_input)
    memories = get_recent_memories(npc_id=npc_id, limit=50)
    scored_memories = []
    for memory in memories:
        if mode == "legacy":
            enriched = score_memory_for_query_legacy(memory, keywords)
        else:
            enriched = score_memory_for_query(memory, keywords, query_types)
        type_match = mode == "typed" and memory.get("memory_type") in query_types
        if enriched["matched_keywords"] or enriched["matched_tags"] or type_match:
            scored_memories.append(enriched)

    scored_memories.sort(
        key=lambda memory: (
            memory["retrieval_score"],
            memory["importance"],
            memory["id"],
        ),
        reverse=True,
    )
    matched = scored_memories[:limit]
    if not matched:
        matched = [add_fallback_retrieval_metadata(memory) for memory in memories[:limit]]

    update_memory_access_stats([memory["id"] for memory in matched])
    return matched


def search_memories_semantic(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 5,
) -> list[dict[str, Any]]:
    from src.agent.semantic_retrieval import semantic_search_memories

    memories_by_id = {
        memory["id"]: memory
        for memory in get_recent_memories(npc_id=npc_id, limit=100)
    }
    candidates = semantic_search_memories(player_input, npc_id=npc_id, limit=limit)
    matched = []
    for candidate in candidates:
        memory = memories_by_id.get(candidate["memory_id"])
        if not memory:
            continue
        enriched = add_semantic_metadata(memory, candidate)
        matched.append(enriched)
    return matched


def search_memories_hybrid(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 5,
) -> list[dict[str, Any]]:
    from src.agent.semantic_retrieval import semantic_search_memories

    keywords = extract_memory_keywords(player_input)
    query_types = infer_memory_query_types(player_input)
    memories = get_recent_memories(npc_id=npc_id, limit=100)
    by_id: dict[int, dict[str, Any]] = {}

    for memory in memories:
        rule_scored = score_memory_for_query(memory, keywords, query_types)
        if (
            rule_scored["matched_keywords"]
            or rule_scored["matched_tags"]
            or memory.get("memory_type") in query_types
        ):
            by_id[memory["id"]] = rule_scored

    semantic_candidates = {
        candidate["memory_id"]: candidate
        for candidate in semantic_search_memories(player_input, npc_id=npc_id, limit=20)
    }
    memories_by_id = {memory["id"]: memory for memory in memories}
    for memory_id, candidate in semantic_candidates.items():
        if memory_id not in memories_by_id:
            continue
        base = by_id.get(memory_id) or score_memory_for_query(
            memories_by_id[memory_id],
            keywords,
            query_types,
        )
        by_id[memory_id] = add_semantic_metadata(base, candidate, hybrid=True)

    for memory_id, memory in list(by_id.items()):
        if memory_id not in semantic_candidates:
            memory["rule_score"] = memory["retrieval_score"]
            memory["semantic_score"] = 0.0
            memory["semantic_reason"] = "No semantic candidate above zero similarity."
            memory["score_breakdown"] = build_score_breakdown(memory)

    matched = list(by_id.values())
    matched.sort(
        key=lambda memory: (
            memory["retrieval_score"],
            memory["importance"],
            memory["id"],
        ),
        reverse=True,
    )
    return matched[:limit]


def add_semantic_metadata(
    memory: dict[str, Any],
    candidate: dict[str, Any],
    hybrid: bool = False,
) -> dict[str, Any]:
    enriched = dict(memory)
    rule_score = float(enriched.get("retrieval_score", 0.0)) if hybrid else 0.0
    semantic_score = float(candidate["semantic_score"])
    enriched.update(
        {
            "rule_score": round(rule_score, 3),
            "semantic_score": round(semantic_score, 3),
            "semantic_similarity": candidate["semantic_similarity"],
            "semantic_reason": candidate["semantic_reason"],
            "embedding_model": candidate["embedding_model"],
            "embedding_provider": candidate.get("embedding_provider"),
            "query_embedding_provider": candidate.get("query_embedding_provider"),
            "query_embedding_model": candidate.get("query_embedding_model"),
            "query_embedding_fallback_reason": candidate.get("query_embedding_fallback_reason"),
            "retrieval_backend": candidate.get("retrieval_backend"),
            "requested_retrieval_backend": candidate.get("requested_retrieval_backend"),
            "backend_fallback_reason": candidate.get("backend_fallback_reason"),
            "query_embedding_latency_ms": candidate.get("query_embedding_latency_ms"),
            "backend_latency_ms": candidate.get("backend_latency_ms"),
        }
    )
    if hybrid:
        enriched["retrieval_score"] = round(rule_score + semantic_score, 3)
        existing_reason = enriched.get("retrieval_reason", "")
        enriched["retrieval_reason"] = "; ".join(
            reason
            for reason in [
                existing_reason if existing_reason != "Selected by importance and confidence." else "",
                f"semantic match score {semantic_score}",
            ]
            if reason
        ) or "Selected by hybrid semantic and typed scoring."
    else:
        enriched["retrieval_score"] = round(semantic_score, 3)
        enriched["matched_keywords"] = []
        enriched["matched_tags"] = []
        enriched["retrieval_reason"] = f"Semantic retrieval: {candidate['semantic_reason']}"
    enriched["score_breakdown"] = build_score_breakdown(enriched)
    return enriched


def build_score_breakdown(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_score": round(float(memory.get("rule_score", 0.0)), 3),
        "semantic_score": round(float(memory.get("semantic_score", 0.0)), 3),
        "final_retrieval_score": round(float(memory.get("retrieval_score", 0.0)), 3),
        "retrieval_backend": memory.get("retrieval_backend") or "rule_only",
    }


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


def infer_memory_query_types(player_input: str) -> set[str]:
    text = player_input.lower()
    query_types: set[str] = set()
    if any(word in text for word in ["任务", "线索", "遗迹", "地点", "入口", "quest", "ruins", "entrance"]):
        query_types.update({"episodic", "relational", "semantic"})
    if any(word in text for word in ["记得", "之前", "上次", "信任", "关系", "remember", "trust"]):
        query_types.update({"relational", "episodic"})
    if any(word in text for word in ["以后", "喜欢", "偏好", "直接", "绕弯", "prefer"]):
        query_types.add("procedural")
    return query_types


def score_memory_for_query(
    memory: dict[str, Any],
    keywords: list[str],
    query_types: set[str],
) -> dict[str, Any]:
    content = memory["content"].lower()
    tags = [str(tag).lower() for tag in memory["tags"]]
    facets = [str(facet).lower() for facet in memory.get("facets", [])]
    tag_set = set(tags + facets)
    matched_keywords = [keyword for keyword in keywords if keyword.lower() in content]
    matched_tags = [keyword for keyword in keywords if keyword.lower() in tag_set]

    keyword_score = len(matched_keywords) * 2.0
    tag_score = len(matched_tags) * 2.5
    type_bonus = 1.5 if memory.get("memory_type") in query_types else 0.0
    importance_bonus = float(memory["importance"]) * 0.3
    confidence_bonus = float(memory.get("confidence", 1.0)) * 1.0
    recency_bonus = calculate_recency_bonus(memory.get("created_at"))
    retrieval_score = round(
        keyword_score + tag_score + type_bonus + importance_bonus + confidence_bonus + recency_bonus,
        3,
    )

    enriched = dict(memory)
    enriched.update(
        {
            "retrieval_score": retrieval_score,
            "matched_keywords": matched_keywords,
            "matched_tags": matched_tags,
            "retrieval_reason": build_retrieval_reason(
                matched_keywords=matched_keywords,
                matched_tags=matched_tags,
                query_types=query_types,
                memory_type=memory.get("memory_type", "episodic"),
                fallback=False,
            ),
        }
    )
    return enriched


def score_memory_for_query_legacy(
    memory: dict[str, Any],
    keywords: list[str],
) -> dict[str, Any]:
    searchable = f"{memory['content']} {' '.join(memory['tags'])} {' '.join(memory.get('facets', []))}".lower()
    matched_keywords = [keyword for keyword in keywords if keyword.lower() in searchable]
    matched_tags = [
        keyword
        for keyword in keywords
        if keyword.lower() in {str(tag).lower() for tag in memory["tags"] + memory.get("facets", [])}
    ]
    retrieval_score = round(
        len(matched_keywords) * 2.0 + float(memory["importance"]) * 0.3,
        3,
    )
    enriched = dict(memory)
    enriched.update(
        {
            "retrieval_score": retrieval_score,
            "matched_keywords": matched_keywords,
            "matched_tags": matched_tags,
            "retrieval_reason": (
                "Legacy keyword/tag match without memory type, confidence, or query-intent bonus."
                if matched_keywords or matched_tags
                else "Legacy fallback candidate."
            ),
        }
    )
    return enriched


def add_fallback_retrieval_metadata(memory: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(memory)
    enriched.update(
        {
            "retrieval_score": round(float(memory["importance"]) * 0.3 + float(memory.get("confidence", 1.0)), 3),
            "matched_keywords": [],
            "matched_tags": [],
            "retrieval_reason": "No direct keyword match; selected as a recent important memory.",
        }
    )
    return enriched


def calculate_recency_bonus(created_at: str | None) -> float:
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_seconds = max((datetime.now(timezone.utc) - created).total_seconds(), 0)
    if age_seconds < 3600:
        return 0.5
    if age_seconds < 86400:
        return 0.25
    return 0.0


def build_retrieval_reason(
    matched_keywords: list[str],
    matched_tags: list[str],
    query_types: set[str],
    memory_type: str,
    fallback: bool,
) -> str:
    if fallback:
        return "No direct keyword match; selected as a recent important memory."
    reasons = []
    if matched_keywords:
        reasons.append(f"matched content keywords: {', '.join(matched_keywords)}")
    if matched_tags:
        reasons.append(f"matched tags: {', '.join(matched_tags)}")
    if memory_type in query_types:
        reasons.append(f"memory_type {memory_type} matched inferred query intent")
    return "; ".join(reasons) or "Selected by importance and confidence."


def update_memory_access_stats(memory_ids: list[int]) -> None:
    if not memory_ids:
        return
    with connect() as connection:
        for memory_id in memory_ids:
            connection.execute(
                """
                UPDATE memories
                SET last_accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ?
                """,
                (memory_id,),
            )


def find_similar_memory(
    npc_id: str,
    content: str,
    memory_type: str,
    tags: list[str] | None = None,
    facets: list[str] | None = None,
    scope: str = "npc_specific",
    limit: int = 20,
) -> dict[str, Any] | None:
    normalized_content = normalize_memory_content(content)
    normalized_type = normalize_memory_type(memory_type)
    target_tags = set(tags or [])
    target_facets = set(facets or tags or [])
    for memory in get_recent_memories(npc_id=npc_id, limit=limit):
        if memory.get("memory_type") != normalized_type:
            continue
        if memory.get("scope", "npc_specific") != scope:
            continue
        if normalize_memory_content(memory["content"]) == normalized_content:
            return memory
        existing_tags = set(memory.get("tags", []))
        existing_facets = set(memory.get("facets", []))
        target_terms = target_tags | target_facets
        existing_terms = existing_tags | existing_facets
        if target_terms and len(target_terms & existing_terms) >= min(2, len(target_terms)):
            if normalized_content in normalize_memory_content(memory["content"]) or normalize_memory_content(memory["content"]) in normalized_content:
                return memory
    return None


def normalize_memory_content(content: str) -> str:
    return " ".join(content.lower().strip().split())


def normalize_memory_type(memory_type: str) -> str:
    mapping = {
        "quest": "episodic",
        "event": "episodic",
        "relationship": "relational",
        "preference": "procedural",
        "player_profile": "semantic",
    }
    normalized = str(memory_type).strip()
    return mapping.get(normalized, normalized or "episodic")


def add_memory(
    npc_id: str,
    content: str,
    importance: int,
    tags: list[str] | None = None,
    memory_type: str = "episodic",
    confidence: float = 1.0,
    facets: list[str] | None = None,
    scope: str = "npc_specific",
    evidence_text: str = "",
    stability: float = 0.5,
    future_usefulness: float = 0.5,
) -> dict[str, Any]:
    normalized_type = normalize_memory_type(memory_type)
    normalized_facets = facets or tags or []
    tags_json = json.dumps(tags or normalized_facets, ensure_ascii=False)
    facets_json = json.dumps(normalized_facets, ensure_ascii=False)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO memories
                (
                    npc_id, content, memory_type, importance, confidence, tags,
                    facets, scope, evidence_text, stability, future_usefulness
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                npc_id,
                content,
                normalized_type,
                importance,
                confidence,
                tags_json,
                facets_json,
                scope,
                evidence_text,
                stability,
                future_usefulness,
            ),
        )
        memory_id = cursor.lastrowid
    return {
        "id": memory_id,
        "npc_id": npc_id,
        "content": content,
        "memory_type": normalized_type,
        "importance": importance,
        "confidence": confidence,
        "tags": tags or normalized_facets,
        "facets": normalized_facets,
        "scope": scope,
        "evidence_text": evidence_text,
        "stability": stability,
        "future_usefulness": future_usefulness,
    }


def upsert_memory_embedding(
    memory_id: int,
    embedding: list[float],
    model: str,
    provider: str = "mock_hash",
    source_text_hash: str = "",
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO memory_embeddings
                (
                    memory_id,
                    embedding,
                    embedding_model,
                    embedding_provider,
                    embedding_dim,
                    source_text_hash,
                    updated_at
                )
            VALUES
                (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(memory_id) DO UPDATE SET
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                embedding_provider = excluded.embedding_provider,
                embedding_dim = excluded.embedding_dim,
                source_text_hash = excluded.source_text_hash,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                memory_id,
                json.dumps(embedding),
                model,
                provider,
                len(embedding),
                source_text_hash,
            ),
        )


def get_memory_embeddings(npc_id: str = "lina") -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                memory_embeddings.memory_id,
                memory_embeddings.embedding,
                memory_embeddings.embedding_model,
                memory_embeddings.embedding_provider,
                memory_embeddings.embedding_dim,
                memory_embeddings.source_text_hash,
                memory_embeddings.created_at,
                memory_embeddings.updated_at
            FROM memory_embeddings
            JOIN memories ON memories.id = memory_embeddings.memory_id
            WHERE memories.npc_id = ?
            ORDER BY memories.id DESC
            """,
            (npc_id,),
        ).fetchall()
    embeddings = [dict(row) for row in rows]
    for embedding in embeddings:
        embedding["embedding"] = [float(value) for value in json.loads(embedding["embedding"])]
    return embeddings


def get_memory_embedding_metadata(npc_id: str = "lina") -> dict[int, dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                memory_embeddings.memory_id,
                memory_embeddings.embedding_model,
                memory_embeddings.embedding_provider,
                memory_embeddings.embedding_dim,
                memory_embeddings.source_text_hash,
                memory_embeddings.created_at,
                memory_embeddings.updated_at
            FROM memory_embeddings
            JOIN memories ON memories.id = memory_embeddings.memory_id
            WHERE memories.npc_id = ?
            """,
            (npc_id,),
        ).fetchall()
    return {int(row["memory_id"]): dict(row) for row in rows}


def get_memories_without_embeddings(npc_id: str = "lina") -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT memories.*
            FROM memories
            LEFT JOIN memory_embeddings ON memory_embeddings.memory_id = memories.id
            WHERE memories.npc_id = ?
              AND memory_embeddings.memory_id IS NULL
            ORDER BY memories.id ASC
            """,
            (npc_id,),
        ).fetchall()
    memories = [dict(row) for row in rows]
    for memory in memories:
        memory["tags"] = json.loads(memory["tags"])
    return memories


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


def add_recent_interaction(
    npc_id: str,
    player_input: str,
    npc_response: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO recent_interactions
                (npc_id, player_input, npc_response, metadata)
            VALUES
                (?, ?, ?, ?)
            """,
            (npc_id, player_input, npc_response, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        return int(cursor.lastrowid)


def get_recent_interactions(npc_id: str = "lina", limit: int = 5) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM recent_interactions
            WHERE npc_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (npc_id, limit),
        ).fetchall()
    interactions = [dict(row) for row in reversed(rows)]
    for interaction in interactions:
        interaction["metadata"] = json.loads(interaction["metadata"])
    return interactions


def clear_interaction_history(npc_id: str = "lina") -> None:
    """Clear conversation context and logs while preserving state and long-term memories."""
    with connect() as connection:
        connection.execute("DELETE FROM recent_interactions WHERE npc_id = ?", (npc_id,))
        connection.execute("DELETE FROM interaction_logs WHERE npc_id = ?", (npc_id,))


def add_memory_job(
    npc_id: str,
    player_input: str,
    npc_response: str,
    recent_context: list[dict[str, Any]],
    retrieved_lore: list[dict[str, Any]],
    retrieved_memories: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO memory_jobs
                (
                    npc_id,
                    player_input,
                    npc_response,
                    recent_context,
                    retrieved_lore,
                    retrieved_memories,
                    state_before,
                    state_after,
                    tool_calls,
                    state_changes
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                npc_id,
                player_input,
                npc_response,
                json.dumps(recent_context, ensure_ascii=False),
                json.dumps(retrieved_lore, ensure_ascii=False),
                json.dumps(retrieved_memories, ensure_ascii=False),
                json.dumps(state_before, ensure_ascii=False),
                json.dumps(state_after, ensure_ascii=False),
                json.dumps(tool_calls, ensure_ascii=False),
                json.dumps(state_changes, ensure_ascii=False),
            ),
        )
        job_id = int(cursor.lastrowid)
    job = get_memory_job(job_id)
    if job is None:
        raise RuntimeError(f"Memory job was not persisted: {job_id}")
    return job


def get_memory_job(job_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM memory_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return parse_memory_job(row_to_dict(row))


def get_pending_memory_jobs(limit: int = 10) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM memory_jobs
            WHERE status = 'pending'
            ORDER BY id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [job for job in (parse_memory_job(dict(row)) for row in rows) if job is not None]


def update_memory_job_result(
    job_id: int,
    status: str,
    memory_policy: dict[str, Any] | None = None,
    memory_writes: list[dict[str, Any]] | None = None,
    embedding_updates: list[dict[str, Any]] | None = None,
    error: str = "",
) -> dict[str, Any]:
    processed_at = "CURRENT_TIMESTAMP" if status in {"written", "indexed", "failed"} else "NULL"
    with connect() as connection:
        connection.execute(
            f"""
            UPDATE memory_jobs
            SET
                status = ?,
                memory_policy = ?,
                memory_writes = ?,
                embedding_updates = ?,
                error = ?,
                updated_at = CURRENT_TIMESTAMP,
                processed_at = {processed_at}
            WHERE id = ?
            """,
            (
                status,
                json.dumps(memory_policy or {}, ensure_ascii=False),
                json.dumps(memory_writes or [], ensure_ascii=False),
                json.dumps(embedding_updates or [], ensure_ascii=False),
                error,
                job_id,
            ),
        )
    job = get_memory_job(job_id)
    if job is None:
        raise KeyError(f"Memory job not found: {job_id}")
    return job


def get_memory_job_counts() -> dict[str, int]:
    counts = {"pending": 0, "written": 0, "indexed": 0, "failed": 0}
    with connect() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM memory_jobs GROUP BY status"
        ).fetchall()
    for row in rows:
        counts[str(row["status"])] = int(row["count"])
    counts["processed"] = counts.get("written", 0) + counts.get("indexed", 0)
    return counts


def parse_memory_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    parsed = dict(job)
    for field, default in {
        "recent_context": [],
        "retrieved_lore": [],
        "retrieved_memories": [],
        "state_before": {},
        "state_after": {},
        "tool_calls": [],
        "state_changes": [],
        "memory_policy": {},
        "memory_writes": [],
        "embedding_updates": [],
    }.items():
        parsed[field] = json.loads(parsed.get(field) or json.dumps(default))
    return parsed


def log_interaction(
    npc_id: str,
    player_input: str,
    npc_response: str,
    recent_context: list[dict[str, Any]],
    retrieved_lore: list[dict[str, Any]],
    retrieved_memories: list[dict[str, Any]],
    state_snapshot: dict[str, Any],
    memory_policy: dict[str, Any],
    memory_writes: list[dict[str, Any]],
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
                    recent_context,
                    retrieved_lore,
                    retrieved_memories,
                    state_snapshot,
                    memory_policy,
                    memory_writes,
                    decision,
                    tool_calls,
                    state_changes,
                    workflow_steps
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                npc_id,
                player_input,
                npc_response,
                json.dumps(recent_context, ensure_ascii=False),
                json.dumps(retrieved_lore, ensure_ascii=False),
                json.dumps(retrieved_memories, ensure_ascii=False),
                json.dumps(state_snapshot, ensure_ascii=False),
                json.dumps(memory_policy, ensure_ascii=False),
                json.dumps(memory_writes, ensure_ascii=False),
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
        log["recent_context"] = json.loads(log["recent_context"])
        log["retrieved_lore"] = json.loads(log.get("retrieved_lore") or "[]")
        log["state_snapshot"] = json.loads(log.get("state_snapshot") or "{}")
        log["memory_policy"] = json.loads(log["memory_policy"])
        log["memory_writes"] = json.loads(log["memory_writes"])
        log["decision"] = json.loads(log["decision"])
        log["tool_calls"] = json.loads(log["tool_calls"])
        log["state_changes"] = json.loads(log["state_changes"])
        log["workflow_steps"] = json.loads(log["workflow_steps"])
    return logs
