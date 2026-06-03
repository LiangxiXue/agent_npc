# External Agent Repo Learning Report

本文档记录对参考 GitHub 仓库的代码级学习结果，并把可迁移模式映射到当前 `agent_npc` 的真实缺口。它不是实现方案本身；后续实现方案见 `docs/design/autonomous_tick_next_slice_plan.md`。

## Scope

当前 `agent_npc` 已具备 `NPCMind`、`NarrativeEnvironment`、`NPCAction`、`ActionValidator`、`ActionResult`、`Reflection` 和 LLM-required 主玩家回合。因此本轮学习不再重复建议“新增 mind/environment 基础层”，而是聚焦以下问题：

- NPC 如何从世界事件中被动接收和主动响应；
- action/tool/function 如何被注册、过滤、暴露给 agent；
- tick、event queue、notify、inbox 如何驱动非玩家输入的 agent 回合；
- NPC 可见性、见证者、位置和私有事件如何进入 observation；
- plan state、event history、trace/eval 如何让主动行为可调试。

## Repo Snapshot

| 优先级 | 仓库 | 主要语言 | 许可证观察 | 本轮关注点 |
| --- | --- | --- | --- | --- |
| P0 | `Goodbird-git/Player2NPC` | Java | GitHub API 返回 `NOASSERTION` | Minecraft 内具身 NPC、生命周期、server tick、controller |
| P0 | `Goodbird-git/PlayerEngine` | Java | LGPL-3.0 | task catalog、task chain、conversation queue、距离可见性 |
| P0 | `datawhalechina/hello-agents` | Python | GitHub API 返回 `NOASSERTION` | Cyber Town 教程架构、memory、affection、日志展示 |
| P1 | `elefant-ai/player2-ai-npc-godot` | GDScript | GPL-3.0 | `chat`/`notify` 分离、tool scan、signals、conversation summary |
| P1 | `elefant-ai/unity-player2-sdk` | C# | MIT | serializable functions、NPC manager、per-NPC command surface |
| P1 | `VcGameDev/CobbleBrain` | Kotlin | GitHub API 返回 `NOASSERTION` | `WorldContext`、world event tick、state-driven proactive behavior |
| P1 | `elefant-ai/MindOfTheColony` | Java | GitHub API 返回 `NOASSERTION` | colony event evaluators、event history、bridge manager、NBT 持久化 |
| P2 | `horizonfps/project-lunar` | Python | GitHub API 返回 `NOASSERTION` | witnessed_by、scene presence、knowledge boundaries、memory tier |
| P2 | `PlayHyperia/hyperforge` | TypeScript | GitHub API 返回 `NOASSERTION` | manifest-driven content、validation/backups |
| P3 | `elefant-ai/player2-ai-npc-defold` | C++ | GPL-2.0 | 最小 NPC API surface |
| P3 | `elefant-ai/chatclef` | Java | AGPL-3.0 | command bridge、valid commands prompt、one-command-at-a-time |

许可证结论：GPL/AGPL/LGPL 仓库只能借鉴概念、接口边界和测试思路，不复制代码。MIT 仓库也只作为设计参考，避免把引擎 SDK 细节带入当前 Python 项目。

## Code-Level Notes

### Player2NPC

核心入口文件：

- `src/main/java/com/goodbird/player2npc/companion/AutomatoneEntity.java`
- `src/main/java/com/goodbird/player2npc/companion/CompanionManager.java`

Agent 机制：

- `AutomatoneEntity` 是一个真实 Minecraft entity，持有 inventory、interaction manager、hunger provider 和 `AltoClefController`。
- entity 的 `tick()` 调用 controller 的 server tick，使 NPC 行为进入游戏主循环，而不是只响应玩家文本。
- `CompanionManager` 维护玩家到 companion 的 map，负责 summon、teleport、dismiss、fetch characters 和 server tick 生命周期。

事件、任务、action、memory、trace 模式：

- 事件来源不是抽象文本，而是 entity 状态、玩家状态、世界 tick 和交互。
- action 执行依赖具身控制器和游戏 interaction manager。
- trace 重点在运行时控制和生命周期，缺少适合 Web/文本项目的结构化 trace UI。

可借鉴点：

