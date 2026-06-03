# External Pattern Library For Agent NPC

本文档基于 `docs/reference/external_agent_repo_learning_report.md` 和 `docs/design/autonomous_tick_next_slice_plan.md` 继续提炼参考仓库中的额外机制。它刻意不重复主线：

```text
world_event -> inbox -> autonomous_tick -> ActionCatalog -> trace
```

这里的每个条目都是可选模式，用于后续增强主动 NPC，而不是第一版必须全部实现的功能。许可证处理原则保持不变：GPL/AGPL/LGPL 仓库只借鉴概念、边界和测试思路，不复制代码。

## Selection Rule

- 每个参考仓库提炼 2 个独特机制。
- 每个机制都说明来源、原项目问题、`agent_npc` 改造、涉及文件、最小测试、课堂 demo 价值和是否进入本阶段实现。
- “进入本阶段实现”只表示建议纳入下一轮最小自主 tick 实现；“否”表示适合后续迭代或仅作设计参考。

## Player2NPC

### 1. Companion Lifecycle Lease

1. 来源仓库和文件/类名：`Goodbird-git/Player2NPC`，`CompanionManager.java`，`AutomatoneEntity.java`。
2. 原项目解决的问题：companion 不是永久在线脚本，而是需要 summon、fetch、teleport、dismiss 和 server tick 生命周期管理，避免掉线、重复生成或失去归属。
3. `agent_npc` 的具体改造：为 NPC 主动回合增加轻量 lifecycle 状态，如 `active`、`paused`、`dismissed`。`autonomous_tick` 遇到非 active NPC 时返回 no-op tick result，不执行 mind/action。
4. 新增/修改文件：
   - 修改：`src/storage/schema.sql`，增加 NPC runtime state 或复用 NPC metadata。
   - 修改：`src/agent/workflow.py`，tick 前检查 NPC lifecycle。
   - 修改：`src/api.py`，提供暂停/恢复或在 tick API 中返回 inactive reason。
5. 最小测试：`test_autonomous_tick_skips_paused_npc`：暂停 Lina 后注入相关事件，tick 返回 `status=no_op`、`reason=npc_paused`，inbox 不被错误消费。
6. 课堂 demo 价值：可演示“NPC 是世界中的角色，不是永远响应的聊天窗口”；暂停 Sable 后他不会继续主动误导。
7. 是否进入本阶段实现：否。第一版可先假设 NPC 全部 active；该机制适合自主 tick 稳定后补。

### 2. Embodied Resource Budget

1. 来源仓库和文件/类名：`Goodbird-git/Player2NPC`，`AutomatoneEntity.java` 中 inventory、interaction manager、hunger provider 相关边界。
2. 原项目解决的问题：NPC 行动受身体、背包、饥饿、距离和 interaction manager 限制，不能无限执行任务。
3. `agent_npc` 的具体改造：把复杂身体资源简化为 narrative budget，例如 `daily_proactive_budget`、`risk_tolerance`、`social_energy`。自主 tick 超过预算时只允许 memory-only tick 或 no-op。
4. 新增/修改文件：
   - 新增：`src/agent/npc_runtime_state.py`，保存预算与当天消耗。
   - 修改：`src/agent/action_catalog.py`，把预算作为 action precondition 输入。
   - 修改：`tests/test_autonomous_tick.py`，覆盖预算耗尽。
5. 最小测试：`test_budget_exhaustion_allows_memory_only_tick`：Lina 当日主动消息预算用尽后，仍能记录 reflection，但不生成 proactive message。
6. 课堂 demo 价值：展示 NPC 不会刷屏，也能解释“为什么这次没有主动发言”。
7. 是否进入本阶段实现：是。建议只实现一个简单 `proactive_message_budget`，不要引入完整资源系统。

## PlayerEngine

### 3. Conversation Queue With Priority

