# Hybrid RAG Migration Record

本文最初是从 typed retrieval 迁移到 Hybrid RAG 的执行计划。当前主体迁移已经完成，本文现在作为阶段记录和后续维护清单。

## Current Status

已落地：

- `memory_embeddings`：长期记忆向量索引；
- `lore_documents` / `lore_embeddings`：稳定设定和 NPC 背景检索；
- `src/agent/embedding_client.py`：`mock_hash` 与 OpenAI-compatible provider；
- `src/agent/semantic_retrieval.py`：语义检索、embedding rebuild、backend fallback；
- `database.search_memories(..., mode="off|legacy|typed|semantic|hybrid")`；
- `sqlite_cosine` backend；
- optional `faiss` backend；
- `scripts/rebuild_memory_embeddings.py`；
- `scripts/probe_context_retrieval.py`；
- `scripts/run_memory_eval.py`；
- trace 中的 `semantic_score`、`score_breakdown`、backend/provider metadata。

当前验证基线：

```powershell
python -m unittest discover -s tests -v
```

当前结果：41 个测试通过。

## Architecture After Migration

```text
Player Input
-> Recent Context Load
-> Lore Retrieval
   -> lore_documents
   -> lore_embeddings
-> Memory Retrieval
   -> typed rule scoring
   -> semantic scoring
   -> hybrid fusion
-> State Load
-> Structured Decision
-> Tool Execution
-> Response Generation
-> Memory Job Enqueue
-> Trace Logging

Background Memory Job
-> Memory Policy
-> Memory Write
-> Embedding Update
```

## Retrieval Modes

| Mode | Purpose |
| --- | --- |
| `off` | 消融实验，不检索长期记忆 |
| `legacy` | 关键词/标签 baseline |
| `typed` | 规则可解释检索 |
| `semantic` | embedding similarity 检索 |
| `hybrid` | typed score + semantic score |

## Provider And Backend

默认稳定路径：

```text
AGENT_NPC_EMBEDDING_PROVIDER=mock_hash
AGENT_NPC_RETRIEVAL_BACKEND=sqlite_cosine
```

真实 provider 可选：

```text
AGENT_NPC_EMBEDDING_PROVIDER=openai_compatible
AGENT_NPC_EMBEDDING_MODEL=text-embedding-3-small
AGENT_NPC_EMBEDDING_ALLOW_FALLBACK=1
```

可选 backend：

```text
AGENT_NPC_RETRIEVAL_BACKEND=faiss
```

FAISS 或真实 provider 不可用时，系统保留 mock/SQLite fallback，并在 trace/eval 中记录 fallback 原因。

## Evaluation

运行：

```powershell
python scripts/run_memory_eval.py
```

评测模式：

```text
no_long_term_memory
legacy_keyword_memory
typed_memory_policy
semantic_rag
hybrid_rag
```

输出：

```text
data/eval/memory_eval_report.json
data/eval/memory_eval_summary.md
```

报告重点是展示：

- legacy keyword 在开放表达上更容易漏检；
- semantic/hybrid 能处理隐含帮助、信任、偏好等表达；
- hybrid 保留 rule score 和 semantic score 的解释字段；
- real provider 缺失时标记 skipped，而不是破坏本地评测。

## Completed Phases

| Phase | Status | Result |
| --- | --- | --- |
| Phase 0 | Done | 保护 mock/typed 稳定基线 |
| Phase 1 | Done | embedding provider 和 `memory_embeddings` |
| Phase 2 | Done | `semantic` retrieval |
| Phase 3 | Done | `hybrid` retrieval |
| Phase 4 | Done | memory eval 扩展 |
| Phase 5 | Done | UI/trace 展示 score breakdown |
| Phase 6 | Ongoing | 文档和课程材料持续跟随代码更新 |

## Remaining Work

- 增加常驻后台 worker 或定时任务处理 memory jobs；
- 增加持久化 FAISS index 或外部向量库；
- 增加更多开放表达和跨 NPC 情景评测；
- 将当前自定义 workflow 迁移到 LangGraph 或显式节点图；
- 把 eval 结果整理进最终课程报告和 PPT。