- 当前 `agent_npc` 的下一步应补一个与主玩家回合并行的 `autonomous_tick` 入口。
- NPC lifecycle 和 tick 管理应集中在 workflow/API 层，避免散落在 response 或 memory 写入处。
- “NPC 是世界对象”这一点可转译为 `npc_id + location_id + event inbox + available_actions`。

不适合迁移点：

- Minecraft entity、pathfinding、inventory、server tick 不能直接迁移。
- 当前项目不应引入具身行动层的大型抽象，只需要轻量 action executor 边界。

### PlayerEngine

核心入口文件：

- `TaskCatalogue.java`
- `UserTaskChain.java`
- `ConversationManager.java`

Agent 机制：

- `TaskCatalogue` 把命令名、资源名、物品名映射到 task factory，形成可查询的 task registry。
- `UserTaskChain` 管理 active task、idle task、task finish callback 和 stop 行为。
- `ConversationManager` 对 player chat、AI character message 和 priority message 做队列处理，并使用最大距离限制消息传播。

事件、任务、action、memory、trace 模式：

- task 是可执行单位，catalog 是 agent 可用动作的来源。
- conversation queue 不是直接写入对话响应，而是先排队、再由 process 消费。
- 可见性使用距离规则，这是当前 `visible_world_events` 全局读取的直接对照。

可借鉴点：

- 建立 `ActionCatalog` / `ActionSpec`，让 `NPCMind` 只能从 `available_actions` 中提出动作。
- action preconditions 应在 action catalog 与 `ActionValidator` 之间形成双层约束：catalog 负责“可选”，validator 负责“最后兜底”。
- world event 到 NPC 的传播不应直接查全局最近事件，应经过 location/visibility/inbox 过滤。

不适合迁移点：

- Minecraft 资源任务体系过重。
- 不需要把当前 narrative tools 全部改成 task class；第一版用 dataclass spec 和函数映射即可。

### hello-agents Cyber Town

核心入口文件：

- `docs/chapter15/Chapter15-Building-Cyber-Town.md`
- 文档中描述的 `create_npc_agent`、`MemoryManager`、`WorkingMemory`、`EpisodicMemory`、FastAPI backend 和 Godot scene 分层。

Agent 机制：

- 教程把系统拆成 agent 创建、记忆管理、情感/好感度、前端场景和后端 API。
- 它更像教学型 vertical slice，而不是低层 runtime framework。

事件、任务、action、memory、trace 模式：

- memory 分层清晰，working memory 与 episodic memory 分开。
- affection 和日志展示使 agent 状态可演示。
- trace/debug 方向偏产品展示，适合当前项目的课程报告和 demo。

可借鉴点：

- 当前项目已经有 memory、mind 和 trace，应在自主 tick 中补“可解释展示”：trigger、visible events、available actions、proposed/validated action、reflection。
- demo 文档可以把主动 NPC 回合做成一条可重复脚本，而不是依赖自由聊天。

不适合迁移点：

- 不应重做教学项目的 agent factory 或 memory manager。
- 不应为了展示而弱化当前 LLM-required 和 action validation 约束。

### Godot Player2 SDK

核心入口文件：

- `addons/player2/nodes/Player2AINPC.gd`
- `ToolCallFunctionDefinition.gd`

Agent 机制：

- `Player2AINPC.gd` 暴露 `chat` 和 `notify` 两类入口：chat 是玩家对话，notify 是系统/世界消息。
- node 保存/加载 conversation history，并有 summary trimming。
- signals 包括 thinking、tool_called、chat_received 等运行态信号。
- `ToolCallFunctionDefinition.gd` 用导出字段定义 function 名称、启用状态和描述。

事件、任务、action、memory、trace 模式：

- `notify` 是非常接近当前缺口的入口：世界变化可以通知 NPC，而不必伪装成玩家说话。
- tool scan 让可用 function 由场景节点声明，等价于当前项目可做的 action catalog。
- signals 可对应 trace/debug hook。

可借鉴点：

- 在 API 层区分 `POST /api/world/events` 与玩家 chat。
- `autonomous_tick` 使用 event inbox 作为 trigger，而不是把事件内容塞进 `player_input`。
- action spec 应有 `enabled` 或 precondition 状态，便于 trace 展示为什么某动作不可用。

不适合迁移点：

- Godot node 和 signal 机制不迁移。
- GPL-3.0 风险下不能复制实现。

