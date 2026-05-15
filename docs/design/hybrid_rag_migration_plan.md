# Hybrid RAG 改造计划书

## 1. 目标

当前项目已经实现了一个可解释的规则型 NPC 记忆系统：

```text
短期上下文 recent_interactions
+ 类型化长期记忆 memories
+ Memory Policy
+ 规则关键词检索
+ memory_type / importance / confidence / recency 综合评分
+ trace 导出
```

下一阶段目标不是推翻现有系统，而是把当前规则检索升级为 **Hybrid RAG for NPC Memory**：

```text
规则检索
+ 语义向量检索
+ 类型化记忆权重
+ Memory Policy
+ 可解释 trace
```

最终目标是让 NPC 不只能够处理预设关键词，例如“钥匙、遗迹、入口”，还能够处理更自然、含蓄或预设外的表达，例如：

```text
我之前替你解决过那个麻烦
上次那件事之后，你愿意相信我了吗
你还记得我帮过你吗
以后别跟我绕弯子
```

## 2. 当前系统边界

当前默认检索模式是：

```text
mode = "typed"
```

当前流程：

```text
Player Input
-> get_recent_interactions()
-> search_memories(mode="typed")
-> decide_next_action()
-> execute_tools()
-> generate_npc_response()
-> apply_memory_policy()
-> add_recent_interaction()
-> log_interaction()
```

当前长期记忆检索依赖：

```text
extract_memory_keywords()
infer_memory_query_types()
score_memory_for_query()
```

当前评分：

```text
retrieval_score =
  keyword_score
+ tag_score
+ type_bonus
+ importance_bonus
+ confidence_bonus
+ recency_bonus
```

当前不足：

- 预设外同义表达容易漏检；
- 隐含指代不稳定；
- 复杂偏好表达识别弱；
- 长文本记忆和自然语言相似度无法处理；
- 评测里 `legacy_keyword_memory` 和 `typed_memory_policy` 都能过当前场景，说明还缺少能拉开差距的开放表达测试。

## 3. 目标架构

计划改造后的架构：

```text
Player Input
-> Short-Term Context Load
-> Query Understanding
   -> rule keywords
   -> memory query types
   -> optional semantic query text
-> Hybrid Retrieval
   -> rule retrieval
   -> semantic retrieval
-> Score Fusion / Reranking
   -> rule_score
   -> semantic_score
   -> type_bonus
   -> importance_bonus
   -> confidence_bonus
   -> recency_bonus
-> Retrieved Memory Pack
-> Agent Decision
-> Tool Execution
-> Response Generation
-> Memory Policy
-> Embedding Update for New Memories
-> Trace Logging
```

核心原则：

```text
LLM / embedding 只增强检索，不直接拥有状态写入权；
Memory Policy 继续拥有长期记忆写入权；
SQLite 继续是状态和 trace 的 source of truth；
mock 模式必须继续可运行；
报告级 demo 仍应可用稳定 mock 路径复现。
```

## 4. 数据结构改造

### 4.1 推荐新增表

建议新增单独表，而不是直接把 embedding 塞进 `memories` 表：

```sql
CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id INTEGER PRIMARY KEY,
    embedding TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES memories (id)
);
```

理由：

- `memories` 继续保持可读；
- embedding 可以独立重建；
- 后续切换模型时不会破坏原始记忆；
- JSON 文本存储向量对当前 SQLite MVP 足够。

### 4.2 可选新增字段

如需支持 embedding 重建状态，也可以给 `memories` 增加：

```text
embedding_status TEXT DEFAULT 'pending'
```

但第一版可以不加，直接通过 `memory_embeddings` 是否存在对应行判断。

## 5. 模块设计

### 5.1 新增 `src/agent/embedding_client.py`

职责：

```text
提供统一 embedding 接口；
支持 mock/local/openai_compatible 三种路径；
保证无 API key 时项目仍可运行。
```

建议接口：

```python
def embed_text(text: str) -> list[float]:
    ...

def get_embedding_settings() -> dict:
    ...
```

推荐先实现两种模式：

```text
mock_hash
openai_compatible
```

`mock_hash` 用确定性 hash / bag-of-words 向量，保证测试稳定。

### 5.2 新增 `src/agent/semantic_retrieval.py`

职责：

```text
生成 query embedding；
读取 memory_embeddings；
计算 cosine similarity；
返回 semantic candidates。
```

建议接口：

```python
def semantic_search_memories(
    player_input: str,
    npc_id: str = "lina",
    limit: int = 10,
) -> list[dict]:
    ...
```

