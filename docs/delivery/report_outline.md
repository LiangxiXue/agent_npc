# Written Report Outline

报告主体建议控制在 15 页以内，重点写 Agent 系统，不要把篇幅花在游戏剧情。

## 1. 项目背景与问题定义

- 普通 LLM 角色缺少稳定状态和可验证行动；
- 文字冒险场景作为可控实验环境；
- 项目目标：构建记忆驱动、状态驱动、工具可执行的角色 Agent。

## 2. 系统总体设计

- Streamlit 前端；
- SQLite 状态与日志存储；
- Agent workflow；
- 工具调用层。

建议插入 workflow 图：

```text
Player Input
-> Short-Term Context Load
-> Long-Term Memory Retrieval
-> State Load
-> Structured Decision
-> Tool Execution
-> Response Generation
-> Memory Policy
-> Short-Term Interaction Write
-> Trace Logging
```

## 3. 核心模块

### 3.1 状态模型

- NPC 状态：`mood`、`trust`、`affection`；
- 玩家状态：位置、背包、解锁地点；
- 任务状态：`lost_key`；
- 世界事件。

### 3.2 记忆系统

- `recent_interactions` 短期上下文；
- 类型化 `memories` 长期记忆表；
- Memory Policy 写入规则；
- `retrieval_score` 和 `retrieval_reason`；
- 后续可替换为向量检索。

### 3.3 工具调用

重点说明工具调用会真实修改 SQLite：

- `update_trust`
- `update_affection`
- `give_item`
- `update_quest_status`
- `unlock_location`

### 3.4 执行轨迹

页面展示：

- 检索到的记忆；
- Memory Policy 判断；
- 长期记忆写入；
- workflow steps；
- 结构化决策；
- 工具调用；
- 状态变化；
- interaction log。

### 3.5 LLM 接入准备

当前 MVP 使用 mock 决策，保证无 API key 时也能运行。真实 LLM 后续只需要替换 `src/agent/decision.py` 中的决策函数，并沿用 `src/agent/prompts.py` 中的结构化输出格式。

## 4. 实验案例

### 案例一：低信任拒绝透露入口

输入：

```text
我想打听一下地下遗迹的入口。
```

预期：Lina 拒绝透露，系统只写入低重要性记忆。

### 案例二：归还钥匙改变状态

输入：

```text
我把你丢失的钥匙找回来了。
```

预期：提升信任、提升好感、完成任务、发放物品、写入记忆。

### 案例三：基于记忆和任务状态解锁地点

输入：

```text
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

预期：系统检索相关记忆，并调用 `unlock_location`。

## 5. 与普通聊天机器人的区别

- 普通聊天机器人主要生成回复；
- 本系统把记忆和状态作为决策条件；
- 决策会触发工具调用；
- 工具调用会真实改变数据库；
- 状态变化影响后续交互；
- 全流程可被 trace 和 log 复现。

## 6. 测试与验证

说明已实现 `tests/test_workflow.py`，覆盖：

- 低信任拒绝；
- 归还钥匙状态更新；
- 完成任务后解锁入口；
- interaction log 保存 trace artifacts。

## 7. 局限性与后续工作

- 当前使用 mock 决策，尚未接真实 LLM；
- 记忆检索是关键词检索；
- 当前只有一个 NPC；
- 后续可加入 LangGraph、真实 LLM 结构化输出、向量数据库、多 NPC 信息传播。

## 8. AI 工具使用说明

如实说明 AI 辅助了代码模板、文档草稿和调试建议；系统设计、运行验证、课程分析和最终取舍需要由项目成员确认。
