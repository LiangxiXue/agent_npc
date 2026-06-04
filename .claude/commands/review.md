---
description: 代码审查 — 检查当前变更的 bug、回归、测试缺口
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

# /review — 代码审查

对当前分支的变更做代码审查。**重点：bug、回归、测试缺口。**

## 流程

1. **获取变更范围**
   ```bash
   git diff origin/main...HEAD --stat
   git diff origin/main...HEAD
   ```

2. **审查维度**
   - **Bug**: 逻辑错误、边界条件、空值处理、并发问题
   - **回归**: 是否破坏已有功能？检查调用点
   - **测试缺口**: 新增代码是否有测试？关键路径是否覆盖？
   - **CLAUDE.md 合规**: 是否遵循项目规则？

3. **输出格式**
   ```
   ## Code Review: [分支名/变更描述]

   ### Critical (需立即修复)
   - [问题描述] — [文件:行号] — [为什么严重]

   ### Important (推进前修复)
   - [问题描述] — [文件:行号]

   ### Minor (后续改进)
   - [建议]

   ### 总结
   [整体评估]
   ```

4. **禁止**
   - 表演性赞同
   - 只夸奖不找问题
   - 跳过测试缺口检查

## 和 `/review` 内置 skill 的关系

如果当前项目已安装 `code-review` skill，优先使用它（更全面的并行审查）。本命令作为轻量替代，适合快速自审。
