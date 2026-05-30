# Demo Script

本脚本用于课堂展示当前 Memory-Driven Interactive Character Agent，而不是早期单 Lina MVP。

## 展示目标

证明系统具备：

- SQLite 持久化状态；
- 四 NPC 独立任务和记忆；
- lore / memory / state / recent context 分层；
- Hybrid RAG 检索；
- 主观信念、情绪、目标、跨轮计划；
- 社交策略 metadata；
- `NPCAction` 中的 goal / plan step / social stance；
- 程序拥有的任务状态机；
- 环境执行后的 reflection；
- 结构化决策和工具调用；
- 后台 memory jobs；
- 可解释执行轨迹。

## 方案 A：Streamlit 调试台

启动：

```powershell
streamlit run app.py
```

演示前点击 `Reset SQLite Demo Data`。

### 1. Lina 低信任拒绝入口

```text
我想打听一下地下遗迹的入口。
```

观察：

- intent: `withhold_ruins_entrance`;
- social intent: `conceal`;
- trace 中出现 Belief Update / Goal Selection / Plan Step；
- active goal 是 `protect_underground_ruins_entrance`;
- plan step 是 `ask_motive`;
- `NPCAction` 是角色动作意图，不是直接数据库工具；
- no `unlock_location`;
- `underground_ruins_entrance` 未解锁。

### 2. Lina 归还钥匙

```text
我把你丢失的钥匙找回来了。
```

观察：

- intent: `complete_lost_key_quest`;
- trust / affection 上升；
- `lost_key` 变为 `completed`;
- 获得 `tavern_discount_coupon`;
- trace 中出现 background memory job status。

可随后运行：

```powershell
python scripts/memory_worker.py --once --limit 10
```

再检查长期记忆是否写入并索引。

### 3. Ron 证据型守卫任务

```text
我想进入遗迹，守卫这边能放行吗？
我找到守卫徽章了，登记册签名也能对上。
```

观察：

- 第一轮是 `probe_for_evidence`，不直接放行；
- 第二轮完成 `gate_badge`;
- Ron 的任务和记忆与 Lina 隔离。

### 4. Mira 研究型任务

```text
我想问问遗迹铭文和田野笔记该怎么记录。
我看到遗迹门边有三角符号和封闭石门，这是我的一手观察。
```

观察：

- `ancient_notes` 从 `not_started` 到 `in_progress` 再到 `completed`;
- Mira 的社交策略偏 `ally` / `cooperate`;
- 玩家获得研究相关物品。

### 5. Sable 误导型社交任务

```text
Sable，你知道遗迹入口或者古物线索吗？
我听说入口在酒馆后巷，我接受你说的先查换岗记录。
```

观察：

- `social_intent` 包含 `redirect` / `deceive`;
- active goal 可表现为提取遗迹或古物线索；
- 记录可疑世界事件；
- 不调用 `unlock_location`；
- Sable 的欺骗只影响对话和可疑事件，不改写 canonical ruins access。

### 6. Character-agent 对比说明

同样问“地下遗迹入口在哪里？”时，展示 trace 中的差异：

- Lina：保护入口、测试信任、谨慎/试探；
- Ron：要求证据、公共安全优先；
- Mira：关注一手观察和研究价值；
- Sable：寻找可利用线索，语气可能友好但策略更具操控性。

强调：这些 belief / goal / plan / reflection 是开发者 trace 与内部状态，不应该以字段名或 JSON 形式出现在 NPC 台词里。

## 方案 B：React 玩家端

启动 API：

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
npm run dev
```

启动长期记忆 worker：

```powershell
python scripts/memory_worker.py --limit 5
```

打开：

```text
http://127.0.0.1:5173/
```

展示重点：

- 像素风地图、NPC 头像、任务、背包、记忆；
- 同一套 Agent workflow 驱动玩家端；
- 开发者 trace 面板可折叠查看。

## 方案 C：命令行稳定演示

如果现场 Web 不稳定，运行：

```powershell
python scripts/run_mvp_demo.py
```

该脚本会重置数据库并执行 8 轮四 NPC 演示，打印：

- intent；
- social intent / stance；
- belief stance / active goal / plan step；
- reflection；
- workflow steps；
- tool calls；
- memory policy；
- memory writes；
- state changes；
- final state。

## 导出实验结果

```powershell
python scripts/export_trace.py
```

导出文件：

```text
data/agent_trace_export.json
```

该文件用于报告附录、截图核验或 PPT 备份。Streamlit 页面显示 interaction log 时也会自动刷新同一路径。
