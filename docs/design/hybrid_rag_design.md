# Hybrid RAG NPC Memory Design

## Goal

Hybrid RAG upgrades Lina's long-term memory retrieval without changing state ownership:

```text
rule retrieval
+ semantic retrieval
+ typed memory weights
+ Memory Policy writes
+ explainable trace
```

The retrieval target is NPC memory in SQLite, not external documents.

## Data Model

Long-term memory remains readable in `memories`. Embeddings live in `memory_embeddings`:

```text
memory_id
embedding
embedding_model
embedding_dim
created_at
updated_at
```

This keeps memory facts and vector indexes rebuildable independently.

## Runtime Flow

```text
Player Input
-> recent short-term context
-> database.search_memories(mode)
   -> typed rule scoring
   -> semantic embedding scoring
   -> hybrid score fusion
-> decision
-> tool execution
-> response generation
-> Memory Policy
-> embedding update for new memory writes
-> trace logging
```

`Memory Policy` is still the only component that decides long-term memory writes. Embeddings only index existing memory records.

## Modes

| Mode | Purpose |
| --- | --- |
| `off` | ablation baseline |
| `legacy` | keyword/tag baseline |
| `typed` | current explainable rule retrieval |
| `semantic` | embedding-only retrieval |
| `hybrid` | rule score plus semantic score |

The default workflow mode remains `typed` so current demos stay stable.

## Scoring

`semantic_score` is cosine similarity mapped to a positive 0-10 range:

```text
semantic_score = max(cosine_similarity, 0) * 10
```

Hybrid retrieval starts with the typed rule score, then adds semantic score:

```text
retrieval_score = rule_score + semantic_score
```

Trace fields:

```text
retrieval_score
rule_score
semantic_score
semantic_reason
score_breakdown
```

## Stable Mock Path

The default embedding provider is `mock_hash`. It uses deterministic token/concept features and does not require an API key. This keeps tests, classroom demos, and report artifacts reproducible.

Existing memories can be indexed with:

```bash
python scripts/rebuild_memory_embeddings.py
```

## Verification

The current evaluation compares five variants:

```text
no_long_term_memory
legacy_keyword_memory
typed_memory_policy
semantic_rag
hybrid_rag
```

Open-expression scenarios include indirect help, trust, and preference references. The expected report shape is that `legacy_keyword_memory` fails some open-expression cases while `semantic_rag` and `hybrid_rag` pass them with explainable semantic scores.
