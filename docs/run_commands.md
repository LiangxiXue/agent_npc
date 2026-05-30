# Agent NPC 启动命令速查

本文档整理当前项目常用启动、测试和维护命令。默认在项目根目录运行：

```bash
cd /Users/xueliangxi/agent_NPC
```

## 1. 进入 Python 虚拟环境

每开一个新终端，建议先运行：

```bash
source .venv/bin/activate
```

作用：让当前终端使用项目自己的 Python 环境。之后运行 `python`、`streamlit`、`uvicorn` 时，会优先使用 `.venv` 里的依赖。

如果不想激活环境，也可以直接使用：

```bash
.venv/bin/python
```

## 2. Streamlit 调试台

```bash
streamlit run app.py
```

用途：启动开发者/调试视角界面。

适合查看：

- NPC 状态
- 长期记忆
- 检索结果
- 工具调用
- Memory Policy
- Trace 调试信息

通常会打开：

```text
http://localhost:8501
```

## 3. 玩家前台完整启动

玩家端需要同时运行后端、前端和长期记忆 worker。建议开 3 个终端。

### 终端 1：FastAPI 后端

```bash
source .venv/bin/activate
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

用途：启动后端 API。

它负责：

- 接收玩家输入
- 调用 agent workflow
- 返回 NPC 回复
- 提供记忆预检索接口
- 提供 trace 接口
- 提供后台记忆任务处理接口

后端地址：

```text
http://127.0.0.1:8000
```

### 终端 2：React/Vite 玩家前台

第一次运行前端时，先安装依赖：

```bash
cd frontend
npm install
```

平时启动前台：

```bash
cd frontend
npm run dev
```

用途：启动玩家视角界面。

它负责显示：

- 像素 RPG 地图
- NPC 对话
- 玩家输入框
- 状态面板
- 开发者 trace 面板

浏览器打开：

```text
http://127.0.0.1:5173/
```

### 终端 3：长期记忆 Worker

```bash
source .venv/bin/activate
python scripts/memory_worker.py --limit 5
```

用途：常驻处理长期记忆队列。

它会持续检查 `memory_jobs` 表里的 `pending` 任务，并执行：

- Memory Policy
- LLM 记忆候选生成
- 程序 gate 审核
- 去重
- 写入 `memories`
- 更新 embedding

`--limit 5` 表示每次最多处理 5 条 pending memory jobs。

如果没有启动 worker，前台对话仍然能正常回复，但长期记忆任务只会排队，不会自动写入长期记忆。

## 4. 单次处理长期记忆任务

只处理一次积压任务：

```bash
python scripts/memory_worker.py --once --limit 10
```

含义：最多处理 10 条 pending memory jobs，然后退出。

旧的单次处理脚本也仍可用：

```bash
python scripts/process_memory_jobs.py --limit 10
```

## 5. 前端构建

```bash
cd frontend
npm run build
```

用途：检查前端能否正式打包。

它会执行：

- TypeScript 检查
- Vite 生产构建

## 6. 后端测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

用途：运行 Python 测试。

覆盖内容包括：

- Agent workflow
- Memory Policy
- API
- 检索
- 多 NPC
- 工具调用
- 状态机

## 7. 重建 Memory Embedding

```bash
python scripts/rebuild_memory_embeddings.py
```

用途：重建长期记忆 embedding。

一般 worker 会给新写入的记忆自动更新 embedding。只有在以下情况通常才需要手动运行：

- 改了 embedding provider
- 改了 embedding model
- 数据库里已有记忆缺少索引
- 想强制刷新 memory embedding

## 8. 导出 Trace

```bash
python scripts/export_trace.py
```

用途：导出最近的交互 trace。

适合：

- 写报告
- 展示 Agent 执行过程
- 排查 workflow / memory / retrieval 问题

## 9. 命令行 Demo

```bash
python scripts/run_mvp_demo.py
```

用途：不用打开前台，直接在命令行跑预设 demo。

适合快速确认 agent workflow 是否能跑通。

## 10. 记忆系统评测

```bash
python scripts/run_memory_eval.py
```

用途：运行记忆检索评测场景。

适合比较：

- 不同 retrieval mode
- memory policy 是否启用
- 长期记忆写入和检索效果

## 11. 最常用组合

### 只看调试台

```bash
source .venv/bin/activate
streamlit run app.py
```

### 跑玩家前台

终端 1：

```bash
source .venv/bin/activate
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

终端 2：

```bash
cd frontend
npm run dev
```

终端 3：

```bash
source .venv/bin/activate
python scripts/memory_worker.py --limit 5
```

### 跑测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### 构建前端

```bash
cd frontend
npm run build
```
