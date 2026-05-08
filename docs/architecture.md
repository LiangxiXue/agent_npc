# MVP Architecture

## Project Positioning

This MVP uses a text-adventure NPC scenario only as a controlled test environment. The main object is the Agent workflow, not the game plot.

## Workflow

```text
Player Input
-> Memory Retrieval
-> State Load
-> Structured Decision
-> Tool Execution
-> Response Generation
-> Memory Update
-> Trace Logging
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `app.py` | Streamlit UI and trace visualization |
| `src/agent/workflow.py` | Agent turn orchestration and mock structured decision |
| `src/agent/decision.py` | LLM-ready structured decision layer, currently backed by deterministic mock logic |
| `src/agent/response.py` | Final NPC response generation from decision keywords, using optional LLM polish with deterministic fallback |
| `src/agent/llm_client.py` | Optional OpenAI-compatible client using standard library HTTP |
| `src/agent/prompts.py` | Prompt and output schema template for later LLM integration |
| `src/agent/world_facts.py` | Canonical facts and narrow major-fact guards for response validation |
| `src/storage/database.py` | SQLite initialization, persistence, queries, logs |
| `src/storage/schema.sql` | Database schema |
| `src/tools/sqlite_tools.py` | Tool functions that mutate SQLite state |
| `tests/test_workflow.py` | Regression tests for the core Agent behavior |

## Why This Is Agent-Oriented

The system does not simply retrieve memory and generate a reply. It uses memory and state as decision inputs, then executes tools that change external state.

Example:

```text
Player returns Lina's key
-> add_memory
-> update_trust
-> update_affection
-> update_quest_status
-> give_item
-> log_interaction
```

These effects are written into SQLite and influence later turns.

## Persistent Trace

Each interaction log stores:

- retrieved memories;
- structured decision;
- system-generated `state_before` and `state_after`;
- response keywords and response-generation metadata;
- tool calls;
- state changes;
- workflow steps.

This makes the behavior reproducible for reports and classroom demos.

## Current Limitation

The MVP can run fully in deterministic mock mode. In OpenAI-compatible mode, the LLM may now participate in two places: structured decision generation and final NPC response polishing. SQLite remains the source of truth for state snapshots. The response polishing step takes the Agent decision, `response_keywords`, current state, canonical world facts, memory, and tool results as constraints, then writes only Lina's final in-character reply.

The guardrails are deliberately narrow: business rules protect task and tool consistency, while response validation only blocks major fact conflicts. Lina is still allowed to vary phrasing, gestures, and small atmosphere details so the NPC does not become a rigid template.

An optional OpenAI-compatible path already exists. It is disabled by default and controlled through environment variables, so the project remains runnable for grading even without paid API access.
