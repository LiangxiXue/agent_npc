# Autonomous Tick Next Slice Plan

本文档是外部仓库代码学习后的下一阶段实现草案。目标不是重做 `NPCMind`、`NarrativeEnvironment` 或 `ActionValidator`，而是在当前稳定基础上补出“主动 NPC agent 回合”。

## Current Baseline

当前仓库已经具备：

- `src/agent/environment.py`：`Observation`、`NPCAction`、`ActionResult`、`NarrativeEnvironment`。
- `src/agent/npc_mind.py`：belief、emotion、goal、plan、social strategy、reflection。
- `src/agent/action_validator.py`：非法 action 降级为安全 action。
- `src/agent/workflow.py`：玩家输入主回合已接入 `observe -> mind -> decision -> action -> validate -> execute -> reflect -> response -> trace`。
- `tests/test_npc_mind.py` 与 `tests/test_workflow.py`：覆盖 mind trace、response guard、environment trace、Sable 不越权等。

当前主要缺口：

- `world_events` 仍偏向 `content/created_at`，事件类型、来源、位置、可见性、payload 不充分。
- `Observation.visible_world_events` 读取最近全局事件，没有 location/visibility/inbox 过滤。
- 所有主流程仍由玩家输入触发，没有 `autonomous_tick`。
- 没有 `ActionCatalog`、`available_actions` 和显式 preconditions。
- plan state 主要靠 procedural memory facets 延续，没有专用 tick 结果或事件流。

## Target Vertical Slice

第一版主动 NPC 回合：

```text
world_event
-> visibility / npc_event_inbox
-> autonomous_tick
-> NPCMind
-> available_actions
-> ActionValidator
-> NarrativeEnvironment.execute
-> trace / proactive_message
```

设计原则：

- 不破坏现有玩家主回合。
- 自主回合作为并行入口，不把 world event 伪装成玩家发言。
- deterministic trigger/action 优先，LLM 只作为可选增强。
- 所有世界后果仍通过 `ActionValidator` 和 `NarrativeEnvironment.execute()`。
- trace 必须能解释 NPC 为什么看见事件、为什么能做某动作、为什么最终执行或降级。

## Data Model Draft

### WorldEvent

建议字段：

```python
WorldEvent(
    id: str,
    event_type: str,
    content: str,
    source_type: str,
    source_id: str | None,
    location_id: str | None,
    visibility: str,
    payload: dict,
    created_at: str,
)
```

`visibility` 第一版建议支持：

- `public`：所有 NPC 可见。
- `location`：同 location NPC 可见。
- `private`：只有 payload 指定 target/witness 可见。
- `npc_only`：只给指定 NPC 或 NPC group。

兼容策略：

- 保留既有 `content` 和 `created_at` 使用路径。
- 老事件没有结构化字段时按 `public` 或 legacy fallback 处理。

### NPCEventInboxItem

建议字段：

```python
NPCEventInboxItem(
    id: str,
    npc_id: str,
    event_id: str,
    seen: bool,
    relevance_score: float,
    reason: str,
    created_at: str,
)
```

`reason` 示例：

- `public`
- `same_location`
- `explicit_target`
- `witnessed_by`
- `relationship_relevant`

第一版 relevance 可 deterministic：target NPC > same location > public。

### ActionSpec

建议字段：

```python
ActionSpec(
    action_type: str,
    description: str,
    args_schema: dict,
    allowed_npcs: list[str] | str,
    preconditions: list[str],
    effects: list[str],
    forbidden_effects: list[str],
)
```

责任边界：

- `ActionCatalog` 负责根据 NPC、observation、trigger event 和 current state 产出 `available_actions`。
- `NPCMind` 或 action proposer 只能从 `available_actions` 中选择或构造 action。
- `ActionValidator` 继续作为最终安全层，防止 LLM 或规则遗漏导致越权。

### AutonomousTickResult

建议字段：

```python
AutonomousTickResult(
    npc_id: str,
    trigger_event_id: str | None,
    observation: dict,
    active_goal: dict | None,
    plan_step: dict | None,
    available_actions: list[dict],
    proposed_action: dict | None,
    validation: dict,
    action_result: dict,
    reflection: dict | None,
    proactive_message: str | None,
    trace_id: str,
)
```

该对象应成为 API 返回和 trace export 的共同基础。

## Proposed API

### POST /api/world/events

用途：

- 写入结构化 world event。
- 根据 visibility/location/target 派生 `npc_event_inbox`。
- 不运行 NPC mind，不生成 NPC response。

请求示例：