1. 来源仓库和文件/类名：`Goodbird-git/PlayerEngine`，`ConversationManager.java`。
2. 原项目解决的问题：玩家消息、AI 角色消息和高优先级消息不能直接抢占输出，需要排队、按距离和优先级处理，避免对话混乱。
3. `agent_npc` 的具体改造：新增 `proactive_message_queue`，autonomous tick 只入队主动消息；玩家主回合或 API 再按优先级取出展示。高优先级任务提醒可插队，低优先级闲聊可延后。
4. 新增/修改文件：
   - 修改：`src/storage/schema.sql`，增加 `proactive_messages`。
   - 新增：`src/agent/proactive_queue.py`。
   - 修改：`src/api.py`，增加读取/ack 主动消息的接口或在 bootstrap 中返回 pending messages。
5. 最小测试：`test_proactive_messages_are_ordered_by_priority_and_created_at`：同一 NPC 两条消息按 priority 再按时间返回。
6. 课堂 demo 价值：可以在前端展示“NPC 主动消息弹出”，比 tick 返回文本更接近游戏体验。
7. 是否进入本阶段实现：否。第一版可让 tick 直接返回 `proactive_message`；队列适合前端接入阶段。

### 4. Task Lifecycle State

1. 来源仓库和文件/类名：`Goodbird-git/PlayerEngine`，`UserTaskChain.java`。
2. 原项目解决的问题：任务有 active、idle、finish、stop 和 callback，不是一次性函数调用；任务切换需要明确生命周期。
3. `agent_npc` 的具体改造：为主动 NPC 的 plan step 增加 lifecycle：`pending`、`active`、`blocked`、`completed`、`cancelled`。当 precondition 不满足时记录 `plan_blocker`，而不是反复提议同一 action。
4. 新增/修改文件：
   - 新增：`src/agent/plan_state.py`。
   - 修改：`src/agent/npc_mind.py`，读取/写入 plan lifecycle summary。
   - 修改：`src/agent/workflow.py`，tick result 写入 blocker。
5. 最小测试：`test_plan_blocker_prevents_repeated_invalid_proposal`：Ron 缺少 badge evidence 时记录 blocker，下一次 tick 不再重复推进同一 action。
6. 课堂 demo 价值：能解释“Ron 为什么没有推进任务”，让 agent 看起来像在计划，而不是随机沉默。
7. 是否进入本阶段实现：是。建议只做 `plan_blocker` 字段和测试，不做完整 task chain。

## hello-agents Cyber Town

### 5. Affection Delta Ledger

1. 来源仓库和文件/类名：`datawhalechina/hello-agents`，`docs/chapter15/Chapter15-Building-Cyber-Town.md` 中 affection system。
2. 原项目解决的问题：玩家和 NPC 的关系变化需要可解释，不应只是最终好感度数字。
3. `agent_npc` 的具体改造：在关系变动时记录 delta ledger：`npc_id`、`player_id`、`metric`、`delta`、`reason_event_id`、`evidence_text`。trace 展示“这次为什么加/减 trust”。
4. 新增/修改文件：
   - 修改：`src/storage/schema.sql`，增加 `relationship_deltas`。
   - 修改：`src/agent/environment.py` 或现有任务/关系更新路径，写入 delta reason。
   - 修改：`tests/test_workflow.py`，验证关系变动有证据。
5. 最小测试：`test_relationship_delta_records_reason_event`：Lina trust 增加时必须有 `reason_event_id` 或 `evidence_text`。
6. 课堂 demo 价值：关系系统可视化更强，适合报告中展示“非黑箱关系变化”。
7. 是否进入本阶段实现：否。当前关系约束已有测试，本阶段优先做主动回合。

### 6. Memory-Only Tick

1. 来源仓库和文件/类名：`datawhalechina/hello-agents`，`MemoryManager`、`WorkingMemory`、`EpisodicMemory` 分层设计。
2. 原项目解决的问题：agent 不是每次感知都要说话，有些事件只应更新记忆或短期状态。
3. `agent_npc` 的具体改造：`autonomous_tick` 支持 `outcome=memory_only`。NPC 看见事件后可写 reflection 或更新 belief，但不生成 proactive message、不执行世界 action。
4. 新增/修改文件：
   - 修改：`src/agent/workflow.py`，tick result 支持 memory-only outcome。
   - 修改：`src/agent/npc_mind.py`，为低强度事件返回 reflection-only decision。
   - 修改：`tests/test_autonomous_tick.py`。
