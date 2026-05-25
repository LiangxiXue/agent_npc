# Current Architecture

## Project Positioning

This project uses a text-adventure NPC scene as a controlled testbed for an Agent workflow. The core deliverable is the stateful Agent system: context retrieval, structured decision, tool execution, state persistence, memory writing, and explainable trace.

## Runtime Surfaces

| Surface | File / module | Purpose |
| --- | --- | --- |
| Streamlit debug UI | `app.py` | Inspect provider status, NPC state, retrieval, trace, tools, logs, and exports |
| Player UI | `frontend/` | React/Vite pixel RPG experience for normal interaction |
| Player API | `src/api/server.py` | FastAPI wrapper around the same workflow, plus preview/export/index/job endpoints |
| CLI demo | `scripts/run_mvp_demo.py` | Stable four-NPC mock demonstration |
| Background memory CLI | `scripts/process_memory_jobs.py` | Processes one batch of queued long-term memory jobs |
| Background memory worker | `scripts/memory_worker.py` | Continuously consumes queued long-term memory jobs |

## Synchronous Turn Workflow

```text
Player Input
-> Recent Context Load
-> Lore Retrieval
-> Long-Term Memory Retrieval
-> State Load
-> Turn Classification
-> Structured Decision
-> Program-Owned Quest State Machine
-> Tool Execution
-> Response Generation
-> Background Memory Job Enqueue
-> Short-Term Interaction Write
-> Trace Logging
```

The synchronous path is optimized for player latency. It records enough information for memory processing, but it does not wait for LLM memory candidate generation, review, deduplication, or embedding updates.

## Background Memory Workflow

```text
memory_jobs pending row
-> MemoryPolicyInput reconstruction
-> LLM/mock memory candidate generation
-> optional LLM review
-> programmatic gate
-> deduplication
-> SQLite memory write
-> embedding update
-> memory_jobs status update
```

Background processing is available through:

```powershell
python scripts/process_memory_jobs.py --limit 10
```

For continuous background processing:

```powershell
python scripts/memory_worker.py --limit 5
```

The FastAPI app also exposes `/api/process-memory-jobs` for explicit player UI/debug flow processing.

## Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `src/agent/workflow.py` | Agent turn orchestration, timing capture, memory job enqueue, trace logging |
| `src/agent/context.py` | Explicit context pack assembly for lore, memory, state, and recent dialogue |
| `src/agent/lore_retrieval.py` | Stable world/NPC lore retrieval |
| `src/agent/decision.py` | Structured decision, social metadata, intent validation, universal task state machine |
| `src/agent/turn_classifier.py` | Fast routing between simple rule path, ambiguous turns, sensitive requests, and social maneuvers |
| `src/agent/response.py` | Final NPC response generation with optional LLM polish and deterministic fallback |
| `src/agent/memory_jobs.py` | Queue and process background long-term memory work |
| `src/agent/memory_policy.py` | Long-term memory write policy, LLM candidate orchestration, gate, dedup |
| `src/agent/llm_memory_candidate.py` | OpenAI-compatible and mock memory candidate generator |
| `src/agent/memory_candidate_review.py` | OpenAI-compatible reviewer with mock pass-through review |
| `src/agent/memory_candidate_gate.py` | Programmatic hard gate for evidence/type/state support |
| `src/agent/embedding_client.py` | `mock_hash` and OpenAI-compatible embedding provider abstraction |
| `src/agent/semantic_retrieval.py` | Memory embedding indexing and semantic retrieval |
| `src/agent/trace_export.py` | Shared trace export payload and file writer |
| `src/storage/database.py` | SQLite initialization, migrations, persistence, queries, logs, memory jobs |
| `src/storage/schema.sql` | Canonical schema for state, lore, memory, jobs, and logs |
| `src/tools/sqlite_tools.py` | Tool functions that mutate SQLite state |
| `src/api/server.py` | FastAPI player/debug API |

## Data Ownership

SQLite is the source of truth for:

- NPC state and hidden alignment;
- player location, inventory, and unlocked locations;
- quest lifecycle;
- recent interactions;
- long-term memories;
- memory/lore embeddings;
- lore documents;
- memory jobs;
- world events;
- interaction logs.

LLM calls can propose decision JSON, polish response text, generate memory candidates, or review memory candidates. They do not own canonical state snapshots, tool permissions, quest lifecycle, or final memory writes.

## Quest And Social Safety

All NPC tasks use the same lifecycle:

```text
not_started -> in_progress -> completed
```

`src/agent/decision.py` blocks:

- direct `not_started -> completed` jumps;
- one NPC mutating another NPC's primary quest;
- quest updates from unrelated intents;
- unsupported tools or invalid tool arguments;
- social deception that tries to unlock or rewrite canonical locations.

Social behavior is represented as metadata:

```text
social_intent
social_stance.target
social_stance.attitude
social_stance.intensity
social_stance.reason
```

This lets Sable deceive or redirect in dialogue while the program keeps facts and state changes bounded.

## Trace

Each interaction log stores:

- `recent_context`;
- `retrieved_lore`;
- `retrieved_memories`;
- system-generated `state_snapshot`;
- `memory_policy`;
- `memory_writes`;
- structured `decision`;
- `tool_calls`;
- `state_changes`;
- `workflow_steps`.

The `decision` also carries route, classification, timing-adjacent metadata, response generation info, background memory job status, and state-machine blocks when applicable.

## Current Boundaries

- Agent orchestration is still a custom Python workflow, not LangGraph.
- Background memory jobs are queue-based but not yet run by a permanent worker.
- Real LLM and real embedding providers are optional; tests and demos keep deterministic mock paths.
- FAISS is optional and falls back to SQLite cosine retrieval when unavailable.