```json
{
  "event_type": "player_asked_ruins_too_early",
  "content": "玩家在未建立信任前追问遗迹入口。",
  "source_type": "player",
  "source_id": "player",
  "location_id": "market",
  "visibility": "location",
  "payload": {
    "quest_id": "ruins_access"
  }
}
```

### POST /api/npcs/{npc_id}/tick

用途：

- 选择一个未 seen 的 inbox item 或显式 `trigger_event_id`。
- 构造经过 visibility 过滤的 observation。
- 获取 `available_actions`。
- 运行现有 `NPCMind`、action proposal、validation、environment execution、reflection。
- 返回 `AutonomousTickResult`。

请求示例：

```json
{
  "trigger_event_id": "evt_123",
  "mode": "deterministic_first"
}
```

## Implementation Stages

### Stage 1: Structured World Events

目标：

- 扩展 world event schema，加入 `event_type`、`source_type`、`source_id`、`location_id`、`visibility`、`payload`。
- 保持旧 `content/created_at` 读取兼容。

主要测试：

- legacy event 仍能被现有 observation 读取。
- 新 event 能保存和读取完整 payload。

### Stage 2: Visibility And Inbox

目标：

- 新增 `npc_event_inbox`。
- 写入 world event 时按 visibility 派生 NPC inbox。
- `NarrativeEnvironment.observe()` 改为读取当前 NPC 可见事件。

主要测试：

- private event 不被无关 NPC 看到。
- location event 只被同地点 NPC 看到。
- public event 对所有 NPC 可见。
- inbox item seen 后不重复触发自主 tick。

### Stage 3: ActionCatalog And Available Actions

目标：

- 新增 `ActionSpec` 和 `ActionCatalog`。
- 根据 NPC 身份、observation、任务状态和 trigger event 返回 `available_actions`。
- 将 `available_actions` 写入 trace。

主要测试：

- Lina 可看到 trust-test 类 action。
- Ron 只有 badge evidence 满足后才出现推进 action。
- Sable 不出现 unlock/complete/修改他人 trust 的 action。
- 即使 proposed action 越权，`ActionValidator` 仍会降级。

### Stage 4: Autonomous Tick Workflow

目标：

- 新增 `run_autonomous_tick()` 或同等 workflow 入口。
- 复用现有 `NPCMind`、`ActionValidator`、`NarrativeEnvironment.execute()` 和 reflection。
- 第一版使用 deterministic action proposal，LLM action proposal 可后置。

核心场景：

- Lina 看到 `player_asked_ruins_too_early` 后主动进入 trust-test。
- Ron 只在证据充分时主动推进。
- Sable 可以误导或转移话题，但不能改写世界权限。

### Stage 5: API Integration

目标：

- 新增 `POST /api/world/events`。
- 新增 `POST /api/npcs/{npc_id}/tick`。
- 现有玩家 chat API 不改变。

主要测试：

- 通过 API 注入事件，再 tick 指定 NPC，返回 proactive message 和 trace id。
- 未触发 action 时返回 no-op tick result，而不是伪造对话。

### Stage 6: Trace / Eval / Demo

目标：

- 扩展 `/api/trace` 或 trace export，展示 autonomous trace。
- 增加 demo fixture 和评测场景。

trace 最低字段：

- trigger event；
- visible events；
- available actions；
- proposed action；
- validated action；
- action result；
- reflection；
- proactive message。

## Test Plan

下一阶段实现应至少覆盖：

- private event 不被无关 NPC 看到；
- Lina 看到 `player_asked_ruins_too_early` 后主动进入 trust-test；
- Ron 只在 badge evidence 满足后主动推进；
- Sable 可误导但不能 unlock/complete/改写他人 trust；
- trace 包含 trigger、visible_events、available_actions、proposed_action、validated_action、action_result、reflection；
- 现有玩家主回合测试继续通过。

## Non-Goals

第一版明确不做：

- 重写 `NPCMind`。
- 重写 `NarrativeEnvironment`。
- 用 LLM 直接决定世界事实或任务权限。
- 引入行为树、GOAP、大型 scheduler 或游戏引擎 entity 抽象。
- 复制 GPL/AGPL/LGPL 参考仓库代码。

## Recommended First PR Shape

建议第一组实现变更保持小范围：

1. schema/storage：结构化 world events 与 inbox。
2. environment：按 inbox/visibility 提供 visible events。
3. action catalog：少量 action spec 与 precondition。
4. workflow：`run_autonomous_tick` 返回 `AutonomousTickResult`。
5. API：两个新 endpoint。
6. tests：visibility、Lina/Ron/Sable、自主 trace。

完成后再考虑把 LLM action proposal 接入 `available_actions`。
