# Memory System Evaluation Summary

This report compares rule, semantic, and hybrid memory modes for the single-NPC Lina workflow.

## Variants

- `no_long_term_memory`: retrieval=`off`, policy_enabled=`False`. Disables long-term memory retrieval and long-term memory writes.
- `legacy_keyword_memory`: retrieval=`legacy`, policy_enabled=`True`. Uses long-term memory writes, but retrieves by legacy keyword/tag scoring.
- `typed_memory_policy`: retrieval=`typed`, policy_enabled=`True`. Uses typed long-term memory, Memory Policy, confidence, and query-intent scoring.
- `semantic_rag`: retrieval=`semantic`, policy_enabled=`True`. Uses deterministic embedding retrieval over NPC long-term memories.
- `hybrid_rag`: retrieval=`hybrid`, policy_enabled=`True`. Combines typed rule scoring with deterministic semantic retrieval.

## Aggregate Results

| Variant | Passed | Pass rate | Retrieval success | Decision success | Explainability | Long-term writes | Turns with retrieved memory | Failed scenarios |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `no_long_term_memory` | 10/10 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 0 | - |
| `legacy_keyword_memory` | 8/10 | 0.8 | 0.667 | 0.833 | 1.0 | 16 | 6 | indirect_trust_reference, preference_paraphrase |
| `typed_memory_policy` | 10/10 | 1.0 | 1.0 | 1.0 | 1.0 | 17 | 6 | - |
| `semantic_rag` | 10/10 | 1.0 | 1.0 | 1.0 | 1.0 | 17 | 6 | - |
| `hybrid_rag` | 10/10 | 1.0 | 1.0 | 1.0 | 1.0 | 17 | 6 | - |

## Scenario Matrix

| Scenario | no_long_term_memory | legacy_keyword_memory | typed_memory_policy | semantic_rag | hybrid_rag |
| --- | --- | --- | --- | --- | --- |
| `plain_chat` | PASS | PASS | PASS | PASS | PASS |
| `key_return` | PASS | PASS | PASS | PASS | PASS |
| `followup_ruins_after_key` | PASS | PASS | PASS | PASS | PASS |
| `memory_only_ruins_gate` | PASS | PASS | PASS | PASS | PASS |
| `preference_memory` | PASS | PASS | PASS | PASS | PASS |
| `duplicate_key_return` | PASS | PASS | PASS | PASS | PASS |
| `short_term_context` | PASS | PASS | PASS | PASS | PASS |
| `implicit_help_reference` | PASS | PASS | PASS | PASS | PASS |
| `indirect_trust_reference` | PASS | FAIL | PASS | PASS | PASS |
| `preference_paraphrase` | PASS | FAIL | PASS | PASS | PASS |

## Key Observations

- `typed_memory_policy` passed 10/10 scenarios and produced 17 long-term memory writes.
- `no_long_term_memory` produced 0 long-term writes, which is useful as a control but cannot support memory-gated behavior.
- `legacy_keyword_memory` retrieved memory in 6 turn(s); typed retrieval adds memory type and query-intent explanation on top of keyword/tag matching.
- `semantic_rag` passed 10/10 scenarios and adds `semantic_score` for open expressions.
- `hybrid_rag` passed 10/10 scenarios while keeping rule scores and semantic scores visible.
- The `memory_only_ruins_gate` scenario isolates memory as the deciding factor by keeping trust low and the quest incomplete.

## Retrieval Layer Comparison

| Config | Status | Effective backend | Latency ms | Retrieved | Intent | Fallbacks |
| --- | --- | --- | ---: | ---: | --- | --- |
| `mock_sqlite_hybrid` | ran | sqlite_cosine | 226.086 | 3 | reveal_ruins_entrance | - |
| `mock_faiss_hybrid` | ran | sqlite_cosine | 212.591 | 3 | reveal_ruins_entrance | faiss_unavailable: No module named 'faiss' |
| `real_sqlite_hybrid` | skipped | sqlite_cosine | - | - | - | No embedding API key configured in environment. |
| `real_faiss_hybrid` | skipped | faiss | - | - | - | No embedding API key configured in environment. |

## Output Files

- JSON report: `data\eval\memory_eval_report.json`
- Markdown summary: `data\eval\memory_eval_summary.md`