### Unity Player2 SDK

核心入口文件：

- `NpcManager.cs`
- `Player2Npc.cs`

Agent 机制：

- `NpcManager` 管理 NPC 注册、response listener、function handler 和 serializable functions。
- `Function` / `FunctionArgument` 把可调用函数序列化后发送给 NPC runtime。
- `Player2Npc` spawn request 包含 character description、commands 和 keep game state。

事件、任务、action、memory、trace 模式：

- 每个 NPC 的可调用 function surface 在注册/生成时确定。
- function handler 是 action 执行边界。
- command schema 是 LLM 决策可见的动作空间。

可借鉴点：

- `ActionSpec(action_type, description, args_schema, allowed_npcs, preconditions, effects, forbidden_effects)` 与 Unity SDK 的 serializable function 概念相近。
- 当前 `NPCAction` 不需要消失；它应成为 `ActionSpec` 约束下的 proposed action。

不适合迁移点：

- Unity spawn、listener、MonoBehaviour 生命周期不迁移。
- 第一版不需要复杂 function argument schema 解析器；可先用 Python dict schema 和 deterministic precondition。

### CobbleBrain

核心入口文件：

- `WorldContext.kt`
- `WorldEventsSystem.kt`

Agent 机制：

- `WorldContext` 收集 biome、time、weather、nearby entities/items、health 等局部上下文。
- `MemoryStore` 拆分 short_term 与 long_term。
- `WorldEventsSystem` 在 server tick 中按间隔检查条件，维护 pending/active event，并根据 karma/state 触发后续行为。

事件、任务、action、memory、trace 模式：

- world event 不是被动日志，而是状态机：pending、active、cooldown、resolved。
- event 评估使用 deterministic trigger，LLM 不参与底层世界规则。
- context 明确包含环境快照，避免 NPC 对全局世界全知。

可借鉴点：

- 当前 `Observation` 应逐步增加 location/weather/nearby/visible event 等局部 context，而不是只读最近全局事件。
- 第一版 `autonomous_tick` 应优先 deterministic trigger/action，LLM 作为可选增强。
- trigger 需要 cooldown 或 seen 标记，避免同一事件被 NPC 反复主动响应。

不适合迁移点：

- 大规模世界事件系统和战斗/raid 模型过重。
- 当前 narrative 项目只需要事件可见性、inbox 和少量主动推进规则。

### MindOfTheColony

核心入口文件：

- `CitizenNpcManager.java`
- `ColonyEventManager.java`
- `EventContext.java`

Agent 机制：

- `CitizenNpcManager` 映射 colony citizen、NPC bridge 和 active conversation，并在 server tick 中驱动 bridge/event/conversation manager。
- `ColonyEventManager` 维护 event history、evaluators、`onTick`、`evaluateEvents`、recent events 和持久化。
- `EventContext` 把 colony、weather、citizens、tick、random 作为 evaluator 输入。

事件、任务、action、memory、trace 模式：

- event evaluator 是独立模块，输入是显式 context，输出进入 bounded history。
- recent events 可被格式化为 agent context。
- event history 可持久化，避免 tick 重启后丢失状态。

可借鉴点：

- 当前 `world_events` 表应升级为结构化事件，并保留兼容字段。
- event visibility/inbox 可以先由 lightweight evaluator 填充，而不是让每个 tick 查询所有事件。
- `AutonomousTickResult` 应记录 trigger event、observation、goal、plan step、action、validation、result 和 trace id。

不适合迁移点：

- colony bridge、Minecraft citizen 和 NBT 持久化不迁移。
- 不应把事件系统做成大规模 evaluator framework；先保持小而明确。

### project-lunar

核心入口文件：

- `npc_mind_engine.py`
- `memory_engine.py`
- `world_reactor.py`
- `test_npc_mind_engine.py`

Agent 机制：

- mind state 区分 transient feeling 与持久 goal/opinion/secret_plan。
- 场景 presence、`npcs_present` 和 `npc_knowledge` 限制 NPC 能知道什么。
- memory event 带 `witnessed_by`，有 SHORT/MEDIUM/LONG/MEMORY tier 和 auto crystallization。
- world reactor 使用 tick type 分类处理世界变化。

事件、任务、action、memory、trace 模式：

