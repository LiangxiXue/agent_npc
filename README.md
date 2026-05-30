# Memory-Driven Interactive Character Agent

这是一个以文字冒险 NPC 交互为验证场景的记忆驱动角色 Agent 原型。项目重点不是制作完整游戏，而是展示角色 Agent 如何在多轮交互中读取稳定世界设定、检索玩家相关记忆、读取当前状态、生成结构化决策、调用工具修改外部状态，并保存可解释的执行轨迹。

当前实现已经从单 NPC MVP 扩展为四 NPC、多任务、带社交策略的 Agent 原型：Lina 保留钥匙/遗迹主线，Ron、Mira、Sable 分别验证守卫证据、遗迹研究、古物交易与误导式社交行为。玩家可见的主回合 runtime 需要配置 OpenAI-compatible LLM；LLM 参与结构化决策、最终回复润色和后台记忆处理。测试通过 patch OpenAI-compatible 调用保持离线可运行；检索层支持 OpenAI-compatible embedding、Hybrid RAG 和本地 fallback。

## 当前项目状态

### 已完成

- 多 NPC 原型：`lina`、`ron`、`mira`、`sable`，每个 NPC 有独立状态、主任务、长期记忆、短期上下文和交互日志。
- 四条任务线：`lost_key`、`gate_badge`、`ancient_notes`、`relic_tip`，统一经过程序拥有的任务状态机校验。
- 社交策略层：decision 输出包含 `social_intent` 和 `social_stance`，Sable 使用 `hidden_alignment='exploit_ruins'` 验证欺骗、拉拢、试探、反对等社交行为不会越权改写事实。
- Streamlit 调试台：`app.py` 提供 NPC 选择、输入、状态面板、检索预览、执行轨迹、工具调用、状态变化和 trace 导出。
- React/Vite 玩家端：`frontend/` 提供暗色像素 RPG 界面，保留开发者 trace 面板。
- FastAPI 玩家端接口：`src/api/server.py` 包装同一套 Agent workflow，提供对话、检索预览、trace 导出、embedding rebuild 和后台记忆任务处理接口。
- SQLite 持久化：保存 NPC 状态、玩家状态、物品、地点、任务、长期记忆、记忆/设定 embedding、后台记忆任务、世界事件和交互日志。
- 显式上下文层：`retrieved_lore`、`retrieved_memories`、`state_snapshot`、`recent_context` 分离进入 decision/response/trace。
- 记忆系统：短期交互进入 `recent_interactions`；长期重要事实进入类型化 `memories`，当前长期记忆类型为 `semantic`、`episodic`、`relational`、`procedural`，并带 `facets`、`scope`、`evidence_text`、`stability`、`future_usefulness` 元数据；检索支持 `off`、`legacy`、`typed`、`semantic`、`hybrid`。
- 后台记忆任务：实时回合只 enqueue `memory_jobs`，长期记忆候选、审查、写入和 embedding 更新由单次脚本、API 或常驻 worker 处理，降低玩家端等待时间。
- Provider-aware retrieval：embedding provider 支持 `mock_hash` 和 OpenAI-compatible；backend 支持 `sqlite_cosine` 和可选 `faiss`，不可用时自动 fallback。
- LLM runtime 路径：同一 OpenAI-compatible client 可参与结构化 decision、最终回复润色、记忆候选生成和记忆审查；玩家可见主流程需要可用 API key，测试通过 patch 调用保持离线可运行。
- Narrative Environment：`src/agent/environment.py` 将每轮上下文整理为 `Observation`，把 LLM decision 转成 `NPCAction`，再由程序规则校验并执行成 `ActionResult`。LLM 只能提出行动，世界事实以环境执行结果为准。
- 可解释 trace：每轮记录检索、状态、Observation、decision、NPCAction、ActionResult、工具、状态变化、memory job 状态、timings 和 workflow steps。

### 当前工作流

