# Living World Runtime — 方案 C 设计文档

> 状态: 草案 | 日期: 2026-06-03 | 作者: 架构设计阶段

---

## 1. 当前架构理解

### 1.1 整体概览

当前项目是一个以文字冒险 NPC 交互为验证场景的**记忆驱动角色 Agent 系统**。核心闭环为：

```
Player Input → Context Retrieval → NPCMind(belief/emotion/goal/plan) → LLM Decision
→ Action Validation → Environment Execution → Reflection → Response → Trace
```

系统已具备四个 NPC（Lina、Ron、Mira、Sable），SQLite 持久化所有状态，支持多前端（Streamlit 调试台、React 玩家端、FastAPI API）。

### 1.2 关键模块职责

| 模块 | 职责 | 本次升级影响 |
|------|------|-------------|
| `workflow.py` | 同步 turn 编排、trace 记录 | 保持不变，继续服务于玩家交互路径 |
| `autonomous_tick.py` | NPC 自主行为 tick（事件驱动） | 将被 NpcActorAdapter 包装 |
| `environment.py` | Observation 构建、NPCAction 转换、校验、执行 | 核心执行层，将扩展为统一的 Actor 执行沙箱 |
| `action_catalog.py` | 可用动作定义、前置条件、禁止效果 | 将扩展 Traveler 动作目录 |
| `npc_mind.py` | Belief/Emotion/Goal/Plan/Reflection | 保持不变，NPC 继续使用现有心智模型 |
| `world_arc.py` + `arc_director.py` | Arc 状态追踪、outcome 判定 | 将被 ArcDirectorActor 包装 |
| `player_actions.py` | 玩家发起的场景动作 | 保持不变，继续服务于玩家交互路径 |
| `event_visibility.py` | 世界事件分发到 NPC inbox | 将扩展为以 Actor 为粒度的可见性模型 |
| `decision.py` | 结构化决策、任务状态机 | 保持不变 |
| `schema.sql` | 数据库 schema | 将新增 traveler 相关表 |

### 1.3 当前数据流（玩家交互路径）

```
Player Input
  → NarrativeEnvironment.observe()
    → build_context_inputs()  // lore + memory + state
    → get_visible_world_events()
  → NPCMind.evaluate()
    → BeliefUpdater / EmotionEngine / GoalManager / Planner / SocialStrategySelector
  → decide_next_action()  // LLM structured decision
  → environment.propose_action_from_decision()  // → NPCAction
  → environment.validate()  // ActionValidator
  → environment.execute()   // tool execution + state change collection
  → ReflectionEngine.reflect()
  → generate_npc_response()
  → enqueue_memory_job()
  → log_interaction()
```

### 1.4 当前数据流（Autonomous Tick 路径）

```
NPC Inbox Event (trigger)
  → NarrativeEnvironment.observe()
  → memory search (hybrid)
  → get_available_actions() + get_unavailable_actions_with_reasons()
  → call_autonomous_llm() (or deterministic fallback)
  → validate_selected_action()
  → execute_selected_action()
  → upsert_npc_plan()
  → create_tick_message()
  → run_arc_director()
  → log_autonomous_tick()
  → mark_npc_event_seen()
```

### 1.5 当前世界模型局限性

- **没有空间模型**：NPC 有 location，但没有 distance、visibility、movement
- **NPC 被动响应**：autonomous tick 由 inbox event 触发，NPC 不会主动探索
- **没有 Traveler Agent**：玩家是唯一的外部行动者
- **Arc 判定简单**：仅基于 arc_signal 计数，缺少 phase 门控和 evidence 累积
- **没有多轮 simulation**：living world demo 仅执行一轮 player actions + 一轮 NPC ticks
- **没有对比实验能力**：无法比较不同玩家策略对世界演化的影响

---

## 2. 方案 C 目标

将现有的 **Player → NPC** 交互模型升级为 **Traveler + NPC + ArcDirector 三类型 Actor 协同演化的 Living World Runtime**。

### 2.1 核心原则

1. **统一 Actor 抽象**：Traveler、NPC、ArcDirector 都是 ActorAgent，共享 observe→retrieve→decide→validate→act→reflect→trace 闭环。
2. **NPC 自主性是一等公民**：NPC 不只是 Traveler 的被动反应者。每轮 NPC routines 独立产生 ambient 世界事件；NPC 通过 inbox 事件驱动 autonomous tick，无论事件来源是 Traveler、其他 NPC 还是环境。NPC 拥有自己的 plan、goal、routine 和 proactive message，不依赖 Traveler 触发。
3. **LLM 参与决策，不拥有事实**：LLM 可以选 action、解释动机、生成叙事，但不能直接改数据库。
4. **程序拥有 canonical state**：所有状态变更经过程序校验和工具执行。
5. **渐进式适配**：不重写现有 NPC 代码，用 Adapter 模式包装。
6. **可对比、可复现**：不同 Traveler profile 产生可比较的演化轨迹。
7. **现有测试保持通过**：新模块独立于旧路径，不影响 74 个现有测试。

### 2.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Actor 接口 | Python Protocol (structural subtyping) | 不强制继承，Adapter 灵活包装 |
| Traveler 实现 | 全新独立模块 | 避免耦合旧 workflow |
| NPC 适配 | Adapter 包装 autonomous_tick | 保留现有 NPCMind、action catalog、routine 和 inbox 驱动机制 |
| NPC 自主性 | 每轮独立执行 routine + inbox-driven tick | NPC 有自己的目标、计划、routine 和主动消息，不依赖 Traveler 触发 |
| 决策方式 | profile-biased LLM + deterministic fallback | 保持开放人格驱动，失败不崩溃 |
| 调度 | Round-based, single-threaded，四阶段 | Ambient → Traveler → NPCs → Resolution，详见 §7 |
| 配置 | YAML | 用户直接手写，可版本控制 |
| 数据库 | 新增 traveler 表，复用现有表 | 最小化 schema 变更 |
| 谎言处理 | dialogue/event metadata（不写 canonical fact） | 保护世界事实完整性 |

