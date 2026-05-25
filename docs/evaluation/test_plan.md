# Test Plan

## Goal

Verify that the project behaves like an Agent system with stateful actions, retrieval, tool execution, memory jobs, and explainable traces, not a plain chatbot.

## Automated Tests

Run:

```powershell
.venv/bin/python -m unittest discover -s tests -v
```

Current result:

```text
46 tests passed
```

Current test files:

```text
tests/test_api.py
tests/test_display_translation.py
tests/test_workflow.py
```

## Covered Behaviors

### Lina Low-Trust Refusal

Input:

```text
我想打听一下地下遗迹的入口。
```

Expected:

- intent: `withhold_ruins_entrance`;
- `social_intent`: `conceal`;
- no location unlock;
- trust remains 20.

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