```text
Player Input
-> Recent Context Load
-> Lore Retrieval
-> Long-Term Memory Retrieval
-> State Load
-> Turn Classification
-> LLM Structured Decision
-> NarrativeEnvironment Observation / NPCAction
-> Program-Owned Validation and Quest State Machine
-> Environment Execution
-> ActionResult
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

### 已验证

当前测试命令：

```powershell
.venv/bin/python -m unittest discover -s tests -v
```

当前验证结果：64 个测试全部通过。

玩家端构建命令：

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

命令行四 NPC 演示：

```powershell
python scripts/run_mvp_demo.py
```

导出 trace：

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
│   ├── eval/
│   ├── history/
│   └── agent_trace_export.json
├── docs/
│   ├── delivery/
│   ├── design/
│   ├── evaluation/
│   └── reference/
├── frontend/
│   ├── public/assets/pixel/
│   └── src/
├── scripts/
│   ├── export_trace.py
│   ├── generate_pixel_assets.py
│   ├── probe_context_retrieval.py
│   ├── process_memory_jobs.py
│   ├── memory_worker.py
│   ├── rebuild_memory_embeddings.py
│   ├── run_memory_eval.py
│   ├── run_mvp_demo.py
│   └── test_llm_api.py
├── src/
│   ├── agent/
│   ├── api/
│   ├── storage/
│   └── tools/
└── tests/
    ├── test_api.py
    ├── test_display_translation.py
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

1. 结构化 decision JSON；
2. 最终 NPC 回复润色；
3. 长期记忆候选生成；
4. 长期记忆候选审查。

玩家可见的主回合 runtime 需要配置可用 API key。测试通过 patch OpenAI-compatible 调用保持离线可运行；本地规则分类、任务状态机、schema/business-rule 校验仍是程序确定性逻辑，不属于模型替身。

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

- NPC、玩家、任务、地点和世界事件都写入 SQLite；
- decision 是结构化对象，包含 intent、工具调用、社交策略和回复关键词；
- Environment 将 decision 转成 `NPCAction`，经过校验后才执行工具；
- `ActionResult` 记录本轮是否 accepted、实际执行了哪些工具、状态前后变化和回复约束；
- 工具调用会真实改变数据库，但最终事实以 `ActionResult` 为准，而不是以 LLM 自述为准；
- 任务推进经过程序状态机，不允许 LLM 直接越权完成任务；
- 长期记忆由后台 LLM candidate/review、programmatic gate 和 dedup 管理；
- 检索到的 lore / memory 会进入后续 decision 和 response；
- trace 能解释每轮“检索了什么、为什么行动、改了什么状态、是否写入记忆”。

因此系统不是“说自己记得”，而是“根据记忆和状态做决策，并把行动结果写回系统”。

## 当前边界

- Agent 编排仍是自定义 Python workflow，没有迁移到 LangGraph。
- 玩家可见 LLM runtime 需要 OpenAI-compatible provider 和可用 API key；测试通过 patch LLM 调用保持离线可运行。
- 当前 Environment 层主要提供流程边界、校验、执行和 trace 事实来源；`Decision -> NPCAction` 仍是轻量结构化转换，尚未实现完整世界模拟。
- 后台记忆任务支持通过脚本/API 单次处理，也支持 `scripts/memory_worker.py` 常驻消费。
- FAISS 和真实 embedding 是可选增强，不是默认依赖。
- 课程最终报告 PDF、PPT、录屏和最终截图仍需基于当前运行结果整理。

## 后续方向

1. 做实 Environment 的空间和可见性模型：给 NPC、玩家、物品、事件和地点增加 location / visibility，让 Observation 不再只是按 `npc_id` 聚合上下文，而是反映 NPC 当前能看到、听到或通过信息网络知道的内容。
2. 增加 NPC 私有知识和事件传播：世界事件不再全局可见，而是按酒馆传闻、守卫报告、学者记录、黑市网络等渠道传播给不同 NPC。
3. 增加环境可行动作列表：由 Environment 根据当前状态生成 `available_actions`，LLM 只能从可用行动中选择，避免凭空生成工具或越权行动。
4. 增加场景对象状态：例如 `tavern_backroom.locked`、`town_gate.guard_shift`、`ruins_entrance.discovered`、`sealed_door.symbols_observed`，让任务推进依赖对象状态而不只依赖 quest status。
5. 增强 action prerequisites 和失败结果：为每类行动定义前置条件、失败原因和局部后果，例如不在 town_gate 不能检查 gate badge，没观察 inscription 不能完成 ancient_notes。
6. 引入 LangGraph 或显式节点编排，把当前 workflow 拆成更标准的 Agent graph。
7. 增强后台 worker 的并发锁、重试策略、运行监控和服务化启动方式。
8. 增强真实 LLM decision 的 schema 修复、失败案例记录和回归测试。
9. 增加本地 embedding 模型、持久化 FAISS 索引或 Qdrant/Chroma backend。
10. 完善课程交付材料：报告、PPT、截图、录屏、AI 使用说明和演示脚本。
