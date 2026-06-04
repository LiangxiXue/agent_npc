# CLAUDE.md — agent-npc 项目配置

## 用户偏好

- **默认 Shell**: Windows PowerShell（非 Bash/CMD）。在命令行中应使用 PowerShell 语法。
- **技术问题优先读取**: 真实本地文件、真实 repo 状态、真实运行输出，不凭印象回答。先 Read/Grep/Glob，再给判断。
- **修改代码前**: 检查相关文件内容和 git 状态（`git status`、`git diff`）。
- **不要使用危险命令**: 禁止 `git reset --hard`、`git checkout --`、`git clean -fd` 或其他会丢弃用户本地改动的命令，除非用户明确要求。
- **中文提问 → 中文回答**: 当用户使用中文提问时，默认以中文回答。
- **代码审查格式**: 先列 bug/风险/缺测试，再给总结。不写表演性赞同。
- **完成前验证**: 声称完成前必须运行相关验证命令，报告验证结果。如果无法运行，明确说明原因。

## 核心行为规则（来自 Superpowers 工作流迁移）

### 规则 1: 先检查 Skill/Workflow，再动手

每次任务开始前，检查是否有相关的 skill 或 workflow 可用。即使只有 1% 的可能适用，也要先调用 Skill 工具检查。常见场景映射：

| 场景 | 使用 |
|---|---|
| 新功能/改行为 | 先 `/brainstorm`，再 `/plan` |
| Bug/失败/异常 | `/debug` |
| 多步骤实现 | `/plan` → 按计划执行 |
| 声称完成前 | `/verify` |
| 写新代码 | `/tdd` |
| 检查变更 | `/review` |
| 交接任务 | `/handoff` |

**不要先做再想。先检查流程，再动手。**

### 规则 2: 系统性调试（来自 systematic-debugging）

遇到任何 bug、测试失败、异常行为：
1. **Phase 1 — 根因调查**: 读错误信息 → 复现 → 检查近期变更 → 收集证据
2. **Phase 2 — 模式分析**: 找对标成功案例 → 对比差异
3. **Phase 3 — 假设验证**: 形成单一假设 → 最小变更验证 → 单变量测试
4. **Phase 4 — 实施修复**: 先写失败测试 → 单一修复 → 验证通过

**铁律**: 没有根因调查，不能提出修复。连续 3 次修复失败 → 质疑架构，不要继续修。

### 规则 3: 验证后再声称完成（来自 verification-before-completion）

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

- 声称"测试通过" → 必须刚运行过测试命令
- 声称"已修复" → 必须刚验证过原始症状已消失
- 声称"完成" → 必须逐项核对需求清单
- 禁止使用 "should"、"probably"、"seems to" 描述状态
- 禁止在验证前表达满意（"Great!"、"Done!"）

### 规则 4: 测试驱动开发（来自 test-driven-development）

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

- Red: 写最小失败测试 → 确认它因正确原因失败
- Green: 写最小代码让测试通过
- Refactor: 清理重复，保持测试绿
- 实现前写了代码？删掉重来。不要保留"参考"代码。

### 规则 5: 收到 Review 反馈时（来自 receiving-code-review）

- 先验证反馈是否成立，再实现
- 不写表演性赞同（"You're absolutely right!"）
- 多个反馈项 → 先澄清不明确的 → 再按优先级实现
- 外部反馈 = 需要评估的建议，不是命令
- 实现后只陈述改了什么，不写 "Thanks"

### 规则 6: 重要实现后请求 Review（来自 requesting-code-review）

- 重要功能完成后，用 `/review` 做代码审查
- 重点查 bug、回归、测试缺口
- Review 结果分三级: Critical（立即修）、Important（推进前修）、Minor（记录后续）

## Git 使用规则

- 当前分支: `codex/living-world-demo`，主分支: `main`
- 提交前验证测试通过
- 不要 force push 到 main
- 使用 `git status` 检查变更后再提交
- 使用 `/handoff` 完成分支开发

## 项目特定规则

- 本项目是记忆驱动的 NPC Agent 系统
- 技术栈: Python 3.11 + FastAPI + SQLite + React/Vite 前端
- 测试: `python -m unittest discover -s tests -v`
- 所有 74 个测试应保持通过
- LLM 配置在 `.env` 文件中（不要提交）
- 详细的架构说明在 `docs/design/architecture.md`

## 多 Agent 使用规则

- Subagent 适合: 研究、审查、测试定位
- 不要让多个 subagent 同时大范围改同一批文件
- 每个 subagent 应处理独立的问题域
- 多个不相关的失败可以并行调查