- `witnessed_by` 是当前 visibility 缺口的直接参考。
- 测试显式覆盖 knowledge boundary、scene presence、persistent goals 和 decay。

可借鉴点：

- `WorldEvent` 应支持 `visibility`、`location_id`、`payload` 和可选 witness/inbox 派生。
- 测试应覆盖 private event 不被无关 NPC 看到，而不是只测响应文本。
- plan state 可以先独立于长期 memory 记录 active goal / plan step，后续再沉淀为 memory facets。

不适合迁移点：

- memory tier/crystallization 可以作为后续演进，不应进入第一版自主 tick。
- 不能把当前已经完成的 `NPCMind` 替换成另一个 mind engine。

### hyperforge

核心入口文件：

- `packages/asset-forge/server/services/ManifestService.ts`

Agent 机制：

- manifest service 管理 NPC、world areas、quests 等内容类型。
- 读写包含 validation、backup 和 manifest definitions。

事件、任务、action、memory、trace 模式：

- 重点是内容资产管理，不是 agent runtime。
- schema-driven 内容定义可降低场景配置分散度。

可借鉴点：

- 当 action catalog 和 world areas 增多后，可以把 action/world/npc 配置迁到 manifest。
- 当前阶段可以先保持 Python dataclass 和 SQLite，避免引入内容资产平台。

不适合迁移点：

- 对当前最小垂直切片过度工程。

### Defold Player2 Plugin

核心入口文件：

- README 中的 `ainpc.npc_spawn`、`ainpc.npc_chat`、`ainpc.npc_kill`、`ainpc.npc_responses`、`chat_completion` API。

Agent 机制：

- API surface 极小，偏 SDK 集成。

可借鉴点：

- 当前新增 API 也应少而清楚：`POST /api/world/events` 和 `POST /api/npcs/{npc_id}/tick` 足够启动第一版。

不适合迁移点：

- Defold/C++ runtime 不迁移。
- GPL-2.0 风险下不能复制实现。

### ChatClef

核心入口文件：

- `Command.java`
- `AICommandBridge.java`

Agent 机制：

- command 有 name、description、args parser 和 `run`/`call` 边界。
- AI command bridge 把 valid commands、world/player status 和队列写进 prompt，且一次只允许一个 command。

事件、任务、action、memory、trace 模式：

- LLM 只看到 valid commands，不是看到所有潜在工具。
- command 执行有明确参数解析和运行边界。

可借鉴点：

- `available_actions` 应进入 decision prompt/trace，让 LLM 或 deterministic proposer 在有限动作空间内行动。
- `ActionValidator` 保持最后防线，防止 Sable 等角色越权。

不适合迁移点：

- AGPL-3.0 风险下不能复制实现。
- Minecraft command prompt 结构不能直接用于当前 narrative tool schema。

## Six-Theme Mapping To Current Gaps

### 1. Embodied / Action Executor

当前已有能力：

- `NPCAction` 表达 NPC 想做什么。
- `NarrativeEnvironment.execute()` 统一执行 action 并产出 `ActionResult`。
- `ActionValidator` 能把非法 action 降级为安全 action。

当前缺口：

- 没有 NPC 自主回合入口。
- action 执行仍主要从玩家输入触发。
- observation 缺少清晰的 location/visible event 边界。

最小可迁移做法：

- 新增 `run_autonomous_tick(npc_id, trigger_event_id=None)`，复用现有 mind、validator、environment。
- 第一版不做物理 pathfinding，只把具身概念缩小为 location、event inbox、available action。

过度工程风险：

- 直接迁移 Minecraft/Unity/Godot entity 生命周期会把当前文本叙事项目变成引擎 SDK 项目。

### 2. Tool / Function / Action Registry

当前已有能力：

- `workflow.py` 能把 LLM decision 转成 `NPCAction`。
- validator 已经知道哪些 action 不应该被允许。

当前缺口：

- 没有 `ActionCatalog` / `available_actions`。
- preconditions 没有在 action 提议前显式过滤。
- trace 不能解释“某 action 为什么没出现在候选列表中”。

最小可迁移做法：

- 定义 `ActionSpec`，字段包括 `action_type`、`description`、`args_schema`、`allowed_npcs`、`preconditions`、`effects`、`forbidden_effects`。
- 在 observation 或 decision context 中注入 `available_actions`。
- validator 继续作为最终安全层。

