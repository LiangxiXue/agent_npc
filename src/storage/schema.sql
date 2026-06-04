CREATE TABLE IF NOT EXISTS npcs (
    npc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT NOT NULL,
    hidden_alignment TEXT NOT NULL DEFAULT 'neutral',
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
    memory_type TEXT NOT NULL DEFAULT 'episodic',
    importance INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    facets TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'npc_specific',
    evidence_text TEXT NOT NULL DEFAULT '',
    stability REAL NOT NULL DEFAULT 0.5,
    future_usefulness REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

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
);

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
);

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
);

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
);

CREATE TABLE IF NOT EXISTS recent_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'legacy',
    source_type TEXT NOT NULL DEFAULT 'legacy',
    source_id TEXT,
    location_id TEXT,
    visibility TEXT NOT NULL DEFAULT 'public',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS npc_event_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    relevance_score REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id),
    FOREIGN KEY (event_id) REFERENCES world_events (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS autonomous_tick_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    trigger_event_id INTEGER,
    mode TEXT NOT NULL,
    observation_json TEXT NOT NULL DEFAULT '{}',
    retrieved_memories_json TEXT NOT NULL DEFAULT '[]',
    available_actions_json TEXT NOT NULL DEFAULT '[]',
    unavailable_actions_json TEXT NOT NULL DEFAULT '[]',
    llm_decision_json TEXT NOT NULL DEFAULT '{}',
    proposed_action_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    action_result_json TEXT NOT NULL DEFAULT '{}',
    plan_update_json TEXT NOT NULL DEFAULT '{}',
    memory_candidate_json TEXT NOT NULL DEFAULT '{}',
    reflection_json TEXT NOT NULL DEFAULT '{}',
    proactive_message_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id),
    FOREIGN KEY (trigger_event_id) REFERENCES world_events (id)
);

CREATE TABLE IF NOT EXISTS proactive_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    trigger_event_id INTEGER,
    tick_log_id INTEGER,
    priority INTEGER NOT NULL DEFAULT 5,
    delivered INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id),
    FOREIGN KEY (trigger_event_id) REFERENCES world_events (id),
    FOREIGN KEY (tick_log_id) REFERENCES autonomous_tick_logs (id)
);

CREATE TABLE IF NOT EXISTS npc_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,
    steps_json TEXT NOT NULL DEFAULT '[]',
    current_step TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    blocker TEXT NOT NULL DEFAULT '',
    source_event_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id),
    FOREIGN KEY (source_event_id) REFERENCES world_events (id)
);

CREATE TABLE IF NOT EXISTS npc_cooldowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    cooldown_key TEXT NOT NULL,
    until_turn_or_timestamp TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (npc_id, cooldown_key),
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS npc_runtime_state (
    npc_id TEXT PRIMARY KEY,
    lifecycle_status TEXT NOT NULL DEFAULT 'active',
    tick_enabled INTEGER NOT NULL DEFAULT 1,
    last_tick_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS world_arc_state (
    arc_id TEXT PRIMARY KEY,
    phase TEXT NOT NULL,
    tension INTEGER NOT NULL DEFAULT 0,
    advantage TEXT NOT NULL DEFAULT 'none',
    outcome TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scene_objects (
    object_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location_id TEXT NOT NULL,
    description TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS npc_locations (
    npc_id TEXT PRIMARY KEY,
    location_id TEXT NOT NULL,
    activity TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS npc_routines (
    npc_id TEXT PRIMARY KEY,
    routine_type TEXT NOT NULL,
    location_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_content TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

CREATE TABLE IF NOT EXISTS interaction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    recent_context TEXT NOT NULL DEFAULT '[]',
    retrieved_lore TEXT NOT NULL DEFAULT '[]',
    retrieved_memories TEXT NOT NULL,
    state_snapshot TEXT NOT NULL DEFAULT '{}',
    memory_policy TEXT NOT NULL DEFAULT '{}',
    memory_writes TEXT NOT NULL DEFAULT '[]',
    decision TEXT NOT NULL,
    tool_calls TEXT NOT NULL,
    state_changes TEXT NOT NULL,
    workflow_steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);

-- ── Living World Runtime tables ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS traveler_state (
    traveler_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    current_location TEXT NOT NULL,
    inventory_json TEXT NOT NULL DEFAULT '[]',
    private_notes_json TEXT NOT NULL DEFAULT '[]',
    active_goal_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS traveler_npc_relationship (
    traveler_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.0,
    suspicion REAL NOT NULL DEFAULT 0.0,
    affinity REAL NOT NULL DEFAULT 0.0,
    leverage REAL NOT NULL DEFAULT 0.0,
    exposure REAL NOT NULL DEFAULT 0.0,
    debt REAL NOT NULL DEFAULT 0.0,
    last_tone TEXT NOT NULL DEFAULT 'neutral',
    known_secret_ids_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (traveler_id, npc_id),
    FOREIGN KEY (traveler_id) REFERENCES traveler_state(traveler_id),
    FOREIGN KEY (npc_id) REFERENCES npcs(npc_id)
);

CREATE TABLE IF NOT EXISTS traveler_tick_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    traveler_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    trigger_event_id INTEGER,
    observation_json TEXT NOT NULL DEFAULT '{}',
    retrieved_memories_json TEXT NOT NULL DEFAULT '[]',
    available_actions_json TEXT NOT NULL DEFAULT '[]',
    action_biases_json TEXT NOT NULL DEFAULT '[]',
    llm_decision_json TEXT NOT NULL DEFAULT '{}',
    proposed_action_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    action_result_json TEXT NOT NULL DEFAULT '{}',
    state_changes_json TEXT NOT NULL DEFAULT '[]',
    relationship_changes_json TEXT NOT NULL DEFAULT '[]',
    created_events_json TEXT NOT NULL DEFAULT '[]',
    reflection_json TEXT NOT NULL DEFAULT '{}',
    deception_metadata_json TEXT NOT NULL DEFAULT '{}',
    disclosure_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (traveler_id) REFERENCES traveler_state(traveler_id),
    FOREIGN KEY (trigger_event_id) REFERENCES world_events(id)
);

CREATE TABLE IF NOT EXISTS secret_tracking (
    secret_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    label TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    disclosed_to_json TEXT NOT NULL DEFAULT '[]',
    exposure_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
