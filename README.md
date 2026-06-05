# Memory-Driven Interactive Character Agent

这是一个以文字冒险世界为验证场景的 LLM-driven 角色 Agent 原型。项目重点不是制作完整游戏，而是展示大语言模型如何被放入一个可解释、可验证的 Agent 闭环中：角色会读取稳定世界设定，检索长期记忆，形成主观信念、情绪、目标和计划，再由 LLM 生成结构化决策与自然语言回复；最终行动必须经过程序规则校验，才能改变任务、地点、关系和世界状态。

当前系统已经从单 NPC 对话原型扩展为多角色 living-world simulation：四个 NPC、任务状态机、Hybrid RAG、后台记忆 worker、NPCMind、自主 NPC tick、遗迹主线 world runtime，以及可配置 Traveler agent。系统希望验证的核心问题是：LLM 角色能否在有记忆、有目标、有约束、有世界事件的环境中持续做出一致、可追踪、不会越权改写事实的行动。

一个典型 NPC 回合会经历以下流程：玩家输入或世界事件触发角色观察；系统检索 lore、近期上下文和长期记忆；NPCMind 生成 belief、emotion、active goal、active plan 和 social strategy；LLM 基于这些私有上下文输出结构化 decision；程序将 decision 转换为 NPCAction，并通过 ActionValidator 和任务状态机校验；Environment 执行合法行动，写回数据库；最后系统生成回复、记录 reflection，并把重要信息送入后台长期记忆流程。trace 会保存每一步的输入、决策、工具调用、状态变化和反思结果。

Traveler agent 是 living-world simulation 中的“自动探索者”。它不是普通玩家输入，而是一个由 YAML profile 配置的角色 agent，拥有公开身份、隐藏背景、私人目标、行动边界、关系状态和起始位置。每一轮 simulation 中，Traveler 会观察世界事件和地点状态，检索相关记忆与线索，决定下一步探索、询问、等待或互动行为；这些行动同样要经过程序校验后才能影响世界。这样系统可以在没有手动玩家逐句输入的情况下，自动运行一段多角色遗迹探索过程，并观察 NPC、Traveler 和世界主线如何相互推动。

## 当前项目状态

### 已完成

- 多 NPC 原型：`lina`、`ron`、`mira`、`sable`，每个 NPC 有独立状态、主任务、长期记忆、短期上下文和交互日志。
- 四条任务线：`lost_key`、`gate_badge`、`ancient_notes`、`relic_tip`，统一经过程序拥有的任务状态机校验。
- 社交策略层：decision 输出包含 `social_intent` 和 `social_stance`，Sable 使用 `hidden_alignment='exploit_ruins'` 验证欺骗、拉拢、试探、反对等社交行为不会越权改写事实。
- NPCMind 心智层：`src/agent/npc_mind.py` 从 `Observation` 形成 subjective belief、emotion、active goal、active plan、social strategy 和 reflection。
- Narrative Environment：`src/agent/environment.py` 将每轮上下文整理为 `Observation`，把 LLM decision 和 NPCMind context 转成带 `goal_id`、`plan_step`、`speech_goal` 的 `NPCAction`，再由程序规则校验并执行成 `ActionResult`。
- ActionValidator：`src/agent/action_validator.py` 将动作校验边界从环境执行中拆出，负责把非法提案安全降级为不会改写状态的行动。
- Response guard：回复层会使用 belief / goal / plan / reflection 作为私有上下文，但会阻止 `belief_id`、`goal_id`、`plan_id`、JSON、数据库字段和 trace 字段泄露到玩家台词。
- 记忆系统：短期交互进入 `recent_interactions`；长期重要事实进入类型化 `memories`，当前长期记忆类型为 `semantic`、`episodic`、`relational`、`procedural`，并带 `facets`、`scope`、`evidence_text`、`stability`、`future_usefulness` 元数据；检索支持 `off`、`legacy`、`typed`、`semantic`、`hybrid`。
- 后台记忆任务：实时回合只 enqueue `memory_jobs`，长期记忆候选、审查、写入和 embedding 更新由单次脚本、API 或常驻 worker 处理。
- Provider-aware retrieval：embedding provider 支持 `mock_hash` 和 OpenAI-compatible；backend 支持 `sqlite_cosine` 和可选 `faiss`，不可用时自动 fallback。
- Streamlit 调试台：`app.py` 提供 NPC 选择、输入、状态面板、检索预览、执行轨迹、工具调用、状态变化和 trace 导出。
- React/Vite 玩家端：`frontend/` 提供暗色像素 RPG 界面，保留开发者 trace 面板。
- FastAPI 玩家端接口：`src/api/server.py` 包装同一套 Agent workflow，提供对话、检索预览、trace 导出、embedding rebuild、后台记忆任务处理、自主 tick 和 trace HTML 接口。
- 自主 NPC runtime：`src/agent/autonomous_tick.py` 通过 `world_event -> npc_event_inbox -> ActionCatalog -> constrained decision -> validation -> mailbox/trace` 让 NPC 响应世界事件并主动生成计划和消息。
- Living World ruins demo：`src/agent/world_arc.py`、`src/agent/living_world.py` 和 `scripts/run_living_world_demo.py` 将玩家动作、场景对象、NPC routines、autonomous tick、ArcDirector 和可变结局连在一起。
- Traveler runtime：`data/travelers/*.yaml`、`src/agent/traveler_*`、`src/agent/living_world_runtime.py` 和 `scripts/run_traveler_world_demo.py` 支持用可配置 Traveler profile 替代手动玩家，运行多轮 living-world simulation。
- Exploration planner：`src/agent/exploration_planner.py` 为 Traveler fallback 和 timeline export 提供线索路由、信息增益和重复探索降权。
- Timeline export：living-world Traveler demo 可导出 JSON 和 Markdown，包含 round、Traveler 内部 timings、NPC tick、exploration routing 和 arc progress。
- 可解释 trace：玩家回合和 autonomous/living-world runtime 都记录检索、状态、Observation、Belief Update、Goal Selection、Plan Step、decision、NPCAction、ActionResult、Reflection、工具、状态变化、memory job、timings 和 workflow steps。

