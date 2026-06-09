# 01_cover

大家好，我是薛良玺。这次课程汇报的主题是“记忆驱动的可验证 LLM 角色 Agent 系统”。项目关注的不是做一个普通聊天界面，而是把 LLM 角色对话放入状态、记忆、校验和 trace 组成的运行链路中。接下来我会先说明普通角色聊天为什么不足，再展示项目如何从单 NPC 对话逐步演进到 Traveler living-world runtime。

---

# 02_problem

项目的起点是一个很具体的问题：角色说了什么，并不等于世界里真的发生了什么。普通 LLM 对话可能生成“入口已经解锁”这样的文本，但数据库、任务状态和物品并没有对应变化；如果只保存最终回复，也很难回头解释一次行为为什么发生。这里列出的三个风险分别是语言幻觉、上下文断裂和不可复盘。我的设计目标，就是把角色语言能力保留下来，同时把世界事实交给可验证的程序流程。

---

# 03_goal

基于这个问题，项目目标可以概括为四个支柱：状态、记忆、校验和 trace。状态层用 SQLite 保存任务、地点、物品和关系；记忆层把近期上下文、长期记忆和 lore 带入角色决策；校验层阻止 LLM 直接越权改写世界事实；trace 则记录每一步中间过程。这样，一个 NPC 不只是会回复一句话，而是能在受控流程里读取状态、形成计划、提出行动，并留下证据。

---

# 04_git_evolution

这页讲的是项目能力的演进历史，而不是版本号清单。第一阶段先做单 NPC 记忆对话原型，验证能否读取状态、调用 LLM、回复玩家并留下 trace。第二阶段发现角色只看当前输入不稳定，所以加入分层上下文、lore 检索、长期记忆和玩家端界面。第三阶段把 NPCMind、NarrativeEnvironment 和 ActionValidator 拆出来，解决 LLM 语言意图和世界事实执行权混在一起的问题。最后加入 autonomous runtime、Traveler profile 和 timeline export，让项目变成可以自动探索、多 NPC 互动、并能在课堂上复盘展示的 living world。

---

# 05_architecture

总体架构的关键，是把 LLM 放在“提出意图”的位置，而不是让它直接拥有执行权。玩家或 Traveler 的输入先变成 observation，再经过记忆与 lore 检索，进入 NPCMind 形成 belief、goal 和 plan；LLM 基于这些上下文输出结构化 decision。这个 decision 必须经过 ActionValidator 和 NarrativeEnvironment，才能写入 SQLite 世界状态。最后，系统会把过程导出为 trace 和 timeline，这也是后面报告和演示的主要证据来源。

---

# 06_module_boundary

这页进一步拆开模块职责。NarrativeEnvironment 负责组织 observation 和执行 action，Memory 系统负责补充上下文，NPCMind 负责形成角色内部判断，LLM Decision 负责提出结构化意图。真正守住事实边界的是 ActionValidator 和 SQLite World State，前者决定行动是否允许，后者保存任务、地点、物品和关系的真实变化。这样的分工让项目更容易解释，也让后续测试和定位问题更清楚。

---

# 07_memory_retrieval

角色要表现得稳定，不能只看当前一句输入。项目把近期上下文、稳定 lore、长期记忆和任务状态作为不同来源，再通过检索合成当前 Agent 的上下文。这样，NPC 在回复前能知道当前地点、之前互动、自己应该知道或不知道的设定，以及当前任务条件。后台 memory jobs 的作用，是把运行过程中产生的交互和反思整理成后续可检索内容，避免所有历史都挤在单轮 prompt 里。

---

# 08_mind_validator

NPCMind 和 ActionValidator 是项目里最重要的一组边界。NPCMind 让角色在回复前先形成 belief、emotion、goal、plan 和 social strategy，所以角色不是只在模板里说话，而是有可记录的主观状态。ActionValidator 则从相反方向工作：它检查 LLM 提出的 action 是否符合当前世界状态，如果越界就阻止或修复。这样既保留了角色语言的灵活性，又避免一句自然语言直接改变数据库事实。

---

# 09_autonomous_runtime

在 autonomous NPC runtime 中，NPC 可以响应世界事件，而不是永远等待玩家输入。流程从 world event 开始，事件进入 NPC inbox，系统根据 NPC 状态和 ActionCatalog 构造可行动作集合，然后让 LLM 在这个集合内做 constrained decision。即使是自主 tick，结果仍然必须经过 Validator，最后写入 mailbox、runtime state 和 trace。这个设计的重点不是让 NPC 随机行动，而是让世界事件以可约束、可复盘的方式影响角色。

---

# 10_traveler_runtime

Traveler runtime 是项目后期最适合课堂展示的部分。Traveler 不是手工输入的玩家，而是由 YAML profile 配置的角色 Agent，它有公开身份、私人目标、隐藏信息、行动边界和探索风格。每一轮它会观察世界、检索线索、决定移动或询问，再执行行动并反思。timeline 导出会记录行动理由、Traveler 发言、NPC 回复、状态变化、timing breakdown 和 arc evidence，因此不同 profile 的路线差异也可以被实际复盘。

---

# 11_real_evidence

为了避免汇报停留在架构图上，这页放的是当前仓库里的真实界面和 trace 证据。左侧是 React/Vite 玩家端界面截图，右侧列出 timeline 中用于复盘的关键字段，包括 Traveler 发言、NPC 回复、关系变化、探索线索、arc evidence、最终 outcome 和 timing。项目还保留了课堂展示 trace 和 Sable 路线 trace，所以报告中的结果不是虚构描述，而是从当前项目运行输出中整理出来的。

---

# 12_sable_case

Sable 路线可以很好地说明语言层和状态层的分离。这个真实 trace 中，Traveler 选择和 Sable 对话，理由是希望通过非正式信息渠道建立信任并获取遗迹传闻；Sable 的决策意图是转移遗迹询问，关系值也确实发生了变化。但是 trace 同时明确记录了 response constraints：不能声称遗迹入口已经解锁，也不能声称玩家获得了物品奖励。所以这里允许的是角色关系和对话策略推进，不是绕过规则完成任务。

---

# 13_evaluation_limits

当前评估主要依赖 demo trace、JSON 和 Markdown timeline，以及人工复盘。它已经能说明一些关键问题，例如角色知识边界能不能复盘，状态变化是否经过 Validator，Traveler profile 是否会影响路线，以及 timing breakdown 能不能帮助定位开销。局限也很明确：目前还不是大规模自动统计，文本 timeline 阅读成本也偏高。后续更合理的方向，是在已有 trace 基础上构建自动分析脚本和图形化回放界面。

---

# 14_closing

总结来说，这个项目的关键设计是把 LLM 放入受规则约束的运行链路中，而不是让它自由决定世界事实。角色先读取状态、检索记忆、形成心智，再由 LLM 提出意图，最后经过校验、执行和 timeline 导出。这样既保留了 LLM 在交互叙事中的表达优势，也降低了幻觉和越权行动对系统状态的破坏。后续如果继续发展，我会重点加强多 Agent 调度、长期记忆质量、自动评估和 timeline 可视化。