返回字段：

```text
memory_id
semantic_score
semantic_reason
embedding_model
```

### 5.3 修改 `src/storage/database.py`

新增：

```python
def upsert_memory_embedding(memory_id: int, embedding: list[float], model: str) -> None
def get_memory_embeddings(npc_id: str) -> list[dict]
def get_memories_without_embeddings(npc_id: str = "lina") -> list[dict]
```

改造：

```python
search_memories(..., mode="typed" | "legacy" | "off" | "semantic" | "hybrid")
```

### 5.4 修改 `src/agent/memory_policy.py`

当 Memory Policy 写入新的长期记忆后，需要触发 embedding 写入。

建议不要让 `memory_policy.py` 直接调用 embedding API，而是在 workflow 中做：

```text
memory_policy writes memory
-> workflow calls ensure_embeddings_for_memory_writes()
```

这样职责更清楚：

```text
memory_policy.py: 决定写什么记忆
embedding_client.py: 怎么向量化
workflow.py: 串联写入后的索引更新
```

### 5.5 新增 `src/agent/query_understanding.py`

第一版可以把现有：

```python
extract_memory_keywords()
infer_memory_query_types()
```

从 `database.py` 挪到该模块，形成更清楚的边界。

后续可加入 LLM query rewrite：

```python
def build_memory_query(player_input: str, recent_context: list[dict]) -> dict:
    return {
        "keywords": [...],
        "query_types": [...],
        "semantic_query": "...",
        "reason": "..."
    }
```

第一阶段不必立刻启用 LLM rewrite。

## 6. Hybrid Scoring 设计

### 6.1 当前 typed rule score

保留当前规则分：

```text
rule_score =
  keyword_score
+ tag_score
+ type_bonus
+ importance_bonus
+ confidence_bonus
+ recency_bonus
```

### 6.2 新增 semantic score

向量相似度：

```text
cosine_similarity(query_embedding, memory_embedding)
```

映射到分数：

```text
semantic_score = max(cosine_similarity, 0) * 10
```

### 6.3 Hybrid final score

建议第一版：

```text
final_score =
  rule_score
+ semantic_score
+ type_bonus
+ importance_bonus
+ confidence_bonus
+ recency_bonus
```

注意：如果 `rule_score` 已经包含 type / importance / confidence / recency，则不要重复加。更稳妥的实现是拆成组件：

```text
final_score =
  keyword_score
+ tag_score
+ semantic_score
+ type_bonus
+ importance_bonus
+ confidence_bonus
+ recency_bonus
```

返回 trace 字段：

```text
retrieval_score
rule_score
semantic_score
matched_keywords
matched_tags
matched_types
retrieval_reason
semantic_reason
score_breakdown
```

## 7. 实施阶段

### Phase 0：保护当前状态

目标：

- 确认当前测试全部通过；
- 确认当前 eval 报告可再生成；
- 不改动现有功能语义。

命令：

```bash
python -m unittest discover -s tests -v
python scripts/run_memory_eval.py
python scripts/run_mvp_demo.py
python scripts/export_trace.py
```

### Phase 1：Embedding 基础设施

新增：

```text
src/agent/embedding_client.py
src/agent/semantic_retrieval.py
```

数据库：

```text
memory_embeddings 表
兼容 migration
```

实现：

- deterministic `mock_hash` embedding；
- cosine similarity；
- 为已有 memories 构建 embedding；
- 新增脚本 `scripts/rebuild_memory_embeddings.py`。

验证：

```bash
python scripts/rebuild_memory_embeddings.py
python -m unittest discover -s tests -v
```

### Phase 2：Semantic Retrieval 模式

目标：

```text
search_memories(mode="semantic")
```

行为：

- 不使用关键词命中作为硬条件；
- 根据 query embedding 找 top-k；
- 返回 `semantic_score` 和 `semantic_reason`；
- trace 中展示语义检索结果。

新增测试：

```text
输入：我之前替你解决过那个麻烦
预期：能够检索到 Player returned Lina's lost key.
```

### Phase 3：Hybrid Retrieval 模式

目标：

```text
search_memories(mode="hybrid")
```

行为：

- 同时跑 typed rule retrieval 和 semantic retrieval；
- 按 memory_id 合并候选；
- 计算统一 `final_score`；
- 返回 top-k；
- trace 展示 score breakdown。

默认模式建议先保持：

```text
typed
```

等评测通过后再切到：

```text
hybrid
```

