# 任务：改进当前 NPC 记忆系统，重点实现 Memory Policy、记忆类型化、短期/长期记忆分层

你现在要改进当前项目中的 NPC 记忆机制。请先完整阅读项目代码，尤其关注以下文件或相关模块：

- `src/agent/workflow.py`
- `src/agent/decision.py`
- `src/storage/database.py`
- `src/storage/schema.sql`
- `src/tools/sqlite_tools.py`
- 当前和 trace / interaction log / web 展示相关的代码

当前系统已经实现了一个基于 SQLite 的轻量长期记忆机制：

```text
玩家输入
-> 检索 memories 表中的相关记忆
-> 读取 NPC / 玩家 / 任务状态
-> 交给 decision 层决策
-> decision 层决定是否调用 add_memory 工具
-> add_memory 写入 SQLite
-> trace 记录检索记忆、工具调用和状态变化
```

现在请在不破坏现有功能的前提下，对记忆系统进行结构化升级。目标不是简单增加功能，而是让 NPC 的记忆机制更稳定、更可解释、更接近一个真正 Agent 的 memory architecture。

---

## 总体目标

请完成三个方向的改进：

1. **提升记忆写入质量**
   - 增加独立的 `memory_policy` 模块
   - 让系统显式判断“什么值得记忆”
   - 记录为什么写入或不写入记忆

2. **实现记忆类型化**
   - 给长期记忆增加 `memory_type`
   - 区分事件记忆、关系记忆、任务记忆、偏好记忆等类型
   - 让检索和决策可以利用记忆类型

3. **实现短期记忆 / 长期记忆分层**
   - 短期记忆保存最近几轮交互
   - 长期记忆保存真正重要、可持续影响后续决策的内容
   - workflow 中同时向 decision 层传入短期上下文和长期记忆

---

# 第一部分：增加 Memory Policy 模块

## 1.1 新增模块

请新增：

```text
src/agent/memory_policy.py
```

该模块负责判断本轮交互是否应该写入长期记忆。

不要把记忆写入规则散落在 `decision.py` 或 `workflow.py` 中。
`decision.py` 可以继续负责 NPC 当前如何回应，但“是否形成长期记忆”应该交给 `memory_policy.py`。

---

## 1.2 Memory Policy 的输入

请设计一个清晰的数据结构，让 `memory_policy` 能获得以下信息：

```text
- npc_id
- player_input
- npc_response
- retrieved_long_term_memories
- recent_short_term_context
- npc_before
- npc_after
- player_before
- player_after
- quest_before
- quest_after
- tool_calls
- state_changes
```

如果当前代码中还没有全部变量，可以根据现有结构做合理适配。
重点是让 memory policy 能基于“本轮发生了什么变化”来判断是否需要写入长期记忆。

---

## 1.3 Memory Policy 的输出

请定义类似下面的数据结构：

```python
from dataclasses import dataclass

@dataclass
class MemoryCandidate:
    should_write: bool
    npc_id: str
    content: str
    memory_type: str
    importance: int
    tags: list[str]
    confidence: float
    reason: str
```

其中：

| 字段 | 含义 |
|---|---|
| `should_write` | 是否应该写入长期记忆 |
| `npc_id` | 记忆属于哪个 NPC |
| `content` | 记忆正文 |
| `memory_type` | 记忆类型 |
| `importance` | 重要性，建议 1-10 |
| `tags` | 标签列表 |
| `confidence` | 可信度，建议 0-1 |
| `reason` | 为什么写入或不写入 |

注意：即使不写入，也应该在 trace 中保留 reason，这样后续可以解释系统为什么没有记忆某件事。

---

## 1.4 记忆写入规则

请先使用规则系统实现，不要依赖外部 LLM 或 embedding API。

至少实现以下规则：

### A. 任务完成类记忆

如果某个 quest 的状态从非 completed 变成 completed，则写入一条长期记忆。

示例：

```text
Player completed the lost_key quest for Lina.
```

建议：

```text
memory_type = "quest"
importance = 8 或 9
tags = ["quest", "completed", quest_id]
```

---

### B. 关键事件类记忆

如果玩家完成了对 NPC 有明确影响的行为，例如归还钥匙、帮助 NPC、解锁地点、获得重要道具，则写入事件记忆。

示例：

```text
Player returned Lina's lost key.
```

建议：

```text
memory_type = "event"
importance = 7 或 8
tags = ["event", "help", "lost_key"]
```

---

### C. 关系变化类记忆

