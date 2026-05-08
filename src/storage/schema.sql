CREATE TABLE IF NOT EXISTS npcs (
    npc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT NOT NULL,
    mood TEXT NOT NULL,
    trust INTEGER NOT NULL,
    affection INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS player_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    location TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_items (
    item TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS unlocked_locations (
    location TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS quests (
    quest_id TEXT PRIMARY KEY,
    npc_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interaction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    retrieved_memories TEXT NOT NULL,
    decision TEXT NOT NULL,
    tool_calls TEXT NOT NULL,
    state_changes TEXT NOT NULL,
    workflow_steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);
