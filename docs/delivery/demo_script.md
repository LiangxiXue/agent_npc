# MVP Demo Script

本脚本用于课堂展示 Memory-Driven Interactive Character Agent 的最小可运行版本。

## 展示目标

证明系统不是普通聊天机器人，而是具备：

- SQLite 持久化状态；
- 短期 / 长期记忆分层；
- 类型化长期记忆；
- Memory Policy；
- 结构化决策；
- 工具调用；
- 状态变化；
- 可解释执行轨迹。

## 演示步骤

### 1. 启动应用

```bash
streamlit run app.py
```

打开页面后，点击左侧 `Reset SQLite Demo Data`，保证从初始状态开始。

### 2. 低信任询问遗迹入口

输入：

```text
我想打听一下地下遗迹的入口。
```

预期现象：

- `intent` 为 `withhold_ruins_entrance`；
- Lina 拒绝透露入口；
- 无长期记忆写入，或 trace 中显示 `memory_policy` 不写入长期记忆的原因；
- `trust` 不提升；
- `underground_ruins_entrance` 不会出现在已解锁地点中。

### 3. 归还钥匙

输入：

```text
我把你丢失的钥匙找回来了。
```

预期现象：

- `intent` 为 `complete_lost_key_quest`；
- 行为工具调用包括 `update_trust`、`update_affection`、`update_quest_status`、`give_item`；
- `memory_policy` 写入 `quest`、`event`、`relationship` 类型长期记忆；
- Lina 的 `trust` 从 20 变为 30；
- Lina 的 `affection` 从 30 变为 38；
- `lost_key` 任务状态变为 `completed`；
- 玩家背包获得 `tavern_discount_coupon`。

### 4. 基于记忆和状态再次询问入口

输入：

```text
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

预期现象：

- `intent` 为 `reveal_ruins_entrance`；
- 系统检索到玩家帮助 Lina 的长期记忆，并显示 `retrieval_score` / `retrieval_reason`；
- 工具调用 `unlock_location`；
- 玩家已解锁地点中出现 `underground_ruins_entrance`。

## 备用命令行演示

如果现场 Web 演示不稳定，可以运行：

```bash
python scripts/run_mvp_demo.py
```

该命令会自动重置数据库，连续执行三轮交互，并打印每轮的 intent、workflow、工具调用和状态变化。

## 导出实验结果

Web 页面中可以点击 `Download Trace JSON` 导出当前 trace。也可以运行：

```bash
python scripts/export_trace.py
```

导出的 `data/agent_trace_export.json` 可用于报告附录、截图核验或 PPT 备份。Web 页面显示 interaction log 时也会自动把同一份 trace 写入 `data/agent_trace_export.json`。
