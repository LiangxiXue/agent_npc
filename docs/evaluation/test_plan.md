# Test Plan

## Goal

Verify that the project behaves like an Agent system with stateful actions, retrieval, tool execution, memory jobs, and explainable traces, not a plain chatbot.

The current target is a narrative character agent with both player-driven turns and autonomous NPC ticks. Trace should show subjective belief, emotion, active goal, plan step, social strategy, environment execution, reflection, response constraints, visible world events, ActionCatalog available/unavailable actions, LLM-selected autonomous actions, validation, mailbox output, and cooldown/plan blockers.

## Automated Tests

Run:

```powershell
.venv/bin/python -m unittest discover -s tests -v
```

Current result:

```text
Run the command above for the current count. The suite includes API, display translation, LLM client, workflow, environment, and NPC mind tests.
```

Current test files:

```text
tests/test_api.py
tests/test_action_catalog.py
tests/test_autonomous_storage.py
tests/test_autonomous_tick.py
tests/test_display_translation.py
tests/test_event_visibility.py
tests/test_llm_client.py
tests/test_npc_mind.py
tests/test_workflow.py
```

## Autonomous NPC Runtime Coverage

Expected:

- structured `world_events` save/load and legacy fallback;
- additive migration for legacy `world_events(content, created_at)`;
- `public`, `location`, `private`, and `npc_only` visibility dispatch;
- NPC inbox seen behavior;
- invisible private events do not enter unrelated NPC observations;
- ActionCatalog returns available actions and unavailable action reasons;
- Ron cannot grant gate access without badge evidence;
- Sable action specs forbid unlock, completion, other-NPC trust mutation, gate grant, and lore rewrite effects;
- LLM-constrained tick logs LLM decision, proposed action, validation, action result, memory candidate, reflection, and timeline;
- unavailable LLM action proposals are rejected before validator;
- invalid action args are recorded in trace;
- one-command-at-a-time guard rejects compound proposals;
- proactive messages are queued and can be marked delivered;
- plan blocker, cooldown, budget, memory-only, paused, disabled, and no-op tick paths are covered;
- autonomous trace JSON and HTML endpoints are available.

## Covered Behaviors

### Lina Low-Trust Refusal

Input:

```text
我想打听一下地下遗迹的入口。
```

Expected:

- intent: `withhold_ruins_entrance`;
- `social_intent`: `conceal`;
- NPCMind belief stance: suspicious;
- active goal: `protect_underground_ruins_entrance`;
- active plan: `lina_test_player_trust`, step `ask_motive`;
- NPCAction includes goal id, plan step, and a concrete action type such as `probe_intent`;
- no location unlock;
- trust remains 20.

### Character-Agent Mind Layer

Expected:

- `NPCMind` can serialize nested belief, emotion, goal, plan, and trace state;
- the same ruins request activates different goals for Lina and Sable;
- Lina can continue a remembered trust-test plan from plan memory facets;
- reflection memory is internal and future-facing, not spoken as player-facing "I remembered this" text;
- ordinary short-term chat does not automatically become long-term memory.

### Lina Quest Completion And Later Unlock

Inputs:

```text
我把你丢失的钥匙找回来了。
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

Expected:

- first task path completes `lost_key`;
- trust and affection increase;
- player receives `tavern_discount_coupon`;
- later ruins request can unlock `underground_ruins_entrance`;
- trace stores tools, state changes, decision, workflow steps, and memory job status.

### Four-NPC Quest Lines

Expected:

- Ron can start/complete `gate_badge`;
- Mira can start/complete `ancient_notes`;
- Sable can start/complete `relic_tip`;
- Sable can redirect/deceive but cannot unlock the ruins;
- each NPC keeps its own quest, memories, recent context, and logs.

### Universal Task State Machine

Expected:

- tasks cannot complete from `not_started`;
- one NPC cannot mutate another NPC's quest;
- unsupported LLM intents/tools are rejected;
- blocked transitions become `probe_for_evidence` with `state_machine.blocked` in trace.
- `ActionValidator` is the boundary that sanitizes invalid actions before environment execution.

### Background Memory Jobs

Expected:

- synchronous turns enqueue `memory_jobs`;
- `process_pending_memory_jobs()` writes approved long-term memories later;
- `scripts/memory_worker.py` can continuously consume pending memory jobs;
- memory jobs record status, memory writes, embedding updates, and errors;
- FastAPI `/api/process-memory-jobs` processes queued work.

### Retrieval And Context

Expected:

- lore retrieval returns shared and NPC-specific lore;
- semantic retrieval handles implicit references;
- hybrid retrieval includes rule and semantic scores;
- FAISS fallback works when optional dependencies are unavailable.

### API And Player UI Contract

Expected:

- bootstrap returns player UI state;
- `/api/turn` runs workflow and returns refreshed state;
- preview and trace endpoints are available;
- translation debug endpoint uses display translation when configured.

### Display Translation

Expected:

- Chinese text is skipped;
- translation is disabled without OpenAI-compatible LLM;
- translation uses existing LLM config and cache when enabled.

## Manual UI Test

Streamlit debug UI:

```powershell
streamlit run app.py
```

Verify:

- NPC selector works for Lina/Ron/Mira/Sable;
- state panel shows selected NPC and primary quest;
- retrieval preview exposes lore/memory scores;
- trace shows social intent, tools, state changes, timings, memory job status;
- trace shows Belief Update, Goal Selection, Plan Step, Action Result, and Reflection stages;
- trace export writes `data/agent_trace_export.json`.

React player UI:

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev
python scripts/memory_worker.py --limit 5
```

Verify:

- browser opens `http://127.0.0.1:5173/`;
- NPC selection and pixel assets render;
- dialogue updates state and task panels;
- developer trace panel remains inspectable.
- worker changes pending memory jobs into `written` or `indexed`.

## Autonomous Demo

Run:

```powershell
python scripts/run_autonomous_llm_demo.py --mock
```

For a real LLM run:

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "<key>"
python scripts/run_autonomous_llm_demo.py
```

Expected cases:

- `lina_early_ruins`: Lina sees an early ruins-access event, selects `offer_minor_task`, starts the low-risk trust-test flow, queues a proactive message, and logs excluded `reveal_partial_lore`.
- `ron_badge_verified`: Ron sees verified badge evidence, can select `grant_conditional_access`, and advances the procedural gate-badge flow through the environment.
- `sable_deception_constrained`: Sable can redirect/mislead, but forbidden world-authority effects remain blocked by available actions and validator boundaries.

## Memory Evaluation

Run:

```powershell
python scripts/run_memory_eval.py
```

Expected outputs:

```text
data/eval/memory_eval_report.json
data/eval/memory_eval_summary.md
```

Expected modes:

- `no_long_term_memory`;
- `legacy_keyword_memory`;
- `typed_memory_policy`;
- `semantic_rag`;
- `hybrid_rag`.

The report should show where semantic/hybrid retrieval improves open-expression cases over legacy keyword retrieval.

## Frontend Build

Run:

```powershell
cd frontend
npm run build
```

Expected: TypeScript build and Vite build pass.
