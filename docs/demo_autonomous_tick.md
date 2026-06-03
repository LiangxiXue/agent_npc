# Demo-Grade LLM-Constrained Autonomous NPC Slice

## What This Demo Proves

This slice demonstrates a proactive character-agent runtime:

```text
WorldEvent
-> visibility resolver / NPC inbox
-> LLM-constrained autonomous tick
-> retrieved memories
-> available_actions / unavailable_actions
-> LLM selected action
-> ActionValidator
-> NarrativeEnvironment.execute()
-> npc_plans / cooldowns
-> proactive_messages mailbox
-> autonomous_tick_logs / trace view
```

World events are not treated as player input. The LLM can choose goals, plan steps, actions, reflections, memory candidates, and proactive wording, but it can only choose from `ActionCatalog.available_actions`. World side effects still go through `ActionValidator` and `NarrativeEnvironment.execute()`.

## Reset And Seed

```powershell
python scripts/reset_demo_db.py
python scripts/seed_autonomous_demo.py
```

Seeded scenarios:

- `player_asked_ruins_too_early` -> Lina
- `badge_evidence_verified` -> Ron
- `player_interested_in_ruins` -> Sable

## API Demo

Start the API:

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

Create a world event:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/world/events -ContentType 'application/json' -Body '{
  "event_type": "player_asked_ruins_too_early",
  "content": "Player asked Lina about the ruins entrance before earning trust.",
  "source_type": "player",
  "source_id": "demo",
  "location_id": "tavern",
  "visibility": "npc_only",
  "payload": {"target_npc_ids": ["lina"]}
}'
```

Run an autonomous tick:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/npcs/lina/tick -ContentType 'application/json' -Body '{
  "mode": "llm_constrained"
}'
```

Read proactive messages:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/npcs/messages?npc_id=lina
```

Open a trace:

```text
http://127.0.0.1:8000/api/trace/autonomous/{tick_log_id}
http://127.0.0.1:8000/api/trace/autonomous/{tick_log_id}?format=html
```

## Scripted Real LLM Demo

Set an OpenAI-compatible runtime:

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "<key>"
python scripts/run_autonomous_llm_demo.py
```

For deterministic smoke testing without spending LLM tokens:

```powershell
python scripts/run_autonomous_llm_demo.py --mock
```

The script prints, for each case:

- `trigger_event_id`
- `tick_log_id`
- `npc_id`
- `visible_events`
- `retrieved_memories`
- `available_actions`
- `unavailable_actions`
- `llm_decision`
- `validation`
- `state_diff`
- `proactive_message`
- `trace_url`

## Expected Demo Beats

### Demo 1: Lina Proactively Tests Trust

Input event: `player_asked_ruins_too_early`

Expected:

- Lina sees only her visible event.
- LLM sets `goal = test_player_trust`.
- LLM selects `offer_minor_task` from available actions.
- `reveal_partial_lore` is excluded because trust is below 60.
- `ActionValidator` allows the safe task-start action.
- `NarrativeEnvironment.execute()` starts the low-risk `lost_key` task.
- A proactive message is queued.

### Demo 2: Ron Advances Only With Evidence

Input event: `badge_evidence_verified`

Expected:

- Ron sees verified badge evidence.
- `grant_conditional_access` becomes available.
- The environment can start the `gate_badge` procedural flow.
- Without the evidence event, the same action appears in unavailable actions with `badge evidence missing`.

### Demo 3: Sable Misleads But Cannot Mutate World Authority

Input event: `player_interested_in_ruins`

Expected:

- Sable sees the player interest event.
- LLM can choose `mislead_player` or `redirect_to_false_clue`.
- Sable action specs forbid `unlock_location`, `complete_quest`, `modify_other_npc_trust`, `grant_gate_access`, and `rewrite_lore_fact`.
- If the LLM proposes an unavailable action such as `unlock_location`, the tick records `rejected_by_available_actions` and falls back to a safe message.
