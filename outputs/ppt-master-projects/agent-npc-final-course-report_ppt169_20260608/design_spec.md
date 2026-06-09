# agent-npc-final-course-report - Design Spec

> Human-readable design narrative — rationale, audience, style, color choices, content outline. Read once by downstream roles for context.
>
> Machine-readable execution contract: `spec_lock.md` (color / typography / icon / image short form). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep both in sync; on divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | agent-npc-final-course-report |
| **Canvas Format** | PPT 16:9 (1280x720) |
| **Page Count** | 14 |
| **Design Style** | General Consulting + 严肃课程项目汇报 / 工程报告风 |
| **Target Audience** | 课程老师优先，同学也能听懂 |
| **Use Case** | 8-10 分钟最终课程汇报 |
| **Created Date** | 2026-06-08 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280x720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | left/right 56px, top 44px, bottom 34px |
| **Content Area** | 1168x642 |

---

## III. Visual Theme

### Theme Style

- **Style**: 严肃课程汇报、工程报告、清晰架构图与证据页
- **Theme**: Light theme
- **Tone**: 克制、可信、项目完成度明确；避免赛博科技、霓虹、大面积 AI 背景、发布会感

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | PKU template white page background |
| **Section band** | `#F2F2F2` | Template-style neutral bands |
| **Primary** | `#A40012` | PKU red title accents and left blocks |
| **Dark text** | `#000000` / `#333333` | Main titles and body |
| **Muted text** | `#666666` | Captions, page numbers, source labels |
| **Border/divider** | `#D9D9D9` | Thin template dividers and panels |
| **Line** | `#BFBFBF` | Process connectors |
| **Warm accent** | `#E87522` / `#FFF1E5` | Cover rule and selected mechanism highlights |
| **Success** | `#15803D` | Allowed / verified |
| **Warning** | `#B91C1C` | Limits / blocked / risk |
| **Code bg** | `#F1F5F9` | Trace and code excerpts |

### Gradient Scheme

Use only subtle linear gradients for page bands or screenshot legibility. Avoid decorative orbs, bokeh blobs, neon glows, and large atmospheric backgrounds.

---

## IV. Typography System

### Font Plan

**Typography direction**: template-following PKU course-report typography using DengXian-style CJK sans.

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"DengXian", "Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Body** | `"DengXian", "Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Emphasis** | `"DengXian", "Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Code** | — | `Consolas` | `monospace` |

**Per-role font stacks**:

- Title: `"Microsoft YaHei", Arial, sans-serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `"Microsoft YaHei", Arial, sans-serif`
- Code: `Consolas`

### Font Size Hierarchy

**Baseline**: Body font size = 18px.

| Purpose | Ratio to body | Current Project | Weight |
| ------- | ------------- | --------------- | ------ |
| Cover title | 2.5-3.0x | 52px | Bold |
| Section / closing title | 2.2-2.5x | 44px | Bold |
| Page title | 1.8-2.0x | 34px | Bold |
| Hero number / key label | 2.0-2.3x | 40px | Bold |
| Subtitle | 1.3x | 24px | SemiBold |
| Body content | 1x | 18px | Regular |
| Code / trace | 0.78x | 14px | Regular |
| Annotation / caption | 0.78x | 14px | Regular |
| Page number / footnote | 0.67x | 12px | Regular |

Formula policy: `text-only`. Source material has no formula-heavy content.

---

## V. Layout Principles

### Page Structure

- **Header area**: 44-92px. Page number and short section label may sit in the upper right; title starts near x=56.
- **Content area**: 96-650px. Prefer process diagrams, matrices, timelines, screenshots, and trace excerpts over decorative visuals.
- **Footer area**: 650-700px. Source note and concise takeaway.

### Layout Pattern Library

Use the supplied PKU course-report template rhythm:

- Cover / closing: large white negative space, PKU logo, left red block, thin grey rule and warm accent rule.
- Body pages: top-left red block, bold black title, subtitle line, PKU logo at top right, bottom page number.
- Diagrams: thin grey outlines, black body text, PKU red emphasis, minimal icons.
- Evidence page: real screenshot framed by template-style thin border; no mobile screenshot.
- Architecture: left-to-right workflow and module maps.
- Evidence: screenshot and trace side-by-side, with source labels.
- Evaluation: compact evidence matrix and limits/future-work path.

### Spacing Specification