如果 NPC 的 trust / affinity / relationship 等关系数值发生明显变化，则写入关系记忆。

例如 trust 增加超过某个阈值：

```text
Lina trusts the player more because the player helped her.
```

建议：

```text
memory_type = "relationship"
importance = 7 或 8
tags = ["relationship", "trust"]
```

---

### D. 玩家偏好类记忆

如果玩家明确表达稳定偏好，则写入偏好记忆。

例如：

```text
玩家说：“以后直接告诉我线索，不要绕弯子。”
```

可以写入：

```text
Player prefers direct hints instead of vague clues.
```

建议：

```text
memory_type = "preference"
importance = 5 或 6
tags = ["preference", "communication_style"]
```

注意：不要把普通闲聊、临时情绪、无长期意义的信息写入长期记忆。

---

### E. 不写入规则

以下情况默认不写入长期记忆：

```text
- 普通问候
- 普通闲聊
- 玩家只是询问系统机制
- 玩家只是重复之前已经记过的事情
- 没有状态变化、没有关系变化、没有任务进展的普通对话
```

但是需要在 trace 中记录：

```text
should_write = false
reason = "No long-term significant event detected."
```

---

## 1.5 去重检查

在写入长期记忆前，请增加基础去重逻辑。

规则可以简单一些：

```text
- 如果已有记忆 content 完全相同，不重复写入
- 如果已有记忆 tags 高度重合，并且 memory_type 相同，并且内容非常接近，则不重复写入
```

可以先用简单字符串规则，不需要复杂语义模型。

如果因为重复而不写入，请在 trace 中记录：

```text
should_write = false
reason = "Similar memory already exists."
```

---

# 第二部分：实现记忆类型化

## 2.1 修改数据库 schema

请修改 `src/storage/schema.sql`，让 `memories` 表支持更多字段。

建议目标结构类似：

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

如果项目中已经存在数据库文件，请同时考虑迁移逻辑。
不要因为表结构变化导致已有数据库直接崩溃。

可以在 `database.py` 初始化时做兼容性检查，例如：

```text
- 如果 memories 表缺少 memory_type，则 ALTER TABLE 添加
- 如果缺少 confidence，则 ALTER TABLE 添加
- 如果缺少 last_accessed_at，则 ALTER TABLE 添加
- 如果缺少 access_count，则 ALTER TABLE 添加
```

---

## 2.2 修改 add_memory 接口

请更新：

```text
src/tools/sqlite_tools.py
src/storage/database.py
```

让 `add_memory` 支持：

```python
add_memory(
    npc_id: str,
    content: str,
    importance: int,
    tags: list[str],
    memory_type: str = "event",
    confidence: float = 1.0,
)
```

并确保旧代码如果没有传入 `memory_type`，仍然可以正常运行。

---

## 2.3 修改 search_memories 返回结果

`search_memories()` 返回的每条记忆应包含：

```text
id
npc_id
content
memory_type
importance
confidence
tags
created_at
last_accessed_at
access_count
retrieval_score
matched_keywords
matched_tags
retrieval_reason
```

其中：

| 字段 | 说明 |
|---|---|
| `retrieval_score` | 当前检索分数 |
| `matched_keywords` | 命中的关键词 |
| `matched_tags` | 命中的标签 |
| `retrieval_reason` | 为什么这条记忆被选中 |

这会提升 trace 的可解释性。

---

## 2.4 改进检索评分

当前系统主要按关键词命中数、importance、id 排序。请改成更清晰的综合评分。

建议评分结构：

```text
retrieval_score =
keyword_score
+ tag_score
+ type_bonus
+ importance_bonus
+ recency_bonus
+ confidence_bonus
```

建议初始规则：

```text
keyword_score = 命中关键词数量 * 2.0
tag_score = 命中 tag 数量 * 2.5
importance_bonus = importance * 0.3
confidence_bonus = confidence * 1.0
recency_bonus = 较新的记忆小幅加分
type_bonus = 根据当前输入意图动态加分
```

---

## 2.5 根据输入意图给 memory_type 加权

请实现一个轻量的输入意图判断函数，例如：

```python
def infer_memory_query_intent(player_input: str) -> set[str]:
    ...
```

返回可能相关的记忆类型。

例如：

```text
玩家问任务 / 线索 / 遗迹 / 地点：
优先 quest, event, relationship

玩家问“你还记得我吗 / 我们之前怎么样”：
优先 relationship, event

玩家表达喜好：
优先 preference

普通对话：
不过度偏向长期记忆
```