---

## 3. 新模块列表

```
src/agent/
├── living_world_runtime.py    # [NEW] ActorAgent Protocol + LivingWorldScheduler
├── traveler_profile.py        # [NEW] YAML profile loader + validation
├── traveler_state.py          # [NEW] Traveler state management (DB read/write)
├── traveler_actions.py        # [NEW] Traveler action catalog + available_actions builder
├── traveler_decision.py       # [NEW] Profile-biased LLM decision + fallback
├── traveler_tick.py           # [NEW] Traveler tick: observe→decide→act→reflect
├── major_events.py            # [NEW] Major event detection rules
├── timeline_export.py         # [NEW] JSON + Markdown timeline exporter
│
data/
├── travelers/                 # [NEW] Traveler YAML profiles
│   ├── truth_seeking_scholar.yaml
│   ├── suspicious_survivor.yaml
│   └── opportunistic_relic_hunter.yaml
├── traces/
│   └── traveler_runs/         # [NEW] Export directory
│
scripts/
├── run_traveler_world_demo.py           # [NEW] Single profile demo
└── run_traveler_profile_comparison.py   # [NEW] Multi-profile comparison
```

---

## 4. 数据模型

### 4.1 新增数据库表

```sql
-- Traveler 基础状态
CREATE TABLE IF NOT EXISTS traveler_state (
    traveler_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    current_location TEXT NOT NULL,
    inventory_json TEXT NOT NULL DEFAULT '[]',
    private_notes_json TEXT NOT NULL DEFAULT '[]',
    active_goal_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Traveler-NPC 关系状态（中等复杂度）
CREATE TABLE IF NOT EXISTS traveler_npc_relationship (
    traveler_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.0,        -- -1.0..1.0
    suspicion REAL NOT NULL DEFAULT 0.0,     -- 0.0..1.0
    affinity REAL NOT NULL DEFAULT 0.0,      -- -1.0..1.0
    leverage REAL NOT NULL DEFAULT 0.0,      -- 0.0..1.0 (traveler 对 NPC 的影响力)
    exposure REAL NOT NULL DEFAULT 0.0,      -- 0.0..1.0 (NPC 对 traveler 秘密的了解程度)
    debt REAL NOT NULL DEFAULT 0.0,          -- -1.0..1.0 (负=traveler 欠 NPC)
    last_tone TEXT NOT NULL DEFAULT 'neutral',
    known_secret_ids_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (traveler_id, npc_id),
    FOREIGN KEY (traveler_id) REFERENCES traveler_state(traveler_id),
    FOREIGN KEY (npc_id) REFERENCES npcs(npc_id)
);

-- Traveler 行动日志（每轮 per-tick 记录）
CREATE TABLE IF NOT EXISTS traveler_tick_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    traveler_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    trigger_event_id INTEGER,
    observation_json TEXT NOT NULL DEFAULT '{}',
    retrieved_memories_json TEXT NOT NULL DEFAULT '[]',
    available_actions_json TEXT NOT NULL DEFAULT '[]',
    action_biases_json TEXT NOT NULL DEFAULT '[]',
    llm_decision_json TEXT NOT NULL DEFAULT '{}',
    proposed_action_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    action_result_json TEXT NOT NULL DEFAULT '{}',
    state_changes_json TEXT NOT NULL DEFAULT '[]',
    relationship_changes_json TEXT NOT NULL DEFAULT '[]',
    created_events_json TEXT NOT NULL DEFAULT '[]',
    reflection_json TEXT NOT NULL DEFAULT '{}',
    deception_metadata_json TEXT NOT NULL DEFAULT '{}',   -- 谎言/隐瞒 record
    disclosure_metadata_json TEXT NOT NULL DEFAULT '{}',  -- 秘密披露 record
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (traveler_id) REFERENCES traveler_state(traveler_id),
    FOREIGN KEY (trigger_event_id) REFERENCES world_events(id)
);

-- 秘密跟踪（Traveler 的 secrets 和 NPC 的 hidden_alignment）
CREATE TABLE IF NOT EXISTS secret_tracking (
    secret_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,              -- traveler_id or npc_id
    owner_type TEXT NOT NULL,            -- 'traveler' | 'npc'
    label TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'medium',  -- low | medium | high | critical
    disclosed_to_json TEXT NOT NULL DEFAULT '[]', -- [{actor_id, actor_type, round, method}]
    exposure_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Simulation 运行记录
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
```

### 4.2 复用现有表

| 现有表 | 复用方式 |
|--------|---------|
| `npcs` | 保持不变，NPC 状态继续由此管理 |
| `world_events` | Traveler 行动产生的事件写入此表，`source_type='traveler'` |
| `npc_event_inbox` | Traveler 行动通过 `dispatch_world_event_to_inbox` 进入 NPC inbox |
| `world_arc_state` | ArcDirectorActor 继续更新此表 |
| `memories` | Traveler 记忆可写入此表（`scope='traveler'`），或新增 traveler 专用记忆表 |
| `scene_objects` | Traveler 可 `investigate` scene objects |
| `npc_locations` | Traveler 移动时参考 |
| `npc_runtime_state` | 保持不变 |
| `quests` | 保持不变 |

---

## 5. ActorAgent 接口

### 5.1 Protocol 定义

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ActorAgent(Protocol):
    """统一 Actor 接口 — structural subtyping，不强制继承。"""

    actor_id: str
    actor_type: str  # "traveler" | "npc" | "director"

    def observe(self, world_state: WorldState) -> Observation:
        """从世界状态中提取当前 Actor 可见的信息。"""
        ...

    def retrieve_memory(self, observation: Observation) -> list[MemoryItem]:
        """根据当前 observation 检索相关记忆。"""
        ...

    def build_action_surface(self, observation: Observation) -> ActionSurface:
        """生成 available_actions + unavailable_actions_with_reasons + soft_biases。"""
        ...

    def decide(self, observation: Observation, action_surface: ActionSurface) -> Decision:
        """选择行动（LLM 驱动或规则驱动）。"""
        ...

    def validate(self, decision: Decision, action_surface: ActionSurface) -> ValidationResult:
        """程序校验 decision 是否合法。"""
        ...

    def act(self, validated_decision: Decision) -> ActionResult:
        """执行行动，修改 canonical state。"""
        ...

    def reflect(self, action_result: ActionResult) -> Reflection:
        """事后反思，可能写入记忆。"""
        ...

    def emit_trace(self) -> TraceEntry:
        """输出本轮 trace。"""
        ...