5. 最小测试：`test_low_relevance_event_creates_memory_only_tick`：public rumor relevance 低时 Lina 记录 visible event，但 `proactive_message is None`。
6. 课堂 demo 价值：展示 NPC 有内心变化但不打扰玩家，提高可信度。
7. 是否进入本阶段实现：是。它能防止主动系统变成刷屏系统。

## Godot Player2 SDK

### 7. Conversation Summary Compaction

1. 来源仓库和文件/类名：`elefant-ai/player2-ai-npc-godot`，`Player2AINPC.gd` 中 conversation history save/load 和 summary trimming。
2. 原项目解决的问题：长期对话不能无限塞进上下文，需要把旧对话压缩成 summary。
3. `agent_npc` 的具体改造：对主动 tick 的 trace 和 conversation history 增加摘要层。旧 proactive messages 不再全部进入 prompt，只保留最近若干条和 `npc_autonomous_summary`。
4. 新增/修改文件：
   - 修改：`src/agent/context_builder.py` 或现有 retrieval/context 组装文件。
   - 修改：`src/storage/schema.sql`，增加 autonomous summary memory facet 或复用 memory facets。
   - 修改：`tests/test_workflow.py`，覆盖旧主动消息不污染 prompt。
5. 最小测试：`test_autonomous_history_is_summarized_before_prompt_growth`：超过阈值后 prompt context 不包含全部旧 proactive messages，但包含 summary。
6. 课堂 demo 价值：可解释“NPC 记得过去主动行为，但上下文不会爆炸”。
7. 是否进入本阶段实现：否。第一版事件量小，先不做压缩。

### 8. Runtime Signal Hooks

1. 来源仓库和文件/类名：`elefant-ai/player2-ai-npc-godot`，`Player2AINPC.gd` 中 `thinking_began`、`tool_called`、`chat_received` signals。
2. 原项目解决的问题：游戏前端需要知道 NPC 什么时候思考、调用工具、收到回复，以便展示状态和调试。
3. `agent_npc` 的具体改造：为自主 tick 增加 trace events：`tick_started`、`observation_built`、`action_proposed`、`action_validated`、`message_emitted`、`tick_finished`。这不是 UI signal，而是结构化 debug timeline。
4. 新增/修改文件：
   - 新增：`src/agent/tick_trace.py`。
   - 修改：`src/agent/workflow.py`，在关键阶段 append timeline event。
   - 修改：`tests/test_autonomous_tick.py`，断言 timeline 顺序。
5. 最小测试：`test_autonomous_tick_trace_has_ordered_timeline`：trace event names 按固定顺序出现。
6. 课堂 demo 价值：Streamlit/trace 页面可逐步展示 NPC 为什么行动，适合答辩。
7. 是否进入本阶段实现：是。它和 autonomous trace 互补，但不重复主线字段。

## Unity Player2 SDK

### 9. Per-NPC Function Surface Cache

1. 来源仓库和文件/类名：`elefant-ai/unity-player2-sdk`，`NpcManager.cs`、`Player2Npc.cs`。
2. 原项目解决的问题：每个 NPC spawn 时携带自己的 commands，运行时不需要每次重新扫描全局函数。
3. `agent_npc` 的具体改造：为每个 NPC 缓存 `action_surface_hash` 和最近一次 `available_actions` 版本。action catalog 未变化时，tick 可复用 spec 列表，只重新计算动态 preconditions。
4. 新增/修改文件：
   - 修改：`src/agent/action_catalog.py`。
   - 新增：`src/agent/action_surface_cache.py`。
   - 修改：`tests/test_action_catalog.py`。
5. 最小测试：`test_action_surface_cache_invalidates_when_catalog_version_changes`：catalog version 变化后缓存失效，否则复用静态 action spec。
6. 课堂 demo 价值：不明显；主要是性能和工程稳定性。
7. 是否进入本阶段实现：否。当前 action 数量小，先不做缓存。

### 10. Function Handler Result Envelope

