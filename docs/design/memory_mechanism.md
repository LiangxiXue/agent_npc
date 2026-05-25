# Current Memory Mechanism

本文档说明当前项目的记忆与上下文系统。当前版本不再是单 Lina 长期记忆表，而是四层上下文加后台长期记忆任务：

```text
recent_context      = 最近几轮短期对话
retrieved_memories  = 玩家/NPC 相关长期记忆
retrieved_lore      = 稳定世界设定和 NPC 设定
state_snapshot      = SQLite 当前事实
memory_jobs         = 后台长期记忆写入任务
```

## 1. 同步回合中的记忆路径

```text
玩家输入
-> 读取 recent_interactions
-> 检索 lore_documents
-> 检索 memories（off / legacy / typed / semantic / hybrid）
-> 读取 NPC / 玩家 / 任务状态
-> decision 层决定 intent、社交策略和工具
-> 程序状态机校验任务生命周期
-> 执行动作工具并更新 SQLite 状态
-> response 层生成 NPC 回复
-> enqueue memory_jobs
-> 写入本轮 recent_interactions
-> interaction_logs 记录完整 trace
```

关键点：实时玩家回合不再同步执行完整长期记忆写入。它只把本轮证据保存成 `memory_jobs`，让后台流程完成候选生成、审查、gate、写入和 embedding 更新。

## 2. 短期记忆

短期记忆保存在 `recent_interactions`：

```sql
CREATE TABLE IF NOT EXISTS recent_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

短期记忆用于话题连续性，不代表重要事实，也不会直接写入长期记忆表。

## 3. 稳定设定 Lore

稳定世界/NPC 背景保存在 `lore_documents`，向量索引保存在 `lore_embeddings`。

```text
data/lore/world_overview.md
data/lore/underground_ruins.md
data/lore/social_deduction_rules.md
data/lore/npc_lina.md
data/lore/npc_ron.md
data/lore/npc_mira.md
data/lore/npc_sable.md
```

Lore 与 memory 的边界：

- lore：稳定世界规则、NPC 背景、社交玩法规则；
- memory：玩家在交互中造成或表达的事件、关系、偏好、画像；
- state_snapshot：当前真相，例如任务状态、trust、背包、地点；
- recent_context：短期对话连续性。

## 4. 长期记忆

长期记忆保存在 `memories`：

```sql
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'episodic',
    importance INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    facets TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'npc_specific',
    evidence_text TEXT NOT NULL DEFAULT '',
    stability REAL NOT NULL DEFAULT 0.5,
    future_usefulness REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0
);
```

支持类型：

```text
semantic    = 稳定玩家事实、画像、玩家知识状态
episodic    = 发生过的具体事件
relational  = NPC 对玩家的关系变化或关系判断
procedural  = 后续应该如何与玩家互动
```

旧类型会自动迁移：`quest/event -> episodic`，`relationship -> relational`，`preference -> procedural`，`player_profile -> semantic`。

长期记忆按 NPC 隔离。Ron 的长期记忆不会污染 Lina；Sable 的可疑线索也不会变成全局事实，除非通过工具写入 `world_events`。

## 5. Embedding Index

长期记忆索引保存在 `memory_embeddings`：

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

`source_text_hash` 让系统能在 memory 内容、tags、facets、scope、provider 或 model 变化时刷新索引。

默认 provider 是 `mock_hash`，不需要 API key。真实 provider 可通过 OpenAI-compatible `/embeddings` 接入。

## 6. Background Memory Jobs

`memory_jobs` 保存后台长期记忆处理所需的完整证据：

```text
npc_id
player_input
npc_response
recent_context
retrieved_lore
retrieved_memories
state_before
state_after
tool_calls
state_changes
status
memory_policy
memory_writes
embedding_updates
error
```

处理命令：

```powershell
python scripts/process_memory_jobs.py --limit 10
```

常驻 worker：

```powershell
python scripts/memory_worker.py --limit 5
```

状态含义：

| Status | Meaning |
| --- | --- |
| `pending` | 已入队，等待后台处理 |
| `written` | 已处理，没有需要索引的新长期记忆 |
| `indexed` | 已写入长期记忆并更新 embedding |
| `failed` | 后台处理失败，`error` 字段保存原因 |

## 7. Memory Policy

后台处理时，`src/agent/memory_jobs.py` 会重建 `MemoryPolicyInput` 并调用 `src/agent/memory_policy.py`。

当前写入链路：

```text
LLM memory candidate generator
-> optional LLM memory review agent
-> programmatic gate
-> deduplication
-> SQLite write
-> embedding update
```

硬 gate 检查：

| Check | Purpose |
| --- | --- |
| allowed type | 只允许 `semantic`、`episodic`、`relational`、`procedural` |
| evidence | 候选必须引用本轮输入、回复、工具或状态变化中的证据 |
| tool/state support | episodic 和 relational 记忆需要工具或状态变化支撑 |
| player-grounded | semantic 和 procedural 玩家记忆必须来自玩家自述 |
| lore boundary | 稳定世界设定应进入 `lore_documents`，不能误写成玩家 memory |
| dedup | 防止同 NPC、同类型、相似内容重复写入 |

## 8. Retrieval Modes

长期记忆检索入口仍是 `database.search_memories(...)`，支持：

| Mode | Behavior |
| --- | --- |
| `off` | 不检索长期记忆，用作消融实验 |
| `legacy` | 旧版关键词/标签检索 |
| `typed` | 关键词、标签、记忆类型、重要性、可信度、新近度评分 |
| `semantic` | embedding similarity 检索 |
| `hybrid` | typed rule score + semantic score |

返回字段包括：

```text
retrieval_score
rule_score
semantic_score
matched_keywords
matched_tags
retrieval_reason
semantic_reason
score_breakdown
retrieval_backend
backend_fallback_reason
query_embedding_latency_ms
```

## 9. Trace 中的记忆信息

每轮 trace 可以解释：

- 本轮用了哪些 recent context；
- 检索到了哪些 lore；
- 检索到了哪些长期记忆；
- 每条 memory 为什么被选中；
- 本轮是否 enqueue 了 memory job；
- 后台处理后写入了哪些长期记忆；
- 重大状态变化来自哪个工具调用。

## 10. 当前能力边界

已经实现：

- 短期 / 长期 / lore / state 分层；
- 多 NPC 记忆隔离；
- LLM 友好的类型化长期记忆：`semantic`、`episodic`、`relational`、`procedural`；
- 后台 memory job；
- 常驻后台 memory worker；
- rule + semantic + hybrid retrieval；
- provider/backend-aware embedding layer；
- LLM candidate/review + programmatic gate；
- trace 展示 memory policy、memory job 状态和 retrieval scores。

尚未实现：

- worker 并发锁、失败重试和运行监控；
- 复杂遗忘机制；
- NPC 间自动记忆传播；
- 大规模外部向量库；
- LangGraph 编排。