```

### 5.2 关键数据类型

```python
@dataclass
class WorldState:
    """调度器在每个 round 开始时构建的全局状态快照。"""
    round_number: int
    traveler_state: dict
    npc_states: dict[str, dict]        # npc_id -> state
    scene_objects: list[dict]
    world_events_since_last_round: list[dict]
    arc_state: dict
    npc_relationships: dict[str, dict]  # npc_id -> relationship

@dataclass
class ActionSurface:
    available: list[ActionSpec]         # 可直接选择的行动
    unavailable: list[dict]             # 被前置条件阻止的行动 + 原因
    soft_biases: list[ActionBias]       # profile 驱动的倾向/阻碍

@dataclass
class ActionBias:
    action_type: str
    supporting_motivations: list[str]   # 哪些动机支持
    opposing_personality: list[str]     # 哪些人格阻碍
    risk_level: str                     # low | medium | high
    profile_alignment_score: float      # -1.0..1.0
```

---

## 6. Traveler Profile Schema

### 6.1 YAML 结构

```yaml
# data/travelers/truth_seeking_scholar.yaml
profile_id: truth_seeking_scholar
version: "1.0"

identity:
  public_name: "Arin the Cartographer"
  public_role: "独立学者，受雇于远方学院进行遗迹测绘"
  cover_story: "我在为学院编写第三版《边疆遗迹图志》"
  private_background: "曾在一处类似遗迹中失去同伴，发誓要查明这些遗迹的真相以防止更多悲剧"

motivations:
  curiosity: 0.95
  wealth: 0.15
  prestige: 0.30
  safety: 0.50
  loyalty: 0.40
  truth_seeking: 0.90
  power: 0.05

personality:
  cautious: 0.60        # 较高谨慎
  bold: 0.30
  empathetic: 0.70
  suspicious: 0.45
  patient: 0.75
  manipulative: 0.10

social_tendencies:
  default_honesty: 0.85
  trusts_authority: 0.25    # 不信任官方
  trusts_scholars: 0.85     # 高度信任学者
  trusts_merchants: 0.35    # 不太信任商人
  willing_to_lie: 0.15      # 几乎不愿撒谎
  willing_to_share_info: 0.70
  willing_to_deceive_for_goal: 0.10

exploration_style:
  primary_approach: "investigation_first"  # investigation_first | follow_rumors | revisit_clues | find_allies_first | avoid_attention
  secondary_approaches:
    - "follow_rumors"
  prefers_direct_questions: true
  revisits_locations: true
  avoids_public_attention: false

secrets:
  - secret_id: "scholar_tragic_past"
    label: "失去同伴的过往"
    content: "Arin 曾在类似遗迹中失去研究同伴，内心有 survivor's guilt"
    disclosure_policy: "只有在深度信任时才会提及"
    exposure_risk: "可能被 Mira 察觉学术动机不纯"
    risk_level: "medium"

private_goals:
  - goal_id: "understand_ruins_truth"
    description: "查明遗迹的真实性质和目的，防止他人重蹈同伴覆辙"
    priority: 0.95
    success_condition: "收集到足够证据理解遗迹性质"
  - goal_id: "protect_innocents"
    description: "确保遗迹相关信息不会导致无辜者受害"
    priority: 0.70

boundaries:
  hard:
    - "不会主动伤害任何 NPC 或破坏遗迹"
    - "不会伪造学术证据"
  soft:
    - "在安全时优先分享发现"
    - "宁愿与学者合作而非商人"

starting_location: "town_square"
starting_inventory: ["cartography_kit", "field_journal", "letter_of_introduction"]
private_notes:
  - "听说 Mira 是对遗迹最了解的学者，应该先找她"
  - "守卫 Ron 看起来很严格，直接问遗迹入口可能会引起怀疑"
  - "Sable 的传闻不可信，但她的信息网络可能有线索"