1. 来源仓库和文件/类名：`elefant-ai/unity-player2-sdk`，`NpcManager.cs` 中 function handler 责任边界。
2. 原项目解决的问题：NPC 调用函数后，游戏侧需要统一返回成功、失败、参数错误或副作用结果。
3. `agent_npc` 的具体改造：在 `ActionResult` 外增加 action handler envelope 字段，如 `handler_status`、`precondition_failures`、`side_effect_ids`。这能区分“action 不可用”“执行失败”“执行成功但无世界变化”。
4. 新增/修改文件：
   - 修改：`src/agent/environment.py`，扩展 `ActionResult` 序列化字段。
   - 修改：`src/agent/action_validator.py`，输出 precondition failure reason。
   - 修改：`tests/test_npc_mind.py`、`tests/test_workflow.py`。
5. 最小测试：`test_action_result_distinguishes_blocked_from_no_effect`：Sable 越权返回 `handler_status=blocked`，普通 no-op 返回 `handler_status=no_effect`。
6. 课堂 demo 价值：trace 更容易讲清楚“系统没有执行坏动作，不是 NPC 没反应”。
7. 是否进入本阶段实现：是。建议只补状态枚举和原因，不扩展复杂 handler 框架。

## CobbleBrain

### 11. Trigger Cooldown

1. 来源仓库和文件/类名：`VcGameDev/CobbleBrain`，`WorldEventsSystem.kt` 中按间隔检查、pending/active event 和状态推进。
2. 原项目解决的问题：world event 如果每个 tick 都满足条件，会重复触发，导致刷屏或重复生成事件。
3. `agent_npc` 的具体改造：为 trigger/npc/action 增加 cooldown key，例如 `npc_id:event_type:action_type`。cooldown 未过期时 tick 返回 no-op 或 memory-only。
4. 新增/修改文件：
   - 新增：`src/agent/cooldowns.py`。
   - 修改：`src/storage/schema.sql`，增加 `npc_cooldowns`。
   - 修改：`src/agent/workflow.py`，tick 前后读取/写入 cooldown。
5. 最小测试：`test_same_trigger_respects_cooldown`：Lina 对同一类 ruins early question 第一次主动回应，第二次在 cooldown 内不再发 proactive message。
6. 课堂 demo 价值：避免演示时重复点击 tick 产生重复台词，显著提升可信度。
7. 是否进入本阶段实现：是。建议纳入第一版，规则保持简单。

### 12. Pending-To-Active Event State

1. 来源仓库和文件/类名：`VcGameDev/CobbleBrain`，`WorldEventsSystem.kt` 中 pending raids、active raids。
2. 原项目解决的问题：世界事件需要从候选状态进入活动状态，再被解决或超时，而不是写入日志后立刻完成。
3. `agent_npc` 的具体改造：对少数剧情事件支持 `event_status=pending|active|resolved|expired`。例如 ruins trust-test 可先 pending，Lina tick 后 active，玩家完成条件后 resolved。
4. 新增/修改文件：
   - 修改：`src/storage/schema.sql`，给 world events 增加 status。
   - 修改：`src/agent/environment.py`，执行 action 时更新 status。
   - 修改：`tests/test_autonomous_tick.py`。
5. 最小测试：`test_trust_test_event_moves_from_pending_to_active`：注入 pending event 后 Lina tick 将其标记 active，不直接 complete。
6. 课堂 demo 价值：可展示剧情事件生命周期，比一次性事件更像任务推进。
7. 是否进入本阶段实现：否。第一版只需要 inbox seen 和 action result；event status 可后续补。

## MindOfTheColony

### 13. Event History Pruning

1. 来源仓库和文件/类名：`elefant-ai/MindOfTheColony`，`ColonyEventManager.java`。
2. 原项目解决的问题：event history 需要保留近期上下文，但不能无限增长或污染 agent context。
3. `agent_npc` 的具体改造：为 `world_events` 和 autonomous trace 增加 pruning policy：保留最近 N 条可见事件进入 observation，数据库仍保留完整记录或按时间归档。
4. 新增/修改文件：
   - 修改：`src/agent/environment.py`，`observe()` 限制 visible event count。
   - 修改：`src/config.py` 或配置文件，增加 `visible_event_limit`。
   - 修改：`tests/test_autonomous_tick.py`。
5. 最小测试：`test_observation_visible_events_are_pruned_to_limit`：写入 20 条 public event，observation 只返回最近配置数量。
6. 课堂 demo 价值：trace 简洁，不会让观众看到一屏过期事件。
7. 是否进入本阶段实现：是。实现成本低，直接保护 prompt/trace 可读性。

