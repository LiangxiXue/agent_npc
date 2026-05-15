# 当前 NPC 记忆机制说明

本文档说明当前项目中 Lina 的记忆系统。当前版本已经从“单一长期记忆表”升级为：

```text
短期上下文 recent_interactions
+ 类型化长期记忆 memories
+ 记忆向量索引 memory_embeddings
+ 独立 Memory Policy
+ 可解释规则/语义检索分数和写入原因
```

## 1. 总体流程

每轮交互的记忆相关流程是：

```text
玩家输入
-> 读取最近几轮短期交互
-> 检索长期记忆（typed / semantic / hybrid）
-> 读取 NPC / 玩家 / 任务状态
-> decision 层决定当前行为工具
-> 执行动作工具并更新 SQLite 状态
-> response 层生成 NPC 回复
-> memory_policy 判断是否写入长期记忆
-> 写入本轮短期交互
-> interaction log 记录完整 trace
```

关键点：`decision.py` 不再直接决定长期记忆写入。长期记忆统一由 `src/agent/memory_policy.py` 串联候选生成、审查、硬校验、去重和写入，避免普通闲聊或重复事件污染长期记忆。

## 2. 短期记忆

短期记忆保存在 `recent_interactions` 表：

```sql
CREATE TABLE IF NOT EXISTS recent_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);
```

它保存最近几轮原始对话，用来帮助 NPC 理解当前话题连续性。短期记忆不代表“重要事实”，也不会直接进入长期记忆表。

相关函数：

```text
database.add_recent_interaction()
database.get_recent_interactions()
```

## 3. 长期记忆

长期记忆保存在 `memories` 表：

```sql
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'event',
    importance INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);
```

长期记忆字段含义：

| 字段 | 含义 |
| --- | --- |
| `content` | 记忆正文 |
| `memory_type` | 记忆类型，例如 `event`、`quest`、`relationship`、`preference` |
| `importance` | 重要性，1-10 |
| `confidence` | 可信度，0-1 |
| `tags` | 可检索标签 |
| `last_accessed_at` | 最近一次被检索时间 |
| `access_count` | 被检索次数 |

旧数据库会在初始化时自动补齐新字段，不需要手动删库。

## 4. 记忆向量索引

语义检索使用单独的 `memory_embeddings` 表，不把向量直接塞进 `memories`：

```sql
CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id INTEGER PRIMARY KEY,
    embedding TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES memories (id) ON DELETE CASCADE
);
```

当前默认 embedding provider 是 `mock_hash`，用确定性特征和 hash 向量实现，不需要 API key。写入长期记忆后，workflow 会调用 `ensure_embeddings_for_memory_writes()` 为新记忆补索引；已有记忆可通过 `python scripts/rebuild_memory_embeddings.py` 重建索引。

## 5. Memory Policy

`src/agent/memory_policy.py` 负责判断“本轮是否值得写入长期记忆”。

输入包括：

```text
npc_id
player_input
npc_response
retrieved_long_term_memories
recent_short_term_context
npc_before / npc_after
player_before / player_after
quest_before / quest_after
tool_calls
state_changes
```

当前写入链路：

```text
rule candidates
-> LLM memory candidate generator
-> LLM memory review agent
-> programmatic gate
-> deduplication
-> SQLite write
-> embedding update
```

`src/agent/llm_memory_candidate.py` 和 `src/agent/memory_candidate_review.py` 都通过 `src/agent/llm_client.py` 使用同一套 `.env` OpenAI-compatible API 配置。它们只生成和审查候选，不直接写 SQLite。

`src/agent/memory_candidate_gate.py` 做不可绕过的硬校验：

| 校验 | 说明 |
| --- | --- |
| allowed type | 只允许 `quest`、`event`、`relationship`、`preference`、`player_profile` |
| evidence | LLM 候选必须引用本轮输入、回复、工具或状态变化中的证据 |
| tool/state support | `event`、`quest`、`relationship` 必须有工具调用或状态变化支撑 |
| player-grounded | `player_profile`、`preference` 必须来自玩家自述 |
| dedup | 写入前仍会检查相似记忆 |

输出会进入 trace：

