# Memory-Driven Interactive Character Agent

这是一个以文字冒险 NPC 交互为验证场景的记忆驱动角色 Agent 原型。项目重点不是制作完整游戏，而是展示一个角色 Agent 如何在多轮交互中读取记忆、读取状态、生成结构化决策、调用工具修改外部状态，并保存可解释的执行轨迹。

当前实现已经完成单 NPC MVP 主线：Lina 可以基于玩家输入、长期记忆、任务状态和信任度做决策；决策会触发 SQLite 工具调用，改变 NPC 关系值、任务状态、玩家解锁地点、世界事件和交互日志。系统默认可用 mock 模式稳定运行，也提供 OpenAI-compatible LLM 实验路径。

## 当前项目进度

### 已完成

- 单 NPC MVP：`lina`，角色为酒馆老板。
- Streamlit Web Demo：`app.py` 提供输入、状态面板、执行轨迹、工具调用、状态变化和日志下载。
- SQLite 持久化：保存 NPC 状态、玩家状态、玩家物品、地点解锁、任务、长期记忆、世界事件和交互日志。
- Agent workflow 主链路：

```text
Player Input
-> Memory Retrieval
-> State Load
-> Structured Decision
-> Tool Execution
-> Response Generation
-> Memory Update
-> Trace Logging
```

- 结构化决策层：`src/agent/decision.py` 支持 mock 决策和可选真实 LLM 决策。
- 回复生成层：`src/agent/response.py` 支持由 Agent decision 输出的 `response_keywords` 约束真实 LLM 润色最终 NPC 台词。
- 事实与规则护栏：系统生成 `state_before/state_after`，并校验关键工具调用、任务推进和遗迹入口等重大事实。
- 工具调用层：`src/tools/sqlite_tools.py` 将 Agent 动作落到 SQLite 状态更新。
- 记忆检索：当前使用轻量关键词、标签、重要性排序，不依赖额外 NLP 或向量数据库。
- 可选真实 LLM 接入：`src/agent/llm_client.py` 支持 OpenAI-compatible `/chat/completions` JSON 输出，并带有失败回退到 mock 的机制。
- 回归测试：`tests/test_workflow.py` 覆盖核心流程、状态更新、日志保存、LLM 配置缺失回退、工具名和参数校验。
- 演示与交付材料草稿：`docs/` 下已有架构说明、LLM 接入说明、测试计划、展示脚本、报告提纲和 AI 使用说明模板。

### 已验证

当前工作区已通过以下验证：

```bash
python -m unittest discover -s tests -v
```

结果：13 个测试全部通过。

命令行 MVP 演示也已可运行：

```bash
python scripts/run_mvp_demo.py
```

该脚本会重置 demo 数据，连续执行 3 轮典型交互，并输出每轮的 intent、workflow、tool calls、state changes 和最终状态。

导出 trace：

```bash
python scripts/export_trace.py
```

导出文件：

```text
data/agent_trace_export.json
```

Web 页面仍保留 `Download Trace JSON` 按钮；同时页面在显示 interaction log 时会自动把同一份 payload 写入 `data/agent_trace_export.json`，不需要再手动下载后复制。

### 当前边界

- 目前主线仍是单 NPC：Lina；Ron、Mira 等多 NPC 泛化尚未实现。
- 记忆检索仍是 SQLite 关键词检索，没有引入向量数据库或语义检索。
- Agent 编排当前是自定义 Python workflow，没有迁移到 LangGraph。
- 真实 LLM 路径已接入为实验能力，但课堂展示和自动测试仍应保留 mock 模式作为稳定兜底。
- mock 模式下最终回复仍使用确定性模板；OpenAI-compatible 模式下会在工具执行后调用 LLM，根据 intent、response style、response keywords、当前状态和工具结果生成更自然的角色回复。
- 目前还没有完整课程报告 PDF、PPT、录屏或最终截图材料。

## 目录结构

```text
agent_npc/
├── app.py
├── README.md
├── requirements.txt
├── Memory_Driven_AI_NPC_Agent_项目选题计划.md
├── archive/
│   └── legacy_json_state/
├── data/
│   ├── agent_state.db
│   └── agent_trace_export.json
├── docs/
│   ├── architecture.md
│   ├── ai_usage_statement.md
│   ├── demo_script.md
│   ├── llm_integration.md
│   ├── report_outline.md
│   └── test_plan.md
├── scripts/
│   ├── export_trace.py
│   ├── run_mvp_demo.py
│   └── test_llm_api.py
├── src/
│   ├── agent/
│   │   ├── decision.py
│   │   ├── llm_client.py
│   │   ├── prompts.py
│   │   ├── response.py
│   │   ├── world_facts.py
│   │   └── workflow.py
│   ├── storage/
│   │   ├── database.py
│   │   └── schema.sql
│   └── tools/
│       └── sqlite_tools.py
└── tests/
    └── test_workflow.py
```

早期 JSON 状态演示代码已经归档到 `archive/legacy_json_state/`，当前运行主线使用 SQLite。