### 14. Evaluator Context Object

1. 来源仓库和文件/类名：`elefant-ai/MindOfTheColony`，`EventContext.java`。
2. 原项目解决的问题：event evaluator 如果直接读全局状态，会难测、难复现；显式 context 让评估规则清楚。
3. `agent_npc` 的具体改造：给 trigger/precondition 函数传入 `TickContext`，包含 `npc_id`、`trigger_event`、`visible_events`、`task_state`、`relationship_state`、`now`。规则函数不直接查数据库。
4. 新增/修改文件：
   - 新增：`src/agent/tick_context.py`。
   - 修改：`src/agent/action_catalog.py`，precondition 接收 `TickContext`。
   - 修改：`tests/test_action_catalog.py`。
5. 最小测试：`test_precondition_uses_tick_context_without_database_access`：用构造出的 `TickContext` 判断 Ron badge evidence，不需要初始化完整 API。
6. 课堂 demo 价值：报告中容易画清楚“规则输入是什么”，也方便解释 deterministic guard。
7. 是否进入本阶段实现：是。它能让 action precondition 测试更稳。

## project-lunar

### 15. Knowledge Leak Test

1. 来源仓库和文件/类名：`horizonfps/project-lunar`，`test_npc_mind_engine.py` 中 knowledge boundary、scene presence 测试。
2. 原项目解决的问题：NPC 容易因为全局状态或 prompt 泄漏知道不该知道的信息。
3. `agent_npc` 的具体改造：增加专门的 knowledge leak 测试矩阵：private event、different location event、Sable secret、Ron badge evidence 均不得泄漏给无关 NPC。
4. 新增/修改文件：
   - 新增：`tests/test_event_visibility.py`。
   - 修改：`src/agent/environment.py`，确保 observation 来源只走 visibility/inbox。
   - 修改：`src/agent/response.py`，防止 response 使用不可见 event。
5. 最小测试：`test_private_event_does_not_enter_observation_or_response_context`：Mira 私有事件不会进入 Lina observation，也不会出现在 response constraints。
6. 课堂 demo 价值：这是“角色不是全知旁白”的关键证明，适合答辩。
7. 是否进入本阶段实现：是。它是主动 NPC 系统的安全底线。

### 16. Transient State Decay

1. 来源仓库和文件/类名：`horizonfps/project-lunar`，`npc_mind_engine.py`。
2. 原项目解决的问题：feeling 等临时状态如果不衰减，NPC 会长期保持一次事件造成的情绪。
3. `agent_npc` 的具体改造：为 `NPCMind` 的 emotion 或 urgency 增加 tick-based decay。自主 tick 后如果没有新强事件，降低 `concern`、`suspicion` 或 proactive urgency。
4. 新增/修改文件：
   - 修改：`src/agent/npc_mind.py`，增加 decay 方法或在 perceive 前应用。
   - 修改：`tests/test_npc_mind.py`，覆盖多次 no-op tick 后 emotion 降低。
5. 最小测试：`test_emotion_urgency_decays_across_no_op_ticks`：Lina 一次低信任追问后 concern 上升，后续无新事件 tick 后逐步下降。
6. 课堂 demo 价值：NPC 情绪动态更可信，但演示成本较高。
7. 是否进入本阶段实现：否。当前主线先验证主动行为闭环，emotion decay 后续再加。

## hyperforge

### 17. Manifest Validation And Backup

1. 来源仓库和文件/类名：`PlayHyperia/hyperforge`，`packages/asset-forge/server/services/ManifestService.ts`。
2. 原项目解决的问题：NPC、world areas、quests 等内容资产需要 schema validation 和备份，避免配置损坏。
3. `agent_npc` 的具体改造：当 action specs、world areas、NPC locations 增多后，把静态配置迁到 `data/manifests/*.json`，加载时校验并在修改前备份。
4. 新增/修改文件：
   - 新增：`data/manifests/actions.json`。
   - 新增：`src/content/manifest_loader.py`。
   - 新增：`tests/test_manifest_loader.py`。
