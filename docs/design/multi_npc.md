# Multi-NPC Prototype

当前多 NPC 版本已经不只是入口验证，而是四个 NPC 共用同一套 Agent workflow，并各自拥有独立任务、记忆、设定检索和社交行为边界。

## Seeded NPCs

| NPC | Role | Primary quest | Social role |
| --- | --- | --- | --- |
| `lina` | Tavern Owner | `lost_key` | 谨慎保护遗迹入口，玩家赢得信任后合作 |
| `ron` | Town Guard | `gate_badge` | 程序化、重证据，面对遗迹通行请求先 probe |
| `mira` | Ruins Scholar | `ancient_notes` | 重视一手观察和研究证据，倾向 ally/cooperate |
| `sable` | Traveling Relic Broker | `relic_tip` | 表面友好，`hidden_alignment='exploit_ruins'`，会 redirect/deceive |

每个 NPC 都有独立：

- `npcs` 状态；
- `quests` 主任务；
- `memories` 长期记忆；
- `recent_interactions` 短期上下文；
- `interaction_logs` trace；
- NPC-specific lore documents。

`world_events` 是共享世界事实。

## Quest Lines

| Quest | NPC | Start signal | Completion signal | Reward / effect |
| --- | --- | --- | --- | --- |
| `lost_key` | Lina | 询问或主动寻找钥匙 | 找回/归还钥匙 | trust/affection 上升，获得 `tavern_discount_coupon` |
| `gate_badge` | Ron | 城门、巡逻、守卫徽章、记录 | 徽章/登记册/签名等证据 | trust 上升，获得 `guard_route_note` |
| `ancient_notes` | Mira | 遗迹铭文、田野笔记、观察方法 | 三角符号、封闭石门、一手观察 | 获得 `ruins_research_note` |
| `relic_tip` | Sable | 遗迹入口、古物、其他 NPC 线索 | 接受或透露敏感入口线索 | 记录可疑世界事件，不解锁遗迹入口 |

## Program-Owned Task Safety

所有任务都经过 `apply_task_state_machine()`：

- 只能从 `not_started` 开始任务；
- 只能从 `in_progress` 完成任务；
- 完成任务必须有 NPC-specific evidence；
- 当前 NPC 不能推进其他 NPC 的任务；
- 被拦截的 decision 会降级为 `probe_for_evidence`，并在 trace 中记录 `state_machine.blocked`。

## Social Strategy

Decision 输出包含：

```text
social_intent: cooperate | conceal | oppose | probe | ally | deceive | redirect | accuse
social_stance:
  target
  attitude
  intensity
  reason
```

这层用于表达“欺骗、拉拢、厌恶、反对”等社会动作，但不直接拥有状态写入权。工具调用仍由 allowlist、schema 和业务规则约束。

## UI Behavior

Streamlit 调试台和 React 玩家端都支持 NPC 选择。选中 NPC 后：

- 状态面板显示该 NPC 的关系值和主任务；
- memory preview 只检索该 NPC 的长期记忆；
- clear chat 只清理该 NPC 的短期上下文和日志；
- memory embedding rebuild 可按 NPC 刷新；
- trace 面板显示该 NPC 的 retrieved lore/memory、decision、tools、state changes。

## Tests

`tests/test_workflow.py` 覆盖：

- seed 数据包含 Lina/Ron/Mira/Sable；
- 四个 NPC 均有独立主任务；
- Ron、Mira、Sable 任务可以 start 和 complete；
- Sable 可以 deception/redirect，但不能解锁遗迹入口；
- 跨 NPC 任务更新会被状态机阻止；
- 未开始任务不能直接完成；
- 多 NPC 记忆隔离和 lore 检索生效。