### 玩家回合工作流

```text
Player Input
-> Recent Context Load
-> Lore Retrieval
-> Long-Term Memory Retrieval
-> State Load
-> NarrativeEnvironment.observe()
-> NPCMind Belief / Emotion / Goal / Plan / Social Strategy
-> Turn Classification
-> LLM Structured Decision
-> NPCAction Proposal
-> Program-Owned Validation and Quest State Machine
-> Environment Execution
-> ActionResult
-> Reflection
-> Response Generation
-> Background Memory Job Enqueue
-> Short-Term Interaction Write
-> Trace Logging

Background:
memory_jobs
-> LLM Memory Candidate Generation
-> LLM Memory Candidate Review
-> Memory Policy / Programmatic Gate / Dedup
-> Long-Term Memory Write
-> Embedding Update
```

### Living World 工作流

```text
Traveler profile
-> TravelerActor observe / retrieve / decide / validate / act / reflect
-> world_events
-> NPC routines and npc_event_inbox dispatch
-> NpcActorAdapter autonomous_tick
-> ArcDirectorActor score and resolve arc
-> Major event detection
-> JSON / Markdown timeline export
```

## 验证

建议使用仓库内虚拟环境运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

查看当前测试收集数量：

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

最近本地完整验证（2026-06-04）：`211 passed, 3 warnings, 17 subtests passed`。

前端构建命令：

```powershell
cd frontend
npm run build
```

## 运行方式

建议使用 Python 3.11 或更高版本。

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

启动 Streamlit 调试台：

```powershell
streamlit run app.py
```

启动玩家端需要三个进程：FastAPI 后端、React/Vite 前台和长期记忆 worker。

终端 1，启动 FastAPI 后端：

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

终端 2，启动 React/Vite 前台：

```powershell
cd frontend
npm install
npm run dev
```

终端 3，启动长期记忆 worker：

```powershell
python scripts/memory_worker.py --limit 5
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

首次启动会自动创建并初始化：

```text
data/agent_state.db
```

## 关键脚本

命令行四 NPC 玩家回合演示：

```powershell
python scripts/run_mvp_demo.py
```

主动 NPC runtime 演示：

```powershell
python scripts/run_autonomous_llm_demo.py --mock
```

遗迹主线 living-world demo：

```powershell
python scripts/run_living_world_demo.py --mock
```

Traveler Living World 验收 demo：

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --mock --max-npc-ticks 4 --idle-npc-probe --stop-on-outcome --export-dir data/traces/living_world_acceptance
```

