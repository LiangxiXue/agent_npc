# Production Retrieval Layer v1

当前检索层目标是让 Hybrid RAG 既能稳定演示，又具备真实 provider 和向量 backend 的工程扩展点。

## Provider

`src/agent/embedding_client.py` 暴露统一 embedding 接口：

- `mock_hash`：默认 provider，确定性、本地运行、适合测试和无网演示。
- `openai_compatible`：调用兼容 `/embeddings` 的真实服务。

真实 provider 失败或未配置时，如果 `AGENT_NPC_EMBEDDING_ALLOW_FALLBACK=1`，系统会回退到 `mock_hash`，并在检索结果中记录 fallback 原因。

## Environment Variables

```text
AGENT_NPC_EMBEDDING_PROVIDER=mock_hash
AGENT_NPC_EMBEDDING_API_KEY=
AGENT_NPC_EMBEDDING_MODEL=text-embedding-3-small
AGENT_NPC_EMBEDDING_BASE_URL=https://api.openai.com/v1
AGENT_NPC_EMBEDDING_TIMEOUT=30
AGENT_NPC_EMBEDDING_ALLOW_FALLBACK=1
AGENT_NPC_RETRIEVAL_BACKEND=sqlite_cosine
```

If embedding-specific key/base URL are empty, the OpenAI-compatible embedding client can reuse the LLM API key/base URL. The selected embedding model still needs to be an embedding model supported by the provider's `/embeddings` endpoint.

## Cache

`memory_embeddings` and `lore_embeddings` record:

- `embedding_provider`
- `embedding_model`
- `embedding_dim`
- `source_text_hash`

When content, tags, provider, or model changes, the index refreshes. Otherwise the existing embedding is reused.

## Backend

`AGENT_NPC_RETRIEVAL_BACKEND` controls semantic retrieval:

- `sqlite_cosine`：default backend, computes cosine similarity from JSON vectors stored in SQLite.
- `faiss`：optional backend, builds a FAISS inner-product index at runtime; if FAISS or NumPy is unavailable, falls back to `sqlite_cosine`.

Result metadata includes:

```text
retrieval_backend
requested_retrieval_backend
backend_fallback_reason
embedding_provider
query_embedding_provider
query_embedding_latency_ms
```

## Operational Commands

Rebuild memory embeddings:

```powershell
python scripts/rebuild_memory_embeddings.py
```

Probe context retrieval:

```powershell
python scripts/probe_context_retrieval.py
```

Run evaluation:

```powershell
python scripts/run_memory_eval.py
```

## Eval

`scripts/run_memory_eval.py` keeps the five memory modes and includes `Retrieval Layer Comparison`:

```text
mock_sqlite_hybrid
mock_faiss_hybrid
real_sqlite_hybrid
real_faiss_hybrid
```

Real-provider rows are skipped when credentials or endpoint support are missing. This lets local tests remain stable while still documenting the upgrade path.