```

### 6.2 Profile 验证规则

- `profile_id` 必须唯一、仅含 `[a-z0-9_]`
- 所有 motivation/personality 值在 `[0.0, 1.0]` 范围内
- `hard_boundaries` 至少包含一条
- `private_goals` 至少包含一条，priority 在 `[0.0, 1.0]` 范围内
- `secrets` 每条必须有 `secret_id`、`label`、`content`、`disclosure_policy`、`risk_level`

---

## 7. 调度器流程

### 7.1 设计理念：NPC 自主性是一等公民

当前项目已具备三个 NPC 自主行为来源，都必须在新 Runtime 中得到保留和增强：

| 来源 | 当前实现 | Living World Runtime 中的角色 |
|------|---------|------------------------------|
| NPC Routines | `npc_routines` 表 + `run_wait_action` 中触发 | 每轮 Phase 1 自动触发，生成 ambient world events |
| NPC Inbox | `npc_event_inbox` 表 + `autonomous_tick` | 所有事件（ambient / traveler / other-npc）都进入 inbox，驱动 NPC tick |
| NPC Plans & Goals | `npc_plans` 表 + `NPCMind` | NPC tick 中持续推进，不受 Traveler 是否互动影响 |

**核心区别**：NPC 的 autonomous tick **不依赖 Traveler 是否与它互动**。只要 NPC inbox 中有 unseen 事件（无论来源），NPC 就可能 tick。一个 rumor 在酒馆传播后，Lina 可能主动去巡逻后巷，即使 Traveler 从未与 Lina 对话。

### 7.2 Simulation Round 定义

每个 simulation round 分为四个阶段（严格顺序）：

```
Round N:
  ═══════════ Phase A: AMBIENT — 世界自主演化 ═══════════
  1. [Scheduler]  Fire 所有 enabled NPC routines → 生成 ambient world_events
                  (Ron 巡逻、Mira 研究、Sable 交易、Lina 巡视)
  2. [Scheduler]  每个 ambient event 通过 dispatch_world_event_to_inbox 进入相关 NPC inbox
  3. [Scheduler]  构建 WorldState 快照（包含本轮的 ambient events + 历史状态）

  ═══════════ Phase B: TRAVELER — 旅行者行动 ═══════════
  4. [Traveler]   observe(WorldState) → retrieve_memory → build_action_surface
                  → decide(profile-biased LLM) → validate → act → reflect → emit_trace
  5. [Scheduler]  Traveler action 结果：
                  a. 生成 world_event(s)（source_type="traveler"）
                  b. 通过 dispatch_world_event_to_inbox 进入相关 NPC inbox
                  c. 更新 traveler_state、traveler_npc_relationship、secret_tracking

  ═══════════ Phase C: NPC — 自主响应 ═══════════
  6. [Scheduler]  收集所有有 unseen inbox items 的 NPC 列表
  7. [Scheduler]  按优先级排序 NPC tick 队列：
                  Priority 0: 被 Traveler 本轮直接影响的 NPC（talk_to, trade_with 的 target）
                  Priority 1: 被 ambient event 直接 targeting 的 NPC
                  Priority 2: 有 public rumor visible 的 NPC
                  Priority 3: 其他有 unseen items 的 NPC
  8. [NPC]        依次执行 NPC autonomous tick（最多 max_npc_ticks_per_round 个）：
                  select_trigger_item(inbox) → observe → retrieve_memory
                  → build_action_surface(available_actions) → decide(LLM) → validate
                  → act → reflect → plan_update → proactive_message → emit_trace
  9. [Scheduler]  每个 NPC tick 结果：
                  a. 可能生成新的 world_event（如 Lina 巡逻后巷、Ron 封锁路线）
                  b. 新事件再次 dispatch 到 inbox（可能触发下一轮的 chain reaction）
                  c. 更新 npc_plans、proactive_messages、npc_cooldowns

  ═══════════ Phase D: RESOLUTION — 结算与导出 ═══════════
  10. [Director]  ArcDirectorActor 观察本轮所有事件（ambient + traveler + npc）
                  → 更新 arc phase / tension / scores → 必要时推进 outcome
  11. [Detector]  MajorEventDetector 扫描本轮所有 tick 结果
                  → 标记 quest/relationship/secret/arc 重大变化
  12. [Exporter]  TimelineExporter 追加本轮结构化日志
```

### 7.3 调度配置

```yaml
# data/simulation_config.yaml
simulation:
  rounds: 12

  # Phase A: Ambient
  npc_routines_fire_every_round: true     # 每轮触发所有 enabled NPC routines
  ambient_event_visibility: "location"     # public | location | private

  # Phase C: NPC
  max_npc_ticks_per_round: 3              # 每轮最多触发几次 NPC tick
  npc_tick_priority: "affected_first"      # affected_first | inbox_order | random
  npc_cooldown_enabled: true               # 同一 NPC 连续 tick 有 cooldown

  # Phase D: Resolution
  arc_director_every_round: true
  memory_retrieval_mode: "hybrid"
  major_event_min_severity: "notable"

  export:
    format: ["json", "markdown"]
    output_dir: "data/traces/traveler_runs"
    include_full_trace: true
```

### 7.4 LivingWorldScheduler 伪代码

```python
class LivingWorldScheduler:
    def __init__(self, config: SimulationConfig, db_path: Path):
        self.config = config
        self.traveler: TravelerActor = ...
        self.npc_adapters: dict[str, NpcActorAdapter] = ...  # lina, ron, mira, sable
        self.arc_director: ArcDirectorActor = ...
        self.event_detector = MajorEventDetector()
        self.exporter = TimelineExporter()

    def run(self) -> SimulationResult:
        for round_num in range(1, self.config.rounds + 1):

            # ═══ Phase A: AMBIENT ═══
            ambient_events = []
            if self.config.npc_routines_fire_every_round:
                for routine in database.list_npc_routines(enabled_only=True):
                    event = database.create_world_event(
                        event_type=routine["event_type"],
                        content=routine["event_content"],
                        source_type="npc_routine",
                        source_id=routine["npc_id"],
                        location_id=routine["location_id"],
                        visibility=self.config.ambient_event_visibility,
                        payload={
                            "arc_id": "ruins_chapter_1",
                            "arc_signal": arc_signal_for_npc(routine["npc_id"]),
                            "routine_type": routine["routine_type"],
                            "round": round_num,
                        },
                    )
                    ambient_events.append(event)
                    dispatch_world_event_to_inbox(event)

            world_state = self.build_world_state(round_num, ambient_events)

            # ═══ Phase B: TRAVELER ═══
            traveler_tick = self.traveler.tick(world_state)
            traveler_events = self.process_actor_events(traveler_tick, source_type="traveler")

            # ═══ Phase C: NPC ═══
            all_npcs_with_inbox = self.collect_npcs_with_unseen_inbox()
            tick_queue = self.prioritize_npc_ticks(
                all_npcs_with_inbox,
                traveler_direct_targets=traveler_tick.get_direct_targets(),
                ambient_direct_targets=self.get_routine_targets(ambient_events),
            )

            npc_ticks = []
            ticked_npc_ids: set[str] = set()
            for npc_id in tick_queue:
                if len(npc_ticks) >= self.config.max_npc_ticks_per_round:
                    break
                if self.config.npc_cooldown_enabled and self.is_on_cooldown(npc_id):
                    continue
                tick_result = self.npc_adapters[npc_id].tick(world_state)
                npc_ticks.append(tick_result)
                ticked_npc_ids.add(npc_id)
                # NPC tick 可能产生新事件 → dispatch to inbox
                self.process_actor_events(tick_result, source_type="npc_autonomous")

            # ═══ Phase D: RESOLUTION ═══
            all_round_events = ambient_events + traveler_events + self.collect_npc_tick_events(npc_ticks)
            arc_update = self.arc_director.tick(world_state, all_round_events, npc_ticks)
            major_events = self.event_detector.scan(
                round_num, traveler_tick, npc_ticks, ambient_events, arc_update,
            )
            self.exporter.append_round(
                round_num, ambient_events, traveler_tick, npc_ticks, arc_update, major_events,
            )

        return self.finalize()

    def prioritize_npc_ticks(
        self,
        all_npcs_with_inbox: list[str],
        traveler_direct_targets: set[str],
        ambient_direct_targets: set[str],
    ) -> list[str]:
        """按优先级排序 NPC tick 队列。

        Priority 0: 被 Traveler 直接互动的 NPC
        Priority 1: 被 ambient routine 直接 targeting 的 NPC
        Priority 2: 有 public event 可见的 NPC
        Priority 3: 其他有 unseen items 的 NPC
        """
        priority_0 = [n for n in all_npcs_with_inbox if n in traveler_direct_targets]
        priority_1 = [n for n in all_npcs_with_inbox if n in ambient_direct_targets and n not in priority_0]
        priority_2 = [
            n for n in all_npcs_with_inbox
            if n not in priority_0 and n not in priority_1
            and self.has_public_unseen_events(n)
        ]
        priority_3 = [
            n for n in all_npcs_with_inbox
            if n not in priority_0 and n not in priority_1 and n not in priority_2
        ]
        return priority_0 + priority_1 + priority_2 + priority_3