5. 最小测试：`test_invalid_action_manifest_reports_field_error`：缺少 `action_type` 时 loader 返回明确错误，不启动 runtime。
6. 课堂 demo 价值：可以展示内容系统专业性，但对主动 NPC 第一版价值有限。
7. 是否进入本阶段实现：否。第一版保持 Python 内部 registry 更稳。

### 18. Available Actions Excluded Report

1. 来源仓库和文件/类名：`PlayHyperia/hyperforge`，`ManifestService.ts` 中 definitions validation 思路。
2. 原项目解决的问题：内容项不只要知道“哪些有效”，还要能解释“哪些因为 schema 或条件不满足被排除”。
3. `agent_npc` 的具体改造：`ActionCatalog` 返回 `available_actions` 的同时返回 `available_actions_excluded`，每项包含 `action_type`、`reason`、`failed_preconditions`。这不是重复主线，而是解释候选动作排除原因。
4. 新增/修改文件：
   - 修改：`src/agent/action_catalog.py`。
   - 修改：`src/agent/workflow.py`，trace 写入 excluded 列表。
   - 新增：`tests/test_action_catalog.py`。
5. 最小测试：`test_excluded_actions_include_failed_precondition_reason`：Ron 未满足 badge evidence 时，推进 action 出现在 excluded，reason 为缺少证据。
6. 课堂 demo 价值：调试台能展示“为什么不能做”，比只显示可用动作更有说服力。
7. 是否进入本阶段实现：是。它能直接提升 trace/eval 质量。

## Defold Player2 Plugin

### 19. Pollable Response Mailbox

1. 来源仓库和文件/类名：`elefant-ai/player2-ai-npc-defold`，README 中 `ainpc.npc_responses`。
2. 原项目解决的问题：游戏循环不一定同步等待 NPC 回复，需要可以轮询 response。
3. `agent_npc` 的具体改造：为 proactive message 增加 pollable mailbox。前端可以定期拉取未读 NPC 主动消息，而不是每次 tick 请求立即展示。
4. 新增/修改文件：
   - 新增：`src/agent/proactive_mailbox.py`。
   - 修改：`src/api.py`，增加 `GET /api/npcs/messages` 或 bootstrap 返回未读消息。
   - 新增：`tests/test_proactive_mailbox.py`。
5. 最小测试：`test_polling_returns_unread_messages_once`：第一次 poll 返回消息并标记 read，第二次不重复返回。
6. 课堂 demo 价值：前端可自然出现“Lina 主动找你说话”的效果。
7. 是否进入本阶段实现：否。和 PlayerEngine queue 类似，等 tick 直返消息稳定后再做。

### 20. NPC Kill / Cleanup Guard

1. 来源仓库和文件/类名：`elefant-ai/player2-ai-npc-defold`，README 中 `ainpc.npc_kill`。
2. 原项目解决的问题：NPC 被移除后，历史请求或异步回复不应继续作用于已不存在的 NPC。
3. `agent_npc` 的具体改造：为 NPC runtime 增加 `deleted` 或 `disabled` guard。tick、message poll、event inbox 消费遇到 disabled NPC 时返回 no-op，并保留 audit trace。
4. 新增/修改文件：
   - 修改：`src/storage/schema.sql`，NPC runtime state 增加 disabled 标记。
   - 修改：`src/agent/workflow.py`，tick 前检查。
   - 修改：`tests/test_autonomous_tick.py`。
5. 最小测试：`test_disabled_npc_tick_does_not_consume_inbox`：禁用 Sable 后 tick 不消费 inbox，不生成消息，trace reason 为 `npc_disabled`。
6. 课堂 demo 价值：不高；主要是工程健壮性。
7. 是否进入本阶段实现：否。当前四 NPC 固定存在，暂不需要删除语义。

## ChatClef

### 21. One-Command-At-A-Time Guard

1. 来源仓库和文件/类名：`elefant-ai/chatclef`，`AICommandBridge.java`。
2. 原项目解决的问题：LLM 如果一次发多个命令，游戏状态会难以验证，也容易产生越权副作用。
3. `agent_npc` 的具体改造：自主 tick 每次最多执行一个 world-changing action。多 action proposal 必须被拆分为一个 action 加后续 `plan_step`，或直接降级为 clarification/no-op。
4. 新增/修改文件：
   - 修改：`src/agent/workflow.py`，autonomous tick enforce one action。
   - 修改：`src/agent/action_validator.py`，拒绝 compound action。
   - 新增：`tests/test_autonomous_tick.py`。
