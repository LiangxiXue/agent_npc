# Production Retrieval Layer v1

当前检索层的目标是让 Hybrid RAG 既能稳定演示，又具备真实 provider 和向量 backend 的工程扩展点。

## Provider

`src/agent/embedding_client.py` 暴露统一 embedding 接口：

- `mock_hash`：默认 provider，确定性、本地运行、适合测试和无网演示。
- `openai_compatible`：调用兼容 `/embeddings` 的真实服务。

真实 provider 失败或未配置时，如果 `AGENT_NPC_EMBEDDING_ALLOW_FALLBACK=1`，系统会回退到 `mock_hash`，并在检索结果中记录 `query_embedding_fallback_reason`。

## Cache

`memory_embeddings` 不只按 `memory_id` 缓存，还记录：

- `embedding_provider`
- `embedding_model`
- `embedding_dim`
- `source_text_hash`

因此当 memory 内容、tags、provider 或 model 改变时，索引会自动刷新；没有变化时不会重复生成 embedding。

## Backend

语义检索 backend 由 `AGENT_NPC_RETRIEVAL_BACKEND` 控制：

- `sqlite_cosine`：默认 backend，从 SQLite 读取 JSON 向量并计算 cosine similarity。
- `faiss`：可选 backend，运行时构建 FAISS inner-product index；如果 FAISS 或 NumPy 不可用，自动回退到 `sqlite_cosine`。

检索结果会带上：

- `retrieval_backend`
- `requested_retrieval_backend`
- `backend_fallback_reason`
- `embedding_provider`
- `query_embedding_provider`
- `query_embedding_latency_ms`

## Eval

`python scripts/run_memory_eval.py` 仍保留原有五种记忆模式对比，并新增 `Retrieval Layer Comparison`：

- `mock_sqlite_hybrid`
- `mock_faiss_hybrid`
- `real_sqlite_hybrid`
- `real_faiss_hybrid`

真实 provider 未配置时会标记 `skipped`，不会破坏本地评测。