| Element | Current Project |
| ------- | --------------- |
| Safe margin from canvas edge | 56px |
| Content block gap | 24-32px |
| Icon-text gap | 10px |
| Card gap | 18-24px |
| Card padding | 18-24px |
| Card border radius | 8px |
| Line height | 1.35-1.5x body font size |

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `tabler-outline`
- **Stroke width**: 2
- **Usage method**: SVG placeholder `<use data-icon="tabler-outline/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Agent / mind | `tabler-outline/brain` | P01, P08 |
| World state | `tabler-outline/database` | P02, P05, P06 |
| Traveler route | `tabler-outline/route` | P10 |
| Validation boundary | `tabler-outline/shield-check` | P03, P08, P12 |
| Timeline / trace | `tabler-outline/timeline` | P05, P11, P13 |
| Git evidence | `tabler-outline/git-branch` | P04 |
| Report / evaluation | `tabler-outline/report-analytics` | P13 |
| Checklist / goal | `tabler-outline/checklist` | P03, P14 |
| Multiple NPCs | `tabler-outline/users` | P09, P11 |
| Runtime / backend | `tabler-outline/server-cog` | P09 |
| World map | `tabler-outline/map-route` | P10 |
| LLM / automation | `tabler-outline/robot` | P01, P10 |
| Lore / memory | `tabler-outline/book` | P07 |
| Code / trace excerpt | `tabler-outline/code` | P12 |
| Chart / metrics | `tabler-outline/chart-bar` | P13 |
| Message / dialogue | `tabler-outline/message-2-code` | P02, P12 |
| Timing | `tabler-outline/clock-check` | P13 |
| Search / retrieval | `tabler-outline/user-search` | P07 |

---

## VII. Visualization Reference List

No chart-library templates are locked. All visualizations are free-design SVG diagrams based on the project evidence:

| Page | Visualization | Usage |
| ---- | ------------- | ----- |
| P04 | Git evolution timeline | Four project phases mapped to key commits |
| P05 | Architecture flow | Input -> observation -> retrieval -> mind -> decision -> validation -> state -> trace |
| P06 | Module boundary map | Ownership table / swimlane |
| P07 | Memory/RAG flow | Recent context, lore, long-term memory, background jobs |
| P09 | Autonomous runtime sequence | world_event -> inbox -> ActionCatalog -> validation -> mailbox/trace |
| P10 | Traveler loop | profile -> observe -> retrieve -> decide -> act -> reflect -> export |
| P13 | Evaluation matrix | evidence source, current observation, limitation, next metric |

**Runners-up considered**:

- `timeline_horizontal` rejected: Git timeline is evidence-oriented and needs commit labels rather than a generic date axis.
- `process_flow` rejected: core architecture needs module ownership and trace/state side paths, so free-design is clearer.
- `matrix_table` rejected: evaluation page combines evidence matrix with limits/future-work path, not a pure chart template.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | ---------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| player_ui_desktop.png | 1440x1100 | 1.31 | Real desktop UI evidence with trace panel and interaction surface | Screenshot | #19 Image floating in whitespace with thin frame and caption + #48 Side-by-side comparison | user | Existing | Project screenshot copied from `data/player_ui_desktop.png` | none | local |
| player_ui_mobile.png | 390x900 | 0.43 | Real mobile UI evidence, used as a narrow device-style inset | Screenshot | #17 Picture-in-picture inset + #56 Image triptych | user | Existing | Project screenshot copied from `data/player_ui_mobile.png` | none | local |

No AI-generated image rows. The deck deliberately avoids large AI backgrounds.

---

## IX. Content Outline

### P01 Cover

- **Title**: 记忆驱动的可验证 LLM 角色 Agent 系统
- **Subtitle**: 从单 NPC 对话到 Traveler living-world runtime 的课程项目汇报
- **Content**: 简洁课程汇报封面：项目题目、汇报简介、汇报人薛良玺、时间 2026年6月9日。
- **Takeaway**: 这不是普通聊天界面，而是一个将 LLM 对话放入状态、记忆、校验和 trace 链路中的角色 Agent 原型。

### P02 Problem

- **Title**: 问题定义：角色聊天不等于世界状态
- **Content**: 普通 LLM 对话容易把“说出来的内容”误当成“已经发生的事实”。课程项目的核心问题是：如何保留角色语言能力，同时保证任务、物品、地点、关系这些世界事实由程序规则维护。
- **Visual**: Three-risk comparison: hallucinated state, weak memory, no replayable evidence.

### P03 Goal

- **Title**: 项目目标：状态 + 记忆 + 校验 + Trace
- **Content**: 构建一个 LLM 角色 Agent 系统，让 NPC 能读取世界设定、检索记忆、形成主观计划、输出结构化 decision，并在 ActionValidator 和任务状态机校验后才改变世界状态。
- **Visual**: Four-pillar goal map.

### P04 Project Evolution

- **Title**: 项目演进：从“会聊天”到可验证 living world
- **Content**: 按能力阶段解释项目为什么演进：单 NPC 记忆对话原型、分层上下文与玩家端、NPCMind / NarrativeEnvironment / ActionValidator、autonomous runtime 与 Traveler timeline。
- **Visual**: Capability evolution timeline without commit hashes; each phase explains motivation and resulting capability.

### P05 System Architecture

- **Title**: 总体架构：输入到 timeline 的受控链路
- **Content**: 玩家或 Traveler 输入进入 observation；系统加载上下文与检索结果；NPCMind 生成主观状态；LLM 产生 decision；ActionValidator 校验；NarrativeEnvironment 写入 SQLite 并生成 trace / timeline。
- **Visual**: Left-to-right architecture flow.

### P06 Module Boundary

- **Title**: 模块职责：LLM 参与认知，系统掌握执行权
- **Content**: 重点展示 NarrativeEnvironment、NPCMind、Memory/Retrieval、LLM Decision、ActionValidator、SQLite World State、Timeline Export、Traveler Runtime、autonomous NPC Runtime 的职责边界。
- **Visual**: Three-layer responsibility map: cognition and intent, validation and execution, state and evidence.

### P07 Memory and Retrieval

- **Title**: 记忆与检索：让角色带着上下文行动
- **Content**: 系统把近期对话、长期记忆、稳定 lore、任务状态和后台 memory jobs 结合起来，使回复和 decision 不只依赖当前一句输入。
- **Visual**: Retrieval stack feeding observation and decision.

### P08 NPCMind + ActionValidator

- **Title**: NPCMind + ActionValidator：自由表达，受控执行
- **Content**: NPCMind 把 observation 转成 belief、emotion、goal、plan 和 social strategy；ActionValidator 拦截或降级越界行动，防止语言直接改写 SQLite 状态。
- **Visual**: Two-layer control diagram.

### P09 Autonomous NPC Runtime

- **Title**: Autonomous NPC Runtime：NPC 响应世界事件
- **Content**: world event 写入后进入 NPC event inbox；系统根据 NPC 状态和 ActionCatalog 构造可行动作集合；LLM 输出 constrained decision；结果经过校验后进入 mailbox、runtime state 和 trace。
- **Visual**: Event-driven sequence.

### P10 Traveler Runtime

- **Title**: Traveler Runtime：用 profile 驱动自动探索
- **Content**: Traveler 不是普通玩家输入，而是 YAML profile 配置的角色 Agent。它每轮观察世界、检索线索、选择移动/询问/检查/等待，并把行动理由、NPC 回复、状态变化和 arc evidence 导出。
- **Visual**: Loop diagram with profile, decision, action, reflection, export.

### P11 Real Evidence

- **Title**: 真实证据：界面、课堂 trace 与多 NPC 覆盖
- **Content**: 当前项目保留 Streamlit 调试台、FastAPI workflow、React/Vite 玩家端、classroom showcase trace 和 Sable route trace 等多条展示路径；截图和 Markdown timeline 证明系统可运行。
- **Visual**: Desktop UI screenshot + trace evidence tags; no mobile screenshot.

### P12 Sable Route Case

- **Title**: Sable 路线：语言行为与状态变化分离
- **Content**: Sable 可以试探、转移话题、引导 Traveler，但不能直接声明遗迹入口解锁或发放物品。真实 trace 显示 Traveler action allowed、Sable action accepted、关系值变化，但任务推进仍由规则控制。
- **Visual**: Trace card with reason, NPCMind belief, validator result, state change, response constraint.

### P13 Evaluation and Limits

- **Title**: 评估：已有证据与下一步指标
- **Content**: 当前评估以 demo trace、JSON / Markdown timeline 和人工复盘为主。已有证据能说明角色边界、状态一致性、Traveler profile 差异和 trace 可解释性；不足是缺少系统化指标和可视化回放。
- **Visual**: Three-card evaluation summary: current evidence, what it shows, next metrics, plus a concise limits note.

### P14 Closing

- **Title**: 结论：可控 LLM 角色需要可追踪执行
- **Content**: 项目的关键设计是把 LLM 放入受规则约束的运行流程中：语言生成提供表达和推理能力，系统流程维护事实、校验行动并记录结果。
- **Takeaway**: 后续工作应加强多 Agent 调度、长期记忆质量、自动评估和 timeline 可视化。

---

## X. Speaker Notes Plan

- Notes language: Chinese.
- Target pace: 30-45 seconds per page, total 8-10 minutes.
- Notes should sound like a course presentation, not a marketing pitch.
- Each note should briefly state page purpose, explain the visual, and connect to the next page.

---

## XI. Technical Constraints

- SVG viewBox must be `0 0 1280 720`.
- Use only colors, fonts, icons, image paths, and rhythms declared in `spec_lock.md`.
- Avoid banned SVG features: `rgba()`, `<style>`, `class`, `<foreignObject>`, `textPath`, `@font-face`, animation/script/iframe, `<mask>`, and group opacity.
- Text must remain editable in PPTX where practical; screenshots are source evidence only.
- Do not invent metrics. All claims must come from the source brief, course report, trace files, screenshots, or Git history.