```

### 7.5 一轮执行示例

假设 `truth_seeking_scholar` profile，第 3 轮：

```
Phase A: AMBIENT
  Ron routine fires: "Ron patrols town_gate → guard_post route" → ambient event
    → dispatch to inbox: Ron (own routine), Lina (same location: tavern)
  Mira routine fires: "Mira studies inscriptions in archive" → ambient event
    → dispatch to inbox: Mira (own routine)
  Sable routine fires: "Sable checks market rumors" → ambient event
    → dispatch to inbox: Sable (own routine)

Phase B: TRAVELER
  Traveler decision: talk_to("mira", topic="三角符号", honesty_level=0.9)
    → event: traveler_talked_to_npc → dispatch to Mira inbox
    → relationship: Mira trust +0.1, affinity +0.1

Phase C: NPC (max 3 ticks)
  Priority 0: Mira (被 Traveler 直接 talk_to)
    → Mira tick: 选择 request_field_notes → proactive_message 生成
  Priority 1: Lina (被 Ron 的 ambient routine 触发 — 同 location)
    → Lina tick: 选择 warn_quietly → proactive_message 生成
  Priority 2: (跳过 — 已达 max 3, 但 Priority 2 是 Sable with public rumor)
  备注: Ron 有 unseen item (own routine)，但 cooldown 中，跳过

Phase D: RESOLUTION
  ArcDirector: tension += 1 (evidence_gathering phase)
  MajorEventDetector: Mira trust increase → notable
  TimelineExporter: 追加 JSON + Markdown
```

关键观察：Ron 和 Sable 本轮没有被 Traveler 互动，但 Ron 的 routine 仍然产生了 ambient event，这个事件进入了 Lina 的 inbox，触发了 Lina 的自主 tick。Sable 的 routine 也产生了 ambient event，进入了她自己的 inbox。下一轮 Sable 可能因积累的 unseen event 而被调度 tick——这体现了 NPC 的自主性。Traveler 行动只是 NPC 获得 inbox 事件的**一个来源**，不是唯一来源。

---

## 8. Traveler 行动类型

### 8.1 行动目录

| 行动 | 描述 | 产生的事件类型 | 可能影响 |
|------|------|---------------|----------|
| `move_to(location_id)` | 移动到指定地点 | `traveler_moved` | 改变 traveler location，可能触发 location-based 事件 |
| `talk_to(npc_id, topic, tone, honesty_level, disclosure)` | 与 NPC 对话 | `traveler_talked_to_npc` | 影响 relationship，可能触发 NPC tick |
| `investigate(target_id, method)` | 调查场景物体 | `traveler_investigated` | 更新 scene object state，记录 evidence |
| `ask_for_help(npc_id, request, honesty_level)` | 向 NPC 求助 | `traveler_asked_help` | 影响 trust/affinity，可能触发 quest |
| `share_information(npc_id, claim, honesty_level)` | 向 NPC 分享信息 | `traveler_shared_info` | 可能影响多个 NPC，可能触发 rumor 传播 |
| `trade_with(npc_id, offered_item, requested_info)` | 与 NPC 交易 | `traveler_traded` | 影响 inventory，影响 debt/leverage |
| `challenge_claim(npc_id, evidence_id)` | 质疑 NPC 的说法 | `traveler_challenged` | 影响 trust/suspicion，可能揭露 deception |
| `follow_lead(lead_id)` | 追踪线索 | `traveler_followed_lead` | 改变 location/goal 状态 |
| `wait_and_observe()` | 等待观察（不行动） | `traveler_waited` | NPC routines 仍会触发，ambient 事件正常产生；可用于观察 NPC 自主行为模式 |
| `record_private_note(content)` | 记录私人笔记 | (无公开事件) | 仅更新 traveler private_notes |

### 8.2 行动前置条件（程序规则示例）

```python
TRAVELER_ACTION_PRECONDITIONS = {
    "talk_to": ["npc_exists", "same_location", "npc_not_hostile"],
    "investigate": ["object_exists", "same_location", "object_not_destroyed"],
    "trade_with": ["npc_exists", "same_location", "traveler_has_item or traveler_has_info"],
    "challenge_claim": ["evidence_exists", "claim_recorded_in_log"],
    "follow_lead": ["lead_exists", "lead_not_expired"],
}
```

---

## 9. Traveler 决策流程

### 9.1 Profile-Biased LLM Decision

```
1. 程序生成 available_actions (with preconditions checked)
2. 程序计算 soft_bias:
   for each available_action:
     - supporting_motivations: 哪些 profile.motivations 值 > 0.6 且与该 action 匹配
     - opposing_personality: 哪些 profile.personality 值 > 0.6 且与该 action 冲突
     - risk_level: 基于 preconditions 和历史 outcome 评估
     - profile_alignment_score: 综合匹配度
