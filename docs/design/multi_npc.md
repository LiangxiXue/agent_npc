# Multi-NPC Prototype

当前多 NPC 改造目标是把原 Lina 单角色 demo 升级为可复用 Agent workflow，而不是一次性写完每个角色的完整任务树。

## Seeded NPCs

- `lina`：酒馆老板，保留完整 lost-key / ruins 主线。
- `ron`：镇门守卫，用于验证同一 workflow 能绑定不同 NPC 状态和任务。
- `mira`：遗迹学者，用于验证角色卡、任务和记忆隔离扩展。

每个 NPC 都有独立：

- `npcs` 状态；
- `quests` 主任务；
- `memories` 长期记忆；
- `recent_interactions` 短期上下文；
- `interaction_logs` trace 记录。

`world_events` 仍是共享世界事实。

## Current Behavior Boundary

Lina 仍拥有完整的确定性任务规则：

- start lost-key quest；
- complete lost-key quest；
- reveal / withhold ruins entrance。

Ron 和 Mira 当前使用通用 `general_conversation` 路径。这个路径不会误触发 Lina 的工具或任务，但可以通过 Memory Policy 写入玩家偏好等 NPC 私有长期记忆。

## UI

Streamlit 侧边栏提供 NPC selector。选中 NPC 后：

- 状态面板显示该 NPC 的关系值和主任务；
- memory preview 只检索该 NPC 的长期记忆；
- clear chat 只清理该 NPC 的短期上下文和日志；
- rebuild memory index 只刷新该 NPC 的 memory embedding。

## Tests

`tests/test_workflow.py` 覆盖：

- seed 数据包含 Lina/Ron/Mira；
- Ron/Mira 具有独立主任务；
- Ron 的长期记忆写入不会污染 Lina；
- FAISS backend 不可用时 semantic retrieval 自动 fallback。