### Phase 4：评测扩展

修改：

```text
scripts/run_memory_eval.py
```

新增 variants：

```text
semantic_rag
hybrid_rag
```

现有 variants 保留：

```text
no_long_term_memory
legacy_keyword_memory
typed_memory_policy
```

新增泛化场景：

```text
implicit_help_reference:
  我之前替你解决过那个麻烦，现在能告诉我入口吗？

indirect_trust_reference:
  上次那件事之后，你应该更愿意相信我了吧？

preference_paraphrase:
  我不太喜欢你每次都神神秘秘的，有线索就直说吧。

memory_without_exact_keywords:
  那个小铜片的事我已经处理好了。
```

目标不是让所有模式都通过，而是让报告体现差异：

```text
legacy_keyword_memory 在开放表达上失败；
typed_memory_policy 部分成功；
semantic_rag / hybrid_rag 在同义表达上更稳；
hybrid_rag 保留规则检索的可解释性。
```

### Phase 5：UI 与 Trace 展示

更新 `app.py`：

```text
Retrieved Long-Term Memories
  - retrieval_score
  - rule_score
  - semantic_score
  - score_breakdown
  - retrieval_reason
```

更新 `trace_export.py`：

```text
导出 embedding settings
导出 retrieval mode
导出 score breakdown
```

### Phase 6：文档与报告材料

更新：

```text
README.md
docs/design/memory_mechanism.md
docs/evaluation/test_plan.md
docs/design/architecture.md
docs/delivery/report_outline.md
```

新增：

```text
docs/design/hybrid_rag_design.md
```

报告重点：

```text
当前项目不是普通聊天机器人；
它是 Memory-RAG NPC Agent；
RAG 检索结果影响 decision 和 tool execution；
Memory Policy 决定长期记忆写入；
trace 可以解释每轮为什么检索、为什么行动、为什么写入记忆。
```

## 8. 评测指标

建议报告中使用以下指标：

| 指标 | 含义 |
| --- | --- |
| `scenario_pass_rate` | 每种模式通过多少场景 |
| `retrieval_success_rate` | 是否检索到目标记忆 |
| `decision_success_rate` | 检索后是否触发正确 intent |
| `false_long_term_write_count` | 普通闲聊是否误写长期记忆 |
| `duplicate_write_count` | 重复事件是否被去重 |
| `explainability_coverage` | 返回结果是否包含 retrieval_reason / score_breakdown |

## 9. 风险与边界

### 9.1 不要让 embedding 破坏稳定演示

必须保留：

```text
mock mode
typed mode
scripts/run_mvp_demo.py
```

### 9.2 不要把 RAG 做成普通文档问答

本项目 RAG 的检索对象是：

```text
NPC long-term memories
```

不是课程 PDF、网页知识库或百科问答。

### 9.3 不要让 LLM 直接写状态

继续保持：

```text
state_before/state_after 由 SQLite/workflow 生成；
tool execution 修改状态；
Memory Policy 写长期记忆；
LLM 只参与 decision / response polish / optional query rewrite。
```

### 9.4 不要一开始就依赖外部 API

第一版 semantic retrieval 应先用 deterministic mock embedding，保证：

```text
测试稳定
课堂演示稳定
无 API key 也能运行
```

之后再加 OpenAI-compatible embedding。

## 10. 推荐下一轮对话执行提示词

可以在新对话中直接使用：

```text
请阅读 docs/design/hybrid_rag_migration_plan.md、docs/design/memory_mechanism.md、src/agent/workflow.py、src/storage/database.py、src/agent/memory_policy.py、scripts/run_memory_eval.py。

目标：按计划将当前 typed memory retrieval 升级为 Hybrid RAG。请从 Phase 0 开始，先验证当前测试和评测，再实现 Phase 1 和 Phase 2。不要破坏当前 demo，不要删除 mock/typed 模式，不要让 LLM 或 embedding 直接拥有状态写入权。
```

## 11. 完成标准

第一轮 Hybrid RAG 改造完成后，应满足：

```text
python -m unittest discover -s tests -v
python scripts/run_memory_eval.py
python scripts/run_mvp_demo.py
python scripts/export_trace.py
```

并且：

- 原有 15 个测试继续通过；
- eval 报告新增 `semantic_rag` 和 `hybrid_rag`；
- 至少 2 个开放表达场景中，hybrid 模式优于 legacy 关键词模式；
- trace 中能看到 semantic_score 和 score_breakdown；
- 无 API key 时仍可运行。
