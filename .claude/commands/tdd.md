---
description: 测试驱动开发 — RED(写失败测试) → GREEN(最小实现) → REFACTOR(清理)
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# /tdd — 测试驱动开发

**铁律: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST**

## RED — 写失败测试

1. 写一个最小的测试，描述期望行为
2. 一个测试 = 一个行为
3. 清晰命名: `test_<what>_<expected>`
4. 用真实代码，不是 mock（除非不可避免）

```bash
# 运行测试，确认失败
python -m unittest tests.test_xxx -v
```

确认：
- 测试确因功能缺失而失败（不是拼写错误）
- 失败消息符合预期

## GREEN — 最小实现

1. 写最简单代码让测试通过
2. 不添加测试没覆盖的功能
3. 不过度设计

```bash
# 运行测试，确认通过
python -m unittest tests.test_xxx -v
```

确认：
- 新测试通过
- 已有测试不受影响
- 输出干净（无 error/warning）

## REFACTOR — 清理

- 消除重复
- 改善命名
- 提取辅助函数
- 保持测试绿

## 红旗信号

- 测试直接通过（可能测的是已有行为）→ 检查测试
- 实现前写完了代码 → 删掉重来
- 想跳过写测试 → 这就是最需要 TDD 的时候
