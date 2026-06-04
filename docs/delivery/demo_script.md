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

## 方案 D：主动 NPC Agent 演示

目标：证明 NPC 不只是在玩家输入后回复，而是能响应世界事件并主动产生意图、计划、消息和 trace。

### 1. 启动 API

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

### 2. 运行三场景脚本

真实 LLM：

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "<key>"
python scripts/run_autonomous_llm_demo.py
```

无 LLM smoke：

```powershell
python scripts/run_autonomous_llm_demo.py --mock
```

### 3. 展示 Lina 主动试探

观察输出：

- `trigger_event_id`;
- `available_actions` 包含 `offer_minor_task`;
- `unavailable_actions` 中 `reveal_partial_lore` 的原因是 trust below 60;
- `llm_decision.goal = test_player_trust`;
- `validation.status = allowed`;
- `state_diff` 显示低风险任务进入 `in_progress`;
- `proactive_message` 已入 mailbox。

打开：

```text
http://127.0.0.1:8000/api/trace/autonomous/{tick_log_id}?format=html
```

### 4. 展示 Ron 证据门控

观察：

- 输入事件是 `badge_evidence_verified`;
- `grant_conditional_access` 只有证据满足时可选;
- 环境侧更新 gate badge 任务状态;
- 没有解锁遗迹入口。

### 5. 展示 Sable 安全误导

观察：

- Sable 的 available actions 是 `mislead_player` / `redirect_to_false_clue` / `ask_leading_question` / `probe_player_secret`;
- 每个 action 的 `forbidden_effects` 包含 `unlock_location`、`complete_quest`、`modify_other_npc_trust`、`grant_gate_access`、`rewrite_lore_fact`;
- 如果 LLM 试图选 `unlock_location`，trace 会显示 `rejected_by_available_actions`，不会改世界事实。

## 方案 E：遗迹主线活世界 Demo

目标：展示同一条遗迹主线如何把玩家动作、世界事件、NPC 日常、主动 tick、LLM 受约束剧情导演和可变结局连起来。

### 1. 运行 deterministic smoke

```powershell
python scripts/run_living_world_demo.py --mock
```

观察输出：

- `player_actions` 显示玩家调查酒馆后巷、提交守卫记录、提交 Mira 田野笔记、在 Sable 摊位传播传闻、等待 NPC 日常推进；
- `npc_ticks` 显示 Lina、Ron、Mira、Sable 各自选择不同 action；
- `final_arc.arc_outcome` 在 `guardian_advantage`、`research_advantage`、`sable_advantage`、`chaotic_lockdown` 之一；
- `proactive_messages` 展示 NPC 主动消息；
- `player_state.unlocked_locations` 不应包含 `underground_ruins_entrance`，除非未来显式设计允许解锁。

### 2. 讲解链路

```text
player action
-> scene object state
-> world event
-> npc_event_inbox
-> autonomous tick
-> available_actions
-> constrained LLM decision
-> environment validation
-> arc director
-> proactive message / trace
```

### 3. 展示重点

- 程序拥有事实和状态：场景对象、任务、地点、主线阶段由数据库和校验器控制；
- LLM 拥有受约束自由度：它可以选择 NPC 策略和结局倾向，但不能直接解锁地点或完成任务；
- Sable 可以制造 `sable_advantage` 倾向，但仍不能调用 `unlock_location`；
- Ron 可以升级风险或巡逻，但不会凭空完成其他 NPC 的任务；
- Mira 可以推动 `research_advantage`，但必须基于具体观察和笔记。

## 方案 F：Traveler Living World 验收 Demo

运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 20 --mock --max-npc-ticks 4 --idle-npc-probe --stop-on-outcome --export-dir data/traces/living_world_acceptance
```

`--mock` 会让 Traveler 与 NPC autonomous tick 都走离线 deterministic 路径，不需要真实 LLM。

验收重点：

- final arc phase 为 `resolved`；
- final arc outcome 非空；
- 导出 JSON 和 Markdown；
- JSON 中能看到多地点探索、NPC tick 目标以及 round / Traveler 内部 timings。
