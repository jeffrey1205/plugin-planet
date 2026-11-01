---
name: codegraph
description: 代码结构查询的默认入口：问「怎么工作/调用链/影响范围/谁调用/改了会怎样」时，必须先加载本 skill 并调用 codegraph_explore，不要先用 grep/read 重建关系。仅适用于已存在 .codegraph 索引的代码库；简单文件读取或文本搜索不适用。
---

# CodeGraph 语义代码图谱

**前提**：项目目录存在 `.codegraph/`。索引已经预建好，不要用 grep/read 重建代码关系。

**已知局限**（使用时需接受）：
- 关键词匹配会混入弱相关符号，通常需要 2~3 次查询逐步收窄
- 打包/压缩后的静态文件也会被索引，其"动态边界"提示多为噪音
- 索引滞后写入约 1 秒，刚改过的文件可能尚未更新

## 调用

`codegraph_explore(query="...")`，query 可以是自然语言、符号名或文件路径：

```
codegraph_explore(query="How does the payment processing flow work?")
codegraph_explore(query="What calls validateUser and what does it call?")
codegraph_explore(query="What path connects router.handleLogin to UserRepository.save?")
codegraph_explore(query="src/services/auth.ts")   # 传路径也能取源码
```

## 结果解读

返回四块：相关符号源码（按文件分组、带行号）、调用路径与动态分发候选、依赖者统计（**计数清单，不是逐条影响路径**；含是否被测试覆盖）、动态边界提示（静态调用链在运行时分发处终止，**对候选符号再查一次即可续上**）。

- 未标记过期的源码**视为已经 Read 过**，不要重复读；只有标记过期时才用 Read 确认当前内容。
- 结果被截断或候选过多时，**换更精确的符号名/文件路径再查一次**，不要立刻退回 grep/read 的人工探索。
- CodeGraph 只提供结构上下文，**不能替代编译、lint、测试或运行时验证**。

## 边界

- 已知路径的单文件读取、配置或非代码文本搜索 → 用内置工具，不要用 `codegraph_explore`
- 项目没有 `.codegraph` 索引 → 不要反复重试，直接用内置工具
