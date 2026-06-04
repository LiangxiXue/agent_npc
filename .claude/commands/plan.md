---
description: 为多步骤实现任务编写可执行计划
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# /plan — 编写实现计划

为多步骤任务编写实现计划，保存到 `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`。

## 流程

1. **范围检查** — 是否覆盖多个独立子系统？如果是，先分解为子项目
2. **文件结构** — 先画出哪些文件要创建/修改，每个文件负责什么
3. **任务分解** — 每个步骤 2-5 分钟，checklist 格式
4. **无占位符** — 禁止 TBD/TODO/implement later/appropriate error handling

## 计划模板

```markdown
# [Feature Name] Implementation Plan

**Goal:** [一句话描述]
**Architecture:** [2-3 句方法说明]
**Tech Stack:** [关键技术]

---

### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

- [ ] **Step 1: Write the failing test**
  [具体测试代码]
- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/path/test.py::test_name -v`
  Expected: FAIL
- [ ] **Step 3: Write minimal implementation**
  [具体实现代码]
- [ ] **Step 4: Run test to verify it passes**
  Expected: PASS
- [ ] **Step 5: Commit**
```

## 自审清单
1. 每个 spec 需求都有对应 task？
2. 没有 TBD/TODO？
3. 前后 task 的类型/签名一致？

完成后提供执行选择：Subagent 驱动（推荐）或 Inline 执行。
