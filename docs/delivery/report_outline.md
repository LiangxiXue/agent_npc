# Written Report Outline

报告主体建议控制在 15 页以内，重点写 Agent 系统和验证证据，不要把篇幅花在剧情复述。

## 1. 项目背景与问题定义

- 普通 LLM 角色缺少稳定状态和可验证行动；
- 文字冒险是可控实验环境；
- 项目目标：构建记忆驱动、状态驱动、工具可执行、可解释 trace 的角色 Agent。

## 2. 系统总体设计

建议图示：

```text
Player Input
-> Recent Context
-> Lore Retrieval
-> Long-Term Memory Retrieval
-> State Load
-> Structured Decision
-> Task State Machine
-> Tool Execution
-> Response Generation
-> Memory Job Enqueue
-> Trace Logging

Background Memory Job
-> LLM Candidate / Review
-> Programmatic Gate
-> Memory Policy / Dedup
-> Memory Write
-> Embedding Update
```

需要说明：

- Streamlit 调试台；
- React/Vite 玩家端；
- FastAPI 后端；
- SQLite 状态和日志；
- Agent workflow；
- 后台 memory jobs。

## 3. 核心模块

### 3.1 状态模型

- NPC 状态：`mood`、`trust`、`affection`、`hidden_alignment`；
- 玩家状态：位置、背包、解锁地点；
- 任务状态：`lost_key`、`gate_badge`、`ancient_notes`、`relic_tip`；
- 世界事件。

### 3.2 上下文和记忆系统

- `recent_interactions`：短期上下文；
- `memories`：玩家交互产生的长期记忆，类型为 `semantic`、`episodic`、`relational`、`procedural`，并带 facets/scope/evidence/scores；
- `lore_documents`：稳定世界/NPC 设定；
- `memory_embeddings` / `lore_embeddings`：语义检索索引；
- `memory_jobs`：后台长期记忆处理队列。

### 3.3 Hybrid RAG

- 对比 `legacy`、`typed`、`semantic`、`hybrid`；
- 解释 `retrieval_score`、`rule_score`、`semantic_score`、`score_breakdown`；
- 说明默认 `mock_hash` 保证可复现，真实 embedding 是可选增强。

### 3.4 结构化决策与工具调用

重点说明工具调用真实修改 SQLite：

- `update_trust`
- `update_affection`
- `give_item`
- `update_quest_status`
- `unlock_location`
- `record_world_event`

### 3.5 任务状态机和社交策略

- 所有任务遵守 `not_started -> in_progress -> completed`；
- Sable 可以 `redirect` / `deceive`，但不能越权解锁遗迹；
- social metadata 表达欺骗、拉拢、试探、反对等行为；
- 程序仍拥有事实和状态写入权。

### 3.6 LLM 接入

- 玩家可见主回合 runtime 需要 OpenAI-compatible LLM；
- 测试通过 patch OpenAI-compatible 调用保持离线可运行；
- LLM 可参与 decision、response polish、memory candidate、memory review；
- 所有 LLM 输出经过 schema、business rule、task state machine 和 memory gate。

## 4. 实验案例

### 案例一：低信任拒绝透露入口

输入：

```text
我想打听一下地下遗迹的入口。
```

预期：Lina 拒绝透露，`social_intent=conceal`，不解锁地点。

### 案例二：归还钥匙改变状态

输入：

```text
我把你丢失的钥匙找回来了。
```

预期：提升信任、提升好感、完成任务、发放物品、enqueue memory job。

### 案例三：四 NPC 独立任务

展示 Ron、Mira、Sable 各自任务线，证明同一 workflow 可复用且隔离状态。

### 案例四：Sable 社交误导不改写事实

展示 Sable 可以诱导或误导玩家，但不会直接调用 `unlock_location`。

### 案例五：Hybrid RAG 处理隐含表达

展示类似：

```text
我之前替你解决过那个麻烦，现在能告诉我入口吗？
```

说明 semantic/hybrid 检索如何补足关键词检索。

## 5. 与普通聊天机器人的区别

- 普通聊天机器人主要生成回复；
- 本系统读取状态和记忆后生成结构化 decision；
- decision 触发工具调用；
- 工具调用真实改变数据库；
- 状态变化影响后续交互；
- 长期记忆通过后台 policy/gate 写入；
- trace 可复现完整路径。

## 6. 测试与验证

当前自动测试：

```powershell
.venv/bin/python -m unittest discover -s tests -v
```

当前结果：64 个测试通过。

覆盖：

- 四 NPC seed 和任务线；
- 任务状态机；
- 多 NPC 记忆隔离；
- LLM-required runtime、constraint guard 和 validation；
- retrieval/lore/embedding fallback；
- FastAPI endpoints；
- display translation；
- trace artifacts。

## 7. 局限性与后续工作

- 自定义 workflow 尚未迁移到 LangGraph；
- 后台 memory worker 已可常驻消费队列，但并发锁、失败重试和运行监控仍可增强；
- 玩家可见主 runtime 需要真实 OpenAI-compatible LLM；embedding provider 仍可在 `mock_hash` 与真实 provider 之间切换，稳定评分路径可使用确定性 embedding；
- 多 NPC 信息传播和复杂关系网络尚未实现；
- 最终 PPT、录屏、截图和报告需要基于当前版本补齐。

## 8. AI 工具使用说明

如实说明 AI 辅助了代码模板、文档草稿和调试建议；系统设计取舍、运行验证、实验案例选择和最终结论由项目成员确认。报告中的截图、trace 和测试结果应来自本地真实运行。