导出玩家回合 trace：

```powershell
python scripts/export_trace.py
```

处理后台长期记忆任务：

```powershell
python scripts/process_memory_jobs.py --limit 10
```

常驻处理后台长期记忆任务：

```powershell
python scripts/memory_worker.py --limit 5
```

重建 memory embedding：

```powershell
python scripts/rebuild_memory_embeddings.py
```

运行记忆检索评测：

```powershell
python scripts/run_memory_eval.py
```

生成像素占位资产：

```powershell
python scripts/generate_pixel_assets.py
```

## 目录结构

```text
agent_npc/
├── app.py
├── README.md
├── requirements.txt
├── data/
│   ├── lore/
│   ├── travelers/
│   ├── traces/
│   ├── eval/
│   ├── history/
│   └── agent_trace_export.json
├── docs/
│   ├── delivery/
│   ├── design/
│   ├── evaluation/
│   ├── reference/
│   └── superpowers/
├── frontend/
│   ├── public/assets/pixel/
│   └── src/
├── scripts/
│   ├── export_trace.py
│   ├── generate_pixel_assets.py
│   ├── memory_worker.py
│   ├── process_memory_jobs.py
│   ├── rebuild_memory_embeddings.py
│   ├── run_autonomous_llm_demo.py
│   ├── run_living_world_demo.py
│   ├── run_memory_eval.py
│   ├── run_mvp_demo.py
│   ├── run_traveler_world_demo.py
│   └── test_llm_api.py
├── src/
│   ├── agent/
│   ├── api/
│   ├── storage/
│   └── tools/
└── tests/
    ├── test_autonomous_tick.py
    ├── test_living_world.py
    ├── test_living_world_runtime.py
    ├── test_traveler_actions.py
    ├── test_traveler_decision.py
    ├── test_traveler_profile.py
    ├── test_traveler_state.py
    ├── test_traveler_tick.py
    └── test_workflow.py
```

## 配置

### LLM Provider

配置 OpenAI-compatible provider 后，系统优先使用真实 LLM。LLM 当前可参与：

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "your_api_key"
$env:AGENT_NPC_LLM_MODEL = "gpt-4o-mini"
$env:AGENT_NPC_LLM_BASE_URL = "https://api.openai.com/v1"
$env:AGENT_NPC_LLM_TIMEOUT = "60"
$env:AGENT_NPC_LLM_RETRIES = "1"
streamlit run app.py
```

1. 玩家回合结构化 decision JSON；
2. 最终 NPC 回复润色；
3. 长期记忆候选生成；
4. 长期记忆候选审查；
5. autonomous NPC tick 的受约束策略选择；
6. Traveler decision。

玩家可见的主回合 runtime 需要配置可用 API key。测试、`--mock` autonomous demo 和 `--mock` Traveler demo 可以离线运行；本地规则分类、任务状态机、schema/business-rule 校验仍是程序确定性逻辑，不属于模型替身。

SQLite 状态、任务状态机、工具权限、重大事实和最终记忆写入仍由程序控制。

### Embedding / Retrieval

默认配置不依赖外部 API：

```powershell
$env:AGENT_NPC_EMBEDDING_PROVIDER = "mock_hash"
$env:AGENT_NPC_RETRIEVAL_BACKEND = "sqlite_cosine"
```

真实 embedding provider：

```powershell
$env:AGENT_NPC_EMBEDDING_PROVIDER = "openai_compatible"
$env:AGENT_NPC_EMBEDDING_API_KEY = "your_api_key"
$env:AGENT_NPC_EMBEDDING_MODEL = "text-embedding-3-small"
$env:AGENT_NPC_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
$env:AGENT_NPC_EMBEDDING_ALLOW_FALLBACK = "1"
```

可选 backend：

```powershell
$env:AGENT_NPC_RETRIEVAL_BACKEND = "faiss"
```

FAISS 或真实 embedding 不可用时，系统会记录 fallback 原因并保持 SQLite/mock 路径可运行。

## 建议演示输入

基础 Lina 主线：

```text
我想打听一下地下遗迹的入口。
我把你丢失的钥匙找回来了。
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