这不需要复杂 NLP，先用关键词和规则即可。

---

## 2.6 更新访问统计

当某条记忆被检索出来并实际传给 decision 层时，请更新：

```text
last_accessed_at
access_count
```

这样后续可以支持记忆强化、遗忘和热度分析。

---

# 第三部分：实现短期记忆 / 长期记忆分层

## 3.1 新增短期交互表

请在 schema 中新增表，例如：

```sql
CREATE TABLE IF NOT EXISTS recent_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_input TEXT NOT NULL,
    npc_response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (npc_id) REFERENCES npcs (npc_id)
);
```

短期记忆用于保存最近几轮对话的原始上下文。
它不等同于长期记忆，不应该影响长期记忆表的纯度。

---

## 3.2 新增 database 方法

请在 `database.py` 中增加：

```python
def add_recent_interaction(
    npc_id: str,
    player_input: str,
    npc_response: str,
    metadata: dict | None = None,
) -> None:
    ...
```

以及：

```python
def get_recent_interactions(
    npc_id: str,
    limit: int = 5,
) -> list[dict]:
    ...
```

返回时按时间从旧到新排列，方便 decision 层理解上下文连续性。

---

## 3.3 workflow 中加入短期上下文

请修改 `src/agent/workflow.py`。

当前 workflow 大概是：

```text
玩家输入
-> search_memories()
-> get_npc()
-> get_player_state()
-> get_quest()
-> decide_next_action()
-> 执行工具
-> 记录 trace
```

请改成：

```text
玩家输入
-> get_recent_interactions()
-> search_memories()
-> get_npc()
-> get_player_state()
-> get_quest()
-> decide_next_action(
       player_input,
       recent_short_term_context,
       retrieved_long_term_memories,
       npc_state,
       player_state,
       quest_state
   )
-> 执行工具
-> memory_policy 判断是否写入长期记忆
-> 写入长期记忆
-> add_recent_interaction()
-> 记录 trace
```

注意：短期交互应该在本轮 NPC 回复生成后写入，因为需要保存 `npc_response`。

---

## 3.4 decision 层支持短期上下文

请修改 `decide_next_action()` 的输入，让它同时接收：

```text
recent_short_term_context
retrieved_long_term_memories
```

并在内部区分两者：

```text
短期上下文：用于理解当前多轮对话在聊什么
长期记忆：用于判断玩家历史行为、关系、任务进度、偏好
```

不要把二者混在一个 `memories` 参数里。

建议命名：

```python
def decide_next_action(
    player_input: str,
    npc_state: dict,
    player_state: dict,
    quest_state: dict,
    retrieved_long_term_memories: list[dict],
    recent_short_term_context: list[dict],
) -> Decision:
    ...
```

如果现有调用较多，可以做兼容层，但最终结构要清楚。

---

## 3.5 trace 中区分短期与长期记忆

请更新 interaction log / trace 结构。

trace 中应明确展示：

```text
Short-term context:
- 最近几轮 player_input / npc_response

Retrieved long-term memories:
- content
- memory_type
- importance
- retrieval_score
- retrieval_reason

Memory policy:
- should_write
- candidate memory
- reason

Memory writes:
- 是否实际写入
- 如果没有写入，原因是什么
```

这样页面上可以清楚解释：

```text
Lina 当前接着上一轮话题回答，是因为 short-term context；
Lina 愿意透露遗迹入口，是因为 long-term memory 里记录了玩家曾帮助过她。
```

---

# 第四部分：集成顺序建议

请按下面顺序改，不要一次性大改导致难以定位问题：

## Step 0：正式修改前先输出实现计划

在正式修改代码前，请先输出你的实现计划，包括：

```text
- 准备修改的文件
- 数据结构变化
- 函数签名变化
- workflow 调整方案
- trace 调整方案
- 测试方案
```

确认计划自洽后再开始改代码。不要删除现有功能，不要重写整个项目。

---

## Step 1：数据库 schema 兼容升级

完成：

```text
- memories 表增加 memory_type / confidence / last_accessed_at / access_count
- recent_interactions 表
- database 初始化兼容旧数据库
```

验证：

```text
- 旧数据库可以启动
- 新数据库可以初始化
- 原有 add_memory 不崩溃
```

---

## Step 2：更新 add_memory 和 search_memories

完成：

```text
- add_memory 支持 memory_type 和 confidence
- search_memories 返回更丰富字段
- 检索评分加入 keyword / tag / type / importance / confidence / recency
- 更新 access_count / last_accessed_at
```