## 核心功能

### 1. 状态和记忆持久化

SQLite schema 位于：

```text
src/storage/schema.sql
```

主要数据表：

- `npcs`
- `player_state`
- `player_items`
- `unlocked_locations`
- `quests`
- `memories`
- `world_events`
- `interaction_logs`

### 2. 工具调用

当前支持的工具：

- `add_memory`
- `update_trust`
- `update_affection`
- `give_item`
- `update_quest_status`
- `unlock_location`
- `record_world_event`

这些工具不是展示用文本，而是真实写入 SQLite 的状态变更。

### 3. 可解释执行轨迹

每轮交互都会记录：

- 玩家输入；
- 检索到的记忆；
- 结构化 decision；
- 系统生成的 `state_before` 和 `state_after`；
- response keywords 和回复生成模式；
- 工具调用及参数；
- 状态变化；
- workflow steps；
- NPC 最终回复。

这些内容会保存到 `interaction_logs`，也可以通过页面按钮或 `scripts/export_trace.py` 导出为 JSON，用于报告、PPT 和课堂演示。

## 运行方式

建议使用 Python 3.11 或更高版本。

安装依赖：

```bash
pip install -r requirements.txt
```

启动 Web demo：

```bash
streamlit run app.py
```

首次启动时会自动创建并初始化：

```text
data/agent_state.db
```

如果需要重置 demo 数据，可以在页面左侧点击 `Reset SQLite Demo Data`。

## LLM 模式

### Mock 模式

mock 模式不需要 API key，适合测试、评分和无网络演示：

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "mock"
streamlit run app.py
```

测试文件会强制使用 mock 模式，避免本地 `.env` 影响测试结果。

### OpenAI-Compatible 模式

项目已提供实验性真实 LLM 接入路径。配置方式示例：

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "your_api_key"
$env:AGENT_NPC_LLM_MODEL = "gpt-4o-mini"
$env:AGENT_NPC_LLM_BASE_URL = "https://api.openai.com/v1"
streamlit run app.py
```

DeepSeek 等兼容服务可以修改 `AGENT_NPC_LLM_MODEL` 和 `AGENT_NPC_LLM_BASE_URL`。真实 LLM 分两步参与：

1. 决策阶段返回与 `src/agent/prompts.py` 中约定一致的 JSON decision，其中包括 intent、工具调用和 `response_keywords`。状态快照不由 LLM 返回，而是由系统从 SQLite 读取后写入 trace。
2. 工具执行前会校验业务规则，例如 `start_lost_key_quest` 只能推进到 `in_progress`，`withhold_ruins_entrance` 不能解锁入口。
3. 回复阶段根据 decision、关键词、工具结果、最新状态和 canonical world facts 润色生成 `npc_response`。系统只拦截重大事实冲突，仍允许语气、动作和小氛围细节自由发挥。

若 LLM 调用失败、超时或返回非法结构，系统会回退到 mock 决策或固定回复模板，并在 trace 中记录 fallback 信息。

## 建议演示输入

先测试低信任度时询问遗迹入口：

```text
我想打听一下地下遗迹的入口。
```

然后测试归还钥匙，触发工具调用：

```text
我把你丢失的钥匙找回来了。
```

再测试基于记忆和状态的后续决策：

```text
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

## 为什么不是普通聊天机器人

普通聊天机器人通常只根据历史对话生成回复。本项目的 MVP 已经具备可验证的状态和行动闭环：

- Lina 的 `trust`、`affection`、任务状态会写入 SQLite；
- 玩家背包和已解锁地点会写入 SQLite；
- Agent 每轮会生成结构化决策和回复关键词；
- 工具调用会真实改变数据库；
- 页面会展示记忆检索、workflow trace、工具调用、状态变化和 interaction log；
- 后续回复会受到之前状态变化和记忆写入的影响。

因此系统不是“说自己记得”，而是“根据记忆和状态做决策，并把行动结果写回系统”。

## 后续主要方向

1. 多 NPC 泛化：把当前 `lina` 单角色扩展为 Ron、Mira 等多个 NPC，确保同一套 workflow 能通过 `npc_id` 复用角色卡、记忆、任务和日志。

2. 强化真实 LLM 稳定性：完善 prompt、JSON schema 校验、工具参数修复策略和失败案例记录，让真实 LLM 路径能稳定产出可执行 decision。

3. 引入更强记忆检索：在保留 SQLite 可解释性的基础上，增加向量检索或混合检索，用于处理同义表达、长文本记忆和跨轮复杂指代。

4. 增加 LangGraph 或显式节点编排：将当前自定义 workflow 拆成更清晰的节点，增强课程汇报中的智能体开发工具使用证据。

5. 完善课程交付材料：基于真实运行日志补充截图、失败案例、对比案例、PPT、书面报告和 AI 使用说明，避免只停留在代码说明。

6. 增加多 Agent 扩展实验：在多 NPC 基础上尝试 NPC 间信息传播、关系网络或间接记忆影响，作为项目加分扩展，而不是 MVP 必需项。