四 NPC 社交/任务演示：

```text
Ron，我想进入遗迹，守卫这边能放行吗？
Ron，我找到守卫徽章了，登记册签名也能对上。
Mira，我想问问遗迹铭文和田野笔记该怎么记录。
Mira，我看到遗迹门边有三角符号和封闭石门，这是我的一手观察。
Sable，你知道遗迹入口或者古物线索吗？
Sable，我听说入口在酒馆后巷，我接受你说的先查换岗记录。
```

## 为什么不是普通聊天机器人

普通聊天机器人通常只根据历史对话生成回复。本项目把回复放在一个可验证 Agent 闭环里：

- NPC、玩家、Traveler、任务、地点、场景对象和世界事件都写入 SQLite；
- decision 是结构化对象，包含 intent、工具调用、社交策略和回复关键词；
- NPCMind 在 decision 前形成 belief、emotion、goal、plan 和 social strategy；
- Environment 将 decision 和 mind context 转成 `NPCAction`，经过校验后才执行工具；
- autonomous tick 只能从 ActionCatalog 暴露的可用行动中选择；
- Traveler tick 有 profile bias、private goals、hard boundaries、relationships 和 private notes；
- `ActionResult` 记录本轮是否 accepted、实际执行了哪些工具、状态前后变化和回复约束；
- Reflection 在 `ActionResult` 之后生成内部反思，必要时写入长期 procedural memory；
- 工具调用会真实改变数据库，但最终事实以 `ActionResult` 为准，而不是以 LLM 自述为准；
- 任务推进、arc phase、scene object state 和地点解锁经过程序状态机，不允许 LLM 直接越权完成；
- 长期记忆由后台 LLM candidate/review、programmatic gate 和 dedup 管理；
- 检索到的 lore / memory 会进入后续 decision 和 response；
- trace 能解释每轮“检索了什么、角色如何理解、目标和计划是什么、为什么行动、改了什么状态、是否反思和写入记忆”。

因此系统不是“说自己记得”，而是“根据记忆和状态做决策，并把行动结果写回系统”。

## 当前边界

- Agent 编排仍是自定义 Python workflow，没有迁移到 LangGraph。
- 玩家可见 LLM runtime 需要 OpenAI-compatible provider 和可用 API key；测试和 `--mock` demo 通过 deterministic fallback / patch 保持离线可运行。
- Living-world runtime 已经支持演示级多轮调度、NPC routines、Traveler tick、NPC autonomous tick、ArcDirector 和 timeline export，但仍是研究原型，不是完整通用游戏引擎。
- NPCMind 是确定性、可测试的第一版；belief、emotion、goal、plan、reflection、plan blockers、cooldown 和 autonomous tick 已接入，但还不是完整认知架构。
- Traveler profile 支持 YAML 配置、hidden identity、private goals、risk level、hard boundaries 和 relationship state；目前主要用于 ruins demo 的可复现实验。
- 后台记忆任务支持通过脚本/API 单次处理，也支持 `scripts/memory_worker.py` 常驻消费。
- FAISS 和真实 embedding 是可选增强，不是默认依赖。

## 后续方向

1. 将 Traveler memory 与现有 player/NPC memory 进一步统一，明确跨 actor 检索和隐私边界。
2. 增强 NPC 主动消息队列，让 React 玩家端能直接消费 proactive messages。
3. 增加更多场景对象、地点可见性和事件传播渠道，让 Observation 更接近“角色当前能看到、听到或通过信息网络知道的内容”。
4. 扩展 `available_actions` 前置条件、失败结果和局部后果，让行动选择更接近可玩的系统。
5. 将计划状态从 memory facets 升级为专用表或事件流，让计划推进、阻塞和放弃更易查询。
6. 引入 LangGraph 或显式节点编排，把当前 workflow 拆成更标准的 Agent graph。
7. 增强后台 worker 的并发锁、重试策略、运行监控和服务化启动方式。
8. 增强真实 LLM decision 的 schema 修复、失败案例记录和回归测试。
9. 增加本地 embedding 模型、持久化 FAISS 索引或 Qdrant/Chroma backend。