3. 构建 LLM prompt:
   - traveler profile (identity, motivations, personality, secrets, goals)
   - relationship states (trust/suspicion/affinity with each NPC)
   - world state (location, known events, arc phase)
   - retrieved memories
   - available_actions + soft_biases
   - unavailable_actions + reasons
4. LLM 返回:
   - selected_action + args
   - decision_reason
   - profile_alignment (哪些 profile 特征支持这个选择)
   - profile_tension (哪些 profile 特征与选择有张力)
   - deception_choice: {is_lie, is_omission, is_partial_disclosure, target_npc_id, what_was_deceived}
   - disclosure_choice: {secret_id, disclosure_level, target_npc_id, reason}
   - expected_consequence
5. 程序校验:
   - action_type 在 available_actions 中
   - args 符合 schema
   - 不违反 hard boundaries
   - deception 不在 canonical fact 中生效
6. 如果 LLM 失败: deterministic fallback
   - 选择 alignment_score 最高的 safe action
   - 或 wait_and_observe()
```

### 9.2 Deception/Disclosure 元数据

```python
@dataclass
class DeceptionMetadata:
    """旅行者撒谎/隐瞒的记录——只影响 dialogue/event，不写入 canonical fact。"""
    round_number: int
    traveler_id: str
    target_npc_id: str
    deception_type: str  # "lie" | "omission" | "partial_disclosure" | "misleading"
    claim_made: str      # 旅行者说了什么
    truth: str           # 事实是什么
    npc_believed: bool | None  # None = unknown
    detected: bool
    detected_by_npc_id: str | None
    evidence_against: list[str]

@dataclass
class DisclosureMetadata:
    """旅行者主动披露秘密的记录。"""
    round_number: int
    secret_id: str
    disclosed_to_actor_id: str
    disclosed_to_actor_type: str  # "npc" | "traveler" (future)
    disclosure_level: str  # "hinted" | "partial" | "full"
    reason: str
    npc_reacted: str | None
```

---

## 10. Major Event 检测规则

### 10.1 检测器设计

`MajorEventDetector` 是纯程序规则引擎，不依赖 LLM。每轮扫描以下信号：

| 规则 ID | 触发条件 | 严重级别 |
|---------|---------|---------|
| `quest_status_changed` | 任何 quest 状态变化 | `notable` |
| `relationship_shift` | trust/suspicion/affinity 变化 ≥ 0.3 | `notable` |
| `relationship_flip` | trust 或 affinity 从正变负或反之 | `major` |
| `secret_disclosed` | 任何 secret 被主动披露 | `major` |
| `deception_detected` | 任何 deception 被 NPC 识破 | `major` |
| `new_world_event_created` | 新 world_event 产生 | `notable` |
| `arc_phase_changed` | Arc phase 推进 | `major` |
| `arc_outcome_reached` | Arc 到达 resolved outcome | `critical` |
| `npc_lockdown` | Ron 执行 escalate_lockdown | `major` |
| `first_contact` | Traveler 首次与某 NPC 对话 | `notable` |
| `hostile_encounter` | NPC 拒绝对话或敌对响应 | `major` |
| `evidence_discovered` | Traveler 发现新 evidence | `notable` |
| `trade_completed` | 交易达成 | `notable` |
| `location_unlocked` | 新地点解锁 | `notable` |

### 10.2 事件严重级别

- **minor**: 仅记录，不突出显示
- **notable**: 在时间线中标记
- **major**: 时间线中突出显示，可能成为关键转折点
- **critical**: ARC final outcome 级别

---

## 11. 导出格式

### 11.1 JSON 结构

```json
{
  "run_id": "20260603T120000-truth_seeking_scholar",
  "profile_id": "truth_seeking_scholar",
  "simulation_config": { ... },
  "started_at": "2026-06-03T12:00:00Z",
  "completed_at": "2026-06-03T12:05:00Z",
  "final_arc_outcome": "research_advantage",
  "rounds": [
    {
      "round_number": 1,
      "traveler_tick": {
        "observation": { ... },
        "retrieved_memories": [ ... ],
        "available_actions": [ ... ],
        "action_biases": [ ... ],
        "llm_decision": {
          "selected_action": { "action_type": "talk_to", "args": { ... } },
          "decision_reason": "...",
          "profile_alignment": { ... },
          "profile_tension": { ... },
          "deception_choice": null,
          "disclosure_choice": null,
          "expected_consequence": "..."
        },
        "validation": { "status": "allowed", ... },
        "action_result": {
          "accepted": true,
          "state_changes": [ ... ],
          "created_events": [ ... ]
        },
        "reflection": { ... },
        "deception_metadata": null,
        "disclosure_metadata": null
      },
      "npc_ticks": [ ... ],
      "arc_state_after_round": { ... },
      "major_events": [ ... ]
    }
  ],
  "key_turning_points": [ ... ],
  "final_relationships": {
    "lina": { "trust": 0.1, "suspicion": 0.6, "affinity": -0.2, ... },
    "mira": { "trust": 0.8, "suspicion": 0.1, "affinity": 0.7, ... },
    ...
  },
  "disclosed_secrets": [ ... ],
  "detected_deceptions": [ ... ],
  "arc_outcome_evidence": { ... }
}
```

### 11.2 Markdown 结构

```markdown
# Living World Simulation Report

## Traveler Profile: truth_seeking_scholar (Arin the Cartographer)

[Profile 摘要: identity, key motivations, personality highlights, secrets]

---

## Timeline