过度工程风险：

- 不要把每个 action 都改成 class hierarchy；第一版 registry + pure precondition function 足够。

### 3. Event Queue / Notify / Tick

当前已有能力：

- 数据库已有 world events，但字段偏简单。
- trace 已经能记录环境执行路径。

当前缺口：

- `world_events` 只有 `content/created_at` 级别。
- `Observation.visible_world_events` 直接读最近全局事件。
- 没有 `npc_event_inbox`、seen 标记、relevance/cooldown。
- 没有 API 级 `notify` 或 `autonomous_tick`。

最小可迁移做法：

- 新增结构化 `WorldEvent(event_type, source_type, source_id, location_id, visibility, payload)`。
- 写入 event 后派生 NPC inbox item。
- `POST /api/world/events` 只负责注入世界事件；`POST /api/npcs/{npc_id}/tick` 负责消费 inbox 并运行 NPC 主动回合。

过度工程风险：

- 不要一开始就做全局 scheduler、复杂 event evaluator 或实时后台 worker；先用手动 tick/API tick 验证闭环。

### 4. State-Driven Proactive Behavior

当前已有能力：

- `NPCMind` 已能维护 belief、emotion、goal、plan、social strategy 和 reflection。
- procedural memory facets 可部分延续 plan。

当前缺口：

- plan state 没有专用持久化或 tick 消费模型。
- 主动行为没有 deterministic trigger/action 测试。

最小可迁移做法：

- 第一版选择少量显式 trigger：
  - Lina 看到 `player_asked_ruins_too_early` 后进入 trust-test。
  - Ron 只在 badge evidence 满足后推进。
  - Sable 可误导但不能 unlock/complete/改写他人 trust。
- LLM 只作为 response 或 action proposal 增强；核心规则用 deterministic preconditions 锁住。

过度工程风险：

- 不要引入通用 GOAP/behavior tree。
- 不要让 LLM 直接决定世界事实或任务权限。

### 5. Knowledge Visibility / Witness Filtering

当前已有能力：

- 多 NPC 与任务隔离已有测试。
- Sable 越权行为已有防线。

当前缺口：

- 世界事件没有结构化可见性。
- observation 没有按 location、visibility、witness、inbox 过滤。

最小可迁移做法：

- `visibility` 先支持 `public`、`location`、`private`、`npc_only`。
- inbox 写入时记录 `reason`，例如 same_location、explicit_target、public、witnessed_by。
- 测试 private event 不被无关 NPC 看到。

过度工程风险：

- 不要过早实现完整权限语言或 spatial simulation。

### 6. Trace / Eval / Debug Presentation

当前已有能力：

- 现有 `/api/trace` 和测试覆盖 mind/environment trace。
- 课程 demo 文档已有。

当前缺口：

- trace 还没有 autonomous trigger、visible_events、available_actions、validated_action 和 proactive message 的完整链路。
- 缺少针对主动 NPC 回合的 eval scenario。

最小可迁移做法：

- `AutonomousTickResult` 作为 trace 基础对象。
- 扩展 trace 展示字段：trigger、visible_events、available_actions、proposed_action、validated_action、action_result、reflection。

过度工程风险：

- 不要先做复杂 UI；先让 API trace 和测试 fixture 稳定。

## Current Project Mapping

不应重复建设的部分：

- `src/agent/npc_mind.py` 已有 mind state 与 reflection。
- `src/agent/environment.py` 已有 observation/action/result/environment。
- `src/agent/action_validator.py` 已有 action 安全降级。
- `src/agent/workflow.py` 已有玩家主回合完整链路。

应优先补齐的部分：

- 结构化 `world_events`。
- 基于 location/visibility/inbox 的 `visible_world_events`。
- `npc_event_inbox` 与 seen/relevance/reason。
- `ActionCatalog`、`ActionSpec`、`available_actions` 和 preconditions。
- `run_autonomous_tick` 或等价 API 入口。
- `AutonomousTickResult` 和 autonomous trace。

## Recommendation

下一阶段应做一个最小垂直切片，而不是再扩展 mind layer：

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

第一版要保持 deterministic trigger/action 为主，LLM 仅作为可选增强。这样既能从外部仓库吸收“主动 agent”的关键机制，又不会破坏当前已经稳定的玩家输入主回合。
