# MVP Architecture

## Project Positioning

This MVP uses a text-adventure NPC scenario only as a controlled test environment. The main object is the Agent workflow, not the game plot.

## Workflow

```text
Player Input
-> Short-Term Context Load
-> Long-Term Memory Retrieval
-> State Load
-> Structured Decision
-> Tool Execution
-> Response Generation
-> Memory Policy
   -> LLM Memory Candidate Generation
   -> LLM Memory Candidate Review
   -> Programmatic Gate
-> Short-Term Interaction Write
-> Trace Logging
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `app.py` | Streamlit UI and trace visualization |
| `src/agent/workflow.py` | Agent turn orchestration and mock structured decision |
| `src/agent/decision.py` | LLM-ready structured decision layer, currently backed by deterministic mock logic |
| `src/agent/memory_policy.py` | Long-term memory write entrypoint, combining rule candidates, LLM candidates, LLM review, hard gate checks, and deduplication |
| `src/agent/llm_memory_candidate.py` | OpenAI-compatible memory candidate generator; proposes memories but never writes SQLite |
| `src/agent/memory_candidate_review.py` | OpenAI-compatible review agent for subject, evidence, overreach, and type checks |
| `src/agent/memory_candidate_gate.py` | Programmatic hard gate for allowed types, evidence support, state/tool support, and player-grounded memories |
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
-> update_trust
-> update_affection
-> update_quest_status
-> give_item
-> memory_policy generates and reviews memory candidates
-> programmatic gate approves quest/event/relationship memories
-> log_interaction
```

These effects are written into SQLite and influence later turns.

## Persistent Trace

Each interaction log stores:

- retrieved memories;
- short-term context;
- memory policy result and long-term memory writes;
- structured decision;
- system-generated `state_before` and `state_after`;
- response keywords and response-generation metadata;
- tool calls;
- state changes;
- workflow steps.

This makes the behavior reproducible for reports and classroom demos.

## Current Limitation

The MVP can run fully in deterministic mock mode. In OpenAI-compatible mode, the LLM may now participate in four places: structured decision generation, final NPC response polishing, memory candidate generation, and memory candidate review. All four paths use the same `src/agent/llm_client.py` OpenAI-compatible API settings from `.env`.

SQLite remains the source of truth for state snapshots. LLM memory modules only produce or review candidates. The final write still happens inside `memory_policy.py` after programmatic gate checks and deduplication.

The guardrails are deliberately narrow: business rules protect task and tool consistency, while response validation only blocks major fact conflicts. Lina is still allowed to vary phrasing, gestures, and small atmosphere details so the NPC does not become a rigid template.

An optional OpenAI-compatible path already exists. It is disabled by default and controlled through environment variables, so the project remains runnable for grading even without paid API access.