### Round 1 — First Contact
- **Traveler**: move_to("archive") → 到达 Mira 的研究室
- **Traveler**: talk_to("mira", "遗迹铭文", tone="respectful", honesty_level=0.9)
  - Mira 积极响应，分享部分研究记录
- **Relationship**: Mira trust +0.2, affinity +0.3
- **Arc**: phase=rumor, tension=1

### Round 2 — Building Trust
...

---

## Major Events

| Round | Event | Severity | Details |
|-------|-------|----------|---------|
| 3 | Mira quest activated | major | Traveler 获得了 ancient_notes 任务 |
| 6 | Secret partially disclosed | major | Arin 向 Mira 暗示了自己的过往动机 |
| 9 | Arc phase → evidence_gathering | major | 证据积累触发阶段推进 |
| 12 | Arc resolved → research_advantage | critical | 研究线获胜 |

---

## Final Outcome: research_advantage

- **优势方**: Mira / 研究路线
- **证据**: Mira 获得完整田野笔记，遗迹研究推进
- **Arc tension**: 4/10

---

## Key Turning Points

1. Round 2: Traveler 选择先找 Mira 而非 Sable，奠定了研究路线
2. Round 6: 向 Mira 部分披露秘密加深了合作
3. Round 9: 提供了足够的符号观察证据

---

## Final Relationships

| NPC    | Trust | Suspicion | Affinity | Exposure | Last Tone |
|--------|-------|-----------|----------|----------|------------|
| Lina   | +0.10 | 0.60      | -0.20    | 0.15     | guarded    |
| Ron    | +0.05 | 0.55      | -0.10    | 0.05     | formal     |
| Mira   | +0.80 | 0.10      | +0.70    | 0.60     | warm       |
| Sable  | +0.20 | 0.40      | +0.15    | 0.30     | charming   |

---

## Disclosure & Deception Report

| Round | Type | Detail | Target | Detected |
|-------|------|--------|--------|----------|
| 6 | partial_disclosure | 暗示过去的研究经历 | Mira | N/A (genuine) |
| 8 | omission | 未告知 Lina 已与 Sable 交谈 | Lina | Yes (by Lina, Round 10) |

---

## Architecture Notes