```text
memory_policy:
  candidates:
    - should_write
    - content
    - memory_type
    - importance
    - tags
    - confidence
    - reason
    - evidence_text
    - source
    - gate
  llm_memory_policy
  summary
```

当前规则：

| 类型 | 触发条件 |
| --- | --- |
| `quest` | 任务状态从非 `completed` 变为 `completed` |
| `event` | 归还钥匙、解锁敏感地点等关键事件 |
| `relationship` | `trust` 或 `affection` 明显上升，且有玩家帮助 Lina 或其他可验证关系变化证据 |
| `preference` | 玩家明确表达稳定交流偏好 |
| `player_profile` | 玩家表达可长期参考的自我描述、处境或情绪需求，并通过 LLM 生成和审查 |
| 不写入 | 普通问候、普通闲聊、无长期意义或重复记忆 |

写入前会做基础去重：同 NPC、同类型、内容相同或核心标签高度重合的近期记忆不会重复写入。重复原因也会记录在 trace 中。

## 6. 长期记忆检索

长期记忆检索入口：

```text
database.search_memories(player_input, npc_id="lina")
```

支持模式：

| 模式 | 行为 |
| --- | --- |
| `off` | 不检索长期记忆，用作消融实验 |
| `legacy` | 旧版关键词/标签检索 |
| `typed` | 关键词、标签、记忆类型、重要性、可信度和新近度评分 |
| `semantic` | 只按 embedding similarity 检索，适合开放表达 |
| `hybrid` | 合并 typed rule score 和 semantic score |

返回结果会包含可解释字段：

```text
retrieval_score
rule_score
semantic_score
matched_keywords
matched_tags
retrieval_reason
semantic_reason
score_breakdown
```

评分由以下部分组成：

```text
keyword_score
+ tag_score
+ type_bonus
+ importance_bonus
+ recency_bonus
+ confidence_bonus
```

系统会先用规则推断本轮输入更关心哪些记忆类型。例如：

| 玩家输入 | 偏向记忆类型 |
| --- | --- |
| 任务、线索、遗迹、入口 | `quest`、`event`、`relationship` |
| 你还记得我吗、上次、信任 | `relationship`、`event` |
| 以后直接告诉我、不要绕弯 | `preference` |

被检索出的长期记忆会更新 `last_accessed_at` 和 `access_count`，为后续“记忆强化/遗忘”留下数据基础。

## 7. 记忆如何影响决策

workflow 会把两类上下文传给 `decide_next_action()`：

```text
recent_short_term_context
retrieved_long_term_memories
```

短期上下文用于理解当前话题；长期记忆用于判断历史行为、关系、任务和偏好。

例如：

```text
第 1 轮：玩家归还钥匙
-> 工具更新 trust、affection、quest、reward
-> memory_policy 写入 quest / event / relationship 长期记忆

第 2 轮：玩家询问遗迹入口
-> search_memories 检索到 lost_key / trust 相关长期记忆
-> decision 判断玩家可信
-> Lina 透露地下遗迹入口
```

## 8. Trace 中新增的记忆信息

每轮 interaction log 现在包含：

| 字段 | 含义 |
| --- | --- |
| `recent_context` | 本轮使用的短期上下文 |
| `retrieved_memories` | 本轮检索到的长期记忆及规则/语义检索解释 |
| `memory_policy` | 本轮是否应该写长期记忆及原因 |
| `memory_writes` | 实际写入的长期记忆 |
| `tool_calls` | 行为工具调用，不再混入长期记忆判断 |
| `state_changes` | 行为工具造成的状态变化 |

因此 trace 可以解释：

```text
Lina 为什么接着上一轮话题说？
本轮检索到了哪些长期记忆？
这些长期记忆为什么被选中？
本轮为什么写入或不写入长期记忆？
```

## 9. 当前能力边界

已经实现：

- 短期 / 长期记忆分层；
- 长期记忆类型化；
- 规则版 Memory Policy；
- 长期记忆去重；
- 可解释检索分数；
- deterministic semantic retrieval；
- hybrid retrieval；
- 访问统计；
- trace 展示 memory policy 和 memory writes。

尚未实现：

- 外部 embedding API 的课堂默认路径；
- 大模型自动总结；
- 复杂遗忘机制；
- 多 NPC 记忆传播；
- 复杂情绪模型。
