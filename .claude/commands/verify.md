---
description: 运行验证命令并报告结果 — 声称完成前必须执行
allowed-tools: Bash
---

# /verify — 验证完成状态

**铁律: 没有新鲜验证证据 = 不能声称完成。**

## 流程

1. **确认验证命令** — 什么命令能证明当前声明？
2. **运行完整命令** — 全新运行，不使用缓存
3. **读取完整输出** — 检查退出码、统计失败数
4. **核对结果** — 输出是否支持声称？
   - No → 报告实际状态
   - Yes → 带证据报告

## 常见声明的验证命令

| 声称 | 验证命令 |
|---|---|
| Tests pass | `python -m unittest discover -s tests -v` (0 failures) |
| Build succeeds | Build command (exit 0) |
| Bug fixed | 运行原始复现步骤 |
| All requirements met | 逐项核对需求清单 |

## 禁止

- "Should work now"
- "I'm confident"
- 使用上次运行结果
- 部分验证代替完整验证
- 验证前表达满意

## 输出格式

```
✅ [验证命令] → [结果] — [声明成立]
```
或
```
❌ [验证命令] → [实际结果] — [差距描述]
```