- 这是一个多智能体系统（Multi-Agent System）
- Traveler、NPC、ArcDirector 都是统一 ActorAgent 的不同实现
- LLM 参与行动决策和叙事整理，但不拥有世界事实
- 所有状态变更有程序 trace/evidence
- 世界演化由工具调用、状态机、记忆系统和调度器共同形成
```

---

## 12. 分阶段实施计划

### Phase 0: 设计文档（当前阶段）✅

- 输出本文件: `docs/design/living_world_runtime.md`
- 评审并达成一致

### Phase 1: Traveler Profile Loader

**文件**:
- `data/travelers/*.yaml` (3 个内置 profile)
- `src/agent/traveler_profile.py`
- `tests/test_traveler_profile.py`

**内容**:
- YAML 加载、schema 校验、默认值填充
- `TravelerProfile` dataclass
- 验证: profile_id 唯一性、值域检查、必需字段检查

**依赖**: PyYAML (新增到 requirements.txt)

### Phase 2: Traveler State / Relationship / Memory

**文件**:
- `src/agent/traveler_state.py`
- `src/storage/schema.sql` (新增 traveler 表)
- `tests/test_traveler_state.py`

**内容**:
- 数据库 DDL 迁移
- `TravelerStateManager`: CRUD 操作
- `TravelerRelationshipManager`: 关系更新
- `SecretTracker`: 秘密跟踪
- 支持 traveler memory scope（可复用现有 `memories` 表或新建）

### Phase 3: Traveler Action Surface and Decision

**文件**:
- `src/agent/traveler_actions.py`
- `src/agent/traveler_decision.py`
- `tests/test_traveler_actions.py`

**内容**:
- `get_traveler_available_actions(traveler, world_state)` → `list[ActionSpec]`
- `compute_action_biases(actions, profile)` → `list[ActionBias]`
- `decide_traveler_action(profile, observation, action_surface)` → `Decision`
  - LLM 路径: profile-biased prompt
  - Fallback 路径: 选 alignment_score 最高的 safe action
- `build_traveler_decision_prompt(profile, observation, action_surface)` → user payload

### Phase 4: Traveler Tick

**文件**:
- `src/agent/traveler_tick.py`
- `tests/test_traveler_tick.py`

**内容**:
- `run_traveler_tick(traveler_id, world_state)` → `TravelerTickResult`
- 完整闭环: observe → retrieve → build_surface → decide → validate → act → reflect → trace
- 与 NPC 不同：traveler tick 不需要 inbox event 触发，是主动 tick
- 集成 `NarrativeEnvironment` 用于 action execution

### Phase 5: ActorAgent Adapters

**文件**:
- `src/agent/living_world_runtime.py`
- `tests/test_living_world_runtime.py`

**内容**:
- `ActorAgent` Protocol 定义
- `TravelerActor`: 包装 `traveler_tick.py`
- `NpcActorAdapter`: 包装 `autonomous_tick.py`（不重写 NPC 逻辑）
- `ArcDirectorActor`: 包装 `arc_director.py` + `world_arc.py`
- `WorldState` dataclass
- 各 Actor 的 `emit_trace()` 实现

### Phase 6: Scheduler

**文件**:
- `src/agent/living_world_runtime.py` (同一文件，追加 Scheduler)
- 配置: `data/simulation_config.yaml`

**内容**:
- `LivingWorldScheduler` 类
- Round-based 调度循环
- NPC 影响范围解析
- 集成所有三个 Actor 类型

### Phase 7: Major Event Detector and Timeline Export

**文件**:
- `src/agent/major_events.py`
- `src/agent/timeline_export.py`
- `tests/test_major_events.py`
- `tests/test_timeline_export.py`

**内容**:
- `MajorEventDetector.scan(round_num, traveler_tick, npc_ticks, arc_update)` → `list[MajorEvent]`
- `TimelineExporter.export_json(simulation_result, output_path)`
- `TimelineExporter.export_markdown(simulation_result, output_path)`
- Markdown 模板

### Phase 8: Demo Scripts

**文件**:
- `scripts/run_traveler_world_demo.py`
- `scripts/run_traveler_profile_comparison.py`

**功能**:
```bash
# 单 profile 运行
python scripts/run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 12 --mock

# 多 profile 对比
python scripts/run_traveler_profile_comparison.py --profiles truth_seeking_scholar,suspicious_survivor,opportunistic_relic_hunter --mock
```

对比脚本输出对比表：
| 指标 | truth_seeking_scholar | suspicious_survivor | opportunistic_relic_hunter |
|------|----------------------|---------------------|---------------------------|
| Final Arc Outcome | research_advantage | chaotic_lockdown | sable_advantage |
| Mira trust | +0.80 | +0.10 | -0.20 |
| Secrets disclosed | 1 | 0 | 2 (partial) |
| Deceptions | 1 (omission) | 0 | 4 (various) |
| Deceptions detected | 1 | 0 | 2 |
| Key ally | Mira | None | Sable |
| Arc tension | 4 | 8 | 6 |

### Phase 9: 测试

**新增测试文件**:
- `tests/test_traveler_profile.py` — YAML 加载、校验、默认值
- `tests/test_traveler_actions.py` — 行动前置条件、bias 计算
- `tests/test_traveler_tick.py` — tick 闭环、mock 决策
- `tests/test_living_world_runtime.py` — Actor 接口、WorldState 构建、调度器集成
- `tests/test_major_events.py` — 每条检测规则
- `tests/test_timeline_export.py` — JSON/MD 导出完整性

**测试策略**:
- 所有新测试使用 mock LLM（patch `call_openai_compatible_json`）
- 使用独立 `:memory:` 数据库
- 不依赖外部 API

---

## 13. 风险和降级策略

### 风险矩阵

| 风险 | 概率 | 影响 | 降级策略 |
|------|------|------|---------|
| LLM 决策质量不稳定 | 中 | 中 | Deterministic fallback 总是可用。在 mock 模式下，使用 profile-alignment 排序选最优 safe action |
| NPC Adapter 与旧 workflow 不兼容 | 低 | 高 | NpcActorAdapter 仅包装 autonomous_tick，不修改内部逻辑。如遇不兼容，跳过该 NPC 的 tick 并记录 |
| ArcDirector 与新事件类型不兼容 | 中 | 中 | ArcDirectorActor 在 Phase 5 仅做薄包装。Traveler 事件使用与 player event 相同的 event_type 约定 |
| 数据库迁移破坏现有数据 | 低 | 高 | 只新增表，不修改现有表结构。新表使用 `IF NOT EXISTS` |
| Scheduler 复杂度超出预期 | 中 | 中 | Phase 6 可先实现最简版本：仅 Traveler + affected NPC + Director，砍掉 visible NPC reaction |
| 测试数量膨胀导致维护困难 | 中 | 低 | 每个新模块独立测试，使用 mock，隔离数据库 |
| YAML profile 设计过度 | 低 | 低 | Phase 1 只实现必需字段，后续按需扩展 |
| 3 个 profile 无法产生差异化结果 | 中 | 中 | 在 Phase 8 先手动构造差异化输入验证，再依赖 LLM |

### 兼容性保障

- **现有 74 个测试必须保持通过**: 新模块不修改任何现有文件的核心逻辑
- **不影响 Streamlit / React / FastAPI**: 新模块是独立的 runtime 路径
- **旧 demo 脚本继续可用**: `scripts/run_living_world_demo.py` 保持不变
- **数据库向后兼容**: 只增加表，不修改列

### 降级运行模式

```
Level 1 (Full): LLM available → 完整 profile-biased decision + narrative
Level 2 (Mock): --mock flag → deterministic fallback decisions, 全离线可运行
Level 3 (Minimal): 无 LLM + 最小配置 → 仅规则驱动，用于 CI/测试
```

---

## 14. 未决问题（待讨论）

1. **Traveler memory 存储**: 复用现有 `memories` 表（加 `scope='traveler'`），还是新建 `traveler_memories` 表？建议先复用，后续按需拆分。
2. **NPC 主动与 Traveler 对话**: 当前 NPC 通过 `proactive_message` 向玩家发消息。在 Living World Runtime 中，NPC tick 产生的 proactive_message 如何处理？建议：proactive_message 进入一个消息队列，Traveler 在下一轮的 observation 中可以看到未读的 NPC 主动消息，并决定是否 respond。NPC routines 和 autonomous tick 都可以产生 proactive_message——这本身就是 NPC 自主性的体现。
3. **多 Traveler**: 当前设计假设单 Traveler。未来是否支持多个 Traveler 同时运行？接口层面已支持（`actor_id` 区分），但 Phase 6 先只实现单 Traveler。
4. **LLM 调用成本**: 每 round 至少 1 次 LLM 调用（Traveler decision）+ 可能的 NPC tick（当前 demo 用 mock）。12 round 单 profile 约 12-36 次调用。需在 demo 中说明。

---

## 15. 总结

本设计将项目从 **Player-NPC 交互 demo** 升级为 **可调度、可追踪、可复现的多智能体 Living World Runtime**，核心变化：

1. **统一 Actor 抽象**: Traveler / NPC / ArcDirector 共享 observe→decide→act→reflect 闭环
2. **开放人格驱动**: YAML profile 定义 Traveler 的动机、人格、社交倾向、秘密和探索风格
3. **程序守护**: LLM 仍只能选 action，不能改事实；Deception 记录但不污染 canonical state
4. **可对比实验**: 多个 profile 同场景运行，比较 world outcome
5. **渐进式落地**: 不推翻现有代码，用 Adapter + 新模块逐步扩展

预计新增代码约 2500-3500 行（含测试），新增 6 个测试文件，新增 3 个 YAML profile，新增 2 个 demo 脚本。
