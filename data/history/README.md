# Demo History Archive

This folder stores pre-guardrails demo artifacts for project reporting.

The archived `pre-guardrails` files were produced before the current fixes:

- LLM-generated `state_summary` could disagree with the actual tool execution order.
- The NPC response could rewrite major world facts, such as moving the ruins entrance to another location.
- The key quest intent was too coarse, so starting and completing the key quest were not clearly separated.

The active demo should use:

```text
data/agent_state.db
data/agent_trace_export.json
```

Use the archived files only as evidence of the system's iteration process, not as the final demo trace.