验证：

```text
- 玩家提到钥匙时，lost_key 相关记忆仍能被检索到
- trace 中能看到 retrieval_score 和 retrieval_reason
```

---

## Step 3：新增 recent_interactions

完成：

```text
- add_recent_interaction()
- get_recent_interactions()
- workflow 每轮读取最近短期上下文
- 每轮结束后写入本轮短期交互
```

验证：

```text
- 连续多轮对话时，系统能读取最近几轮上下文
- 短期交互不会污染长期 memories 表
```

---

## Step 4：新增 memory_policy

完成：

```text
- src/agent/memory_policy.py
- MemoryCandidate 数据结构
- 任务完成、关键事件、关系变化、玩家偏好等规则
- 去重逻辑
- workflow 在工具执行和状态变化后调用 memory_policy
```

验证：

```text
- 完成 lost_key 任务时，会生成 quest/event 记忆
- trust 增加时，会生成 relationship 记忆
- 普通闲聊不会写入长期记忆
- 重复事件不会反复写入
```

---

## Step 5：更新 trace / web 展示

完成：

```text
- trace 区分 short-term context 和 long-term memories
- trace 显示 memory_policy 判断
- trace 显示为什么写入或不写入记忆
- trace 显示检索分数和命中原因
```

验证：

```text
- 页面或导出的 trace 能解释：
  1. 本轮 Lina 参考了哪些短期上下文
  2. Lina 检索到了哪些长期记忆
  3. 为什么这些长期记忆被选中
  4. 本轮有没有写入新长期记忆
  5. 如果没有写入，原因是什么
```

---

# 第五部分：质量要求

## 5.1 不要破坏现有 demo

当前 lost_key / underground ruins / trust 相关演示必须继续能跑。

如果原本逻辑是：

```text
玩家归还钥匙
-> Lina 增加信任
-> 写入记忆
-> 后续询问遗迹入口时能检索到相关记忆
-> Lina 透露入口
```

改进后这个链路仍然必须成立。

---

## 5.2 不要把所有对话都写入长期记忆

长期记忆必须保持“稀疏而重要”。

普通对话应该进入 `recent_interactions`，不应该进入 `memories`。

---

## 5.3 代码结构要清晰

请避免把所有逻辑写进 `workflow.py`。

建议职责划分：

```text
workflow.py
负责调度流程

decision.py
负责 NPC 当前行为决策

memory_policy.py
负责判断是否形成长期记忆

database.py
负责数据库读写和检索

sqlite_tools.py
负责工具封装

trace 相关模块
负责记录和展示过程
```

---

## 5.4 trace 必须可解释

这次升级的重点之一是可解释性。

请确保 trace 能回答：

```text
- 为什么检索到这条记忆？
- 为什么这条记忆影响了决策？
- 为什么本轮写入了新记忆？
- 为什么本轮没有写入长期记忆？
- 当前使用的是短期上下文还是长期记忆？
```

---

## 5.5 优先保证正确性和可维护性

不要为了炫技加入不必要的复杂机制。

暂时不要实现：

```text
- embedding
- vector database
- 多 NPC 记忆传播
- 复杂遗忘机制
- 大模型自动总结
- 复杂情绪模型
```

当前目标是先把基础 memory architecture 做扎实。

---

# 第六部分：最终交付要求

完成后请输出：

1. 修改了哪些文件
2. 新增了哪些数据表 / 字段
3. 旧数据库如何兼容
4. 新的记忆写入流程是什么
5. 新的记忆检索评分逻辑是什么
6. 短期记忆和长期记忆分别如何工作
7. trace 中新增了哪些字段
8. 如何运行和测试
9. 给出至少 3 个测试场景

测试场景至少包括：

```text
场景 1：玩家归还钥匙
预期：
- 写入 event 或 quest 类型长期记忆
- trust 增加
- trace 记录 memory_policy reason

场景 2：玩家后续询问遗迹入口
预期：
- 检索到 lost_key / trust 相关长期记忆
- Lina 判断玩家可信
- trace 显示 retrieval_score 和 retrieval_reason

场景 3：普通闲聊
预期：
- 写入 recent_interactions
- 不写入 long-term memories
- trace 显示 should_write = false 及原因
```

请在改动前先阅读现有代码结构，尽量保持原有风格。
如果发现当前代码结构和以上设计不完全一致，请基于现有项目做合理适配，但不要降低这三个核心目标：

```text
Memory Policy
Typed Long-term Memory
Short-term / Long-term Memory Separation
```
