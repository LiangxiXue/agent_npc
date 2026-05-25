# Hybrid RAG NPC Memory Design

## Goal

Hybrid RAG 现在用于 NPC long-term memory 和 lore retrieval，而不是普通文档问答。目标是让 NPC 能处理含蓄表达、同义表达和跨轮指代，同时保留规则检索的可解释性。

```text
typed rule retrieval
+ semantic retrieval
+ typed memory weights
+ provider/backend metadata
+ explainable trace
```

## Retrieval Targets

| Target | Table | Meaning |
| --- | --- | --- |
| Long-term memory | `memories` + `memory_embeddings` | 玩家交互产生的长期事实、事件、关系判断和互动方式 |
| Lore | `lore_documents` + `lore_embeddings` | 稳定世界设定、NPC 背景、社交推演规则 |

## Data Model

Long-term memories remain readable in `memories`. Embeddings live in `memory_embeddings`:

```text
memory_id
embedding
embedding_model
embedding_provider
embedding_dim
source_text_hash
created_at
updated_at
```

Lore uses parallel metadata in `lore_embeddings`.

## Runtime Flow

```text
Player Input
-> recent short-term context
-> lore retrieval
-> database.search_memories(mode)
   -> typed rule scoring
   -> semantic embedding scoring
   -> hybrid score fusion
-> decision
-> tool execution
-> response generation
-> memory job enqueue
-> trace logging

Background:
memory_jobs
-> LLM/mock memory candidate generation
-> optional LLM review
-> programmatic gate / dedup
-> memory writes
-> embedding update for new memory writes
```

Embedding only indexes existing approved records. It does not create facts or mutate state.

## Modes

| Mode | Purpose |
| --- | --- |
| `off` | ablation baseline |
| `legacy` | keyword/tag baseline |
| `typed` | explainable rule retrieval |
| `semantic` | embedding-only retrieval |
| `hybrid` | rule score plus semantic score |

Streamlit and FastAPI preview paths expose retrieval mode selection. `scripts/run_mvp_demo.py` uses `hybrid` to demonstrate the current full path.

## Scoring

Semantic score:

```text
semantic_score = max(cosine_similarity, 0) * 10
```

Hybrid score:

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
retrieval_backend
requested_retrieval_backend
backend_fallback_reason
query_embedding_provider
query_embedding_latency_ms
```

## Stable Mock Path

The default embedding provider is `mock_hash`. It uses deterministic token/concept features and does not require an API key. This keeps tests, classroom demos, and report artifacts reproducible.

Existing memories can be indexed with:

```powershell
python scripts/rebuild_memory_embeddings.py
```

## Verification

The memory evaluation compares:

```text
no_long_term_memory
legacy_keyword_memory
typed_memory_policy
semantic_rag
hybrid_rag
```

`Retrieval Layer Comparison` also checks mock/real provider and SQLite/FAISS backend combinations. Real provider cases are skipped when not configured, not treated as local test failures.