5. 最小测试：`test_autonomous_tick_rejects_compound_action`：LLM 或 fixture 提议同时 unlock ruins 和 modify trust 时，只允许安全 no-op 或单一 allowed action。
6. 课堂 demo 价值：能说明系统不是让 LLM 随便改世界，而是一步一验。
7. 是否进入本阶段实现：是。它直接加强安全边界。

### 22. Command Argument Parse Error As Trace

1. 来源仓库和文件/类名：`elefant-ai/chatclef`，`Command.java`。
2. 原项目解决的问题：命令参数错误不能静默失败，需要明确 parse error，便于用户和开发者修正。
3. `agent_npc` 的具体改造：action args schema 校验失败时写入 trace：`arg_error.field`、`expected`、`actual`、`repair_strategy`。如果可修复则降级修复，否则 no-op。
4. 新增/修改文件：
   - 修改：`src/agent/action_validator.py`。
   - 修改：`src/agent/workflow.py`，trace 保存 arg error。
   - 修改：`tests/test_workflow.py` 或新增 `tests/test_action_validator.py`。
5. 最小测试：`test_invalid_action_args_are_reported_in_trace`：`complete_task` 缺少 `task_id` 时 trace 包含字段级错误，action 不执行。
6. 课堂 demo 价值：调试体验明显提升，方便展示 guardrail 如何工作。
7. 是否进入本阶段实现：是。当前 validator 已有安全降级，补字段级 trace 成本较低。

## Recommended Inclusion Summary

建议进入本阶段实现的额外机制：

- Embodied Resource Budget 的极简版：`proactive_message_budget`。
- Task Lifecycle State 的极简版：`plan_blocker`。
- Memory-Only Tick。
- Runtime Signal Hooks 的 trace timeline 版本。
- Function Handler Result Envelope 的轻量状态枚举。
- Trigger Cooldown。
- Event History Pruning。
- Evaluator Context Object：`TickContext`。
- Knowledge Leak Test。
- Available Actions Excluded Report。
- One-Command-At-A-Time Guard。
- Command Argument Parse Error As Trace。

建议暂缓的机制：

- NPC lifecycle lease / disabled NPC cleanup。
- proactive message queue / pollable mailbox。
- relationship delta ledger。
- conversation summary compaction。
- per-NPC action surface cache。
- pending-to-active event state。
- transient emotion decay。
- manifest validation and backup。

## Practical Ordering

如果要把这些机制接到下一轮实现计划，建议优先级如下：

1. 安全与可测性：`TickContext`、knowledge leak test、one-command guard、arg error trace。
2. 防刷屏与 no-op：cooldown、memory-only tick、proactive budget、event pruning。
3. 可解释性：available actions excluded、handler result envelope、trace timeline、plan blocker。
4. 后续前端/内容系统：message queue/mailbox、manifest、summary compaction、relationship delta。

## Current Implementation Status

本轮已进入实现的机制：

- `proactive_message_budget` 的轻量版：同一 NPC 有未读 proactive message 时跳过新消息；
- `plan_blocker`：unavailable action 的 failed precondition reason 会进入 `npc_plans.blocker`；
- `memory-only tick`：可见事件可只写 memory candidate/reflection，不发消息；
- trace timeline：`tick_started`、`observation_built`、`action_surface_built`、`llm_decision_received`、`action_validated`、`tick_finished`；
- handler result envelope：tick trace 区分 `allowed`、`rejected_by_available_actions`、`rejected_invalid_args`、`rejected_one_command_at_a_time`、`skipped_by_cooldown`、`skipped_by_budget`、`paused_memory_only`、`no_op`；
- trigger cooldown：`npc_id:event_type:action_type`；
- `TickContext` 的实际等价物：autonomous LLM payload 显式包含 npc/player/quest/trigger/visible events/memories/active plan/action surface；
- knowledge leak tests：private event 不进入无关 NPC observation；
- available actions excluded report；
- one-command-at-a-time guard；
- command argument error trace；
- proactive message mailbox；
- minimal lifecycle：`active`、`paused`、`disabled`。
