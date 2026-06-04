---
description: 总结当前任务状态，方便另一个 AI 或人类接手
allowed-tools: Bash(git *), Read, Grep, Glob
---

# /handoff — 任务交接

总结当前工作状态，输出交接报告。

## 流程

1. **Git 状态**
   ```bash
   git status
   git diff --stat
   git log --oneline -5
   ```

2. **输出交接报告**

```markdown
## Handoff Report: [分支名]

### 目标
[一两句话描述在做什么]

### 已完成
- [已完成的具体事项]

### 进行中
- [当前正在做的事项和进度]

### 待解决
- [待解决的问题或阻塞]

### 关键文件
- `path/to/file` — 描述

### 下一步
1. [下一步的具体操作]
2. [下一个要运行的命令]

### 验证状态
- [最后验证的结果或需要验证的内容]
```
