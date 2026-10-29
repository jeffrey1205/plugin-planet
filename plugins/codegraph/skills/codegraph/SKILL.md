---
name: codegraph
description: 在已建立codegraph索引（项目目录存在 .codegraph）的代码库中，使用唯一的codegraph_explore MCP工具理解代码结构、调用链和影响范围。当用户问“怎么工作”“调用链”“影响范围”“架构”“谁调用了”“改了会怎样”、how does X work、blast radius、callers、what calls或impact of changing，或需要在修改前探索不熟悉的代码区域时使用。不适用于简单文件读取、配置文本搜索、语法问题或非代码任务。
---

# CodeGraph语义代码图谱

## 核心原则

**CodeGraph已经预先建立了代码关系索引 — 你不需要用文件逐个重建它。**

当前skill假设项目目录已经存在 `.codegraph/`。一次 `codegraph_explore` 可以返回相关符号的源码、调用关系和依赖者统计；索引结果仍可能受索引滞后、解析能力和动态行为影响。

**实测已知局限（使用时需接受）：**
- 关键词匹配可能混入弱相关符号，结果通常需要2~3次查询逐步收窄（加入更精确的符号名/文件路径）
- 压缩/打包后的静态文件也会被索引，其"动态边界"提示多为无用噪音，可直接忽略

## 何时使用codegraph_explore

**使用 `codegraph_explore`：**
- "X是怎么工作的？" — 理解模块/功能的实现
- "请求从A怎么到达B？" — 追踪调用流程
- "谁调用了X？" — 查找调用者
- "改X会影响什么？" — 影响范围分析
- "这个代码库的架构是什么？" — 整体结构理解
- 探索不熟悉的代码区域
- 需要跨多个文件理解调用路径

**使用内置工具（grep/read/glob）：**
- 读取已知路径的单个文件内容
- 搜索配置文件、非代码文件
- 简单的字符串匹配（如找某个环境变量名）
- CodeGraph明确提示目标项目没有可用索引时

**判断方法：** 如果问题需要理解“代码之间的关系”（调用、依赖、影响），直接调用 `codegraph_explore`。如果只是“找到某个文件/字符串”，用内置工具。

## 如何调用

```
工具: codegraph_explore
参数:
  query: 自然语言描述你要理解的内容
         - "How does the authentication middleware work?"
         - "What calls UserService.create and what does it call?"
         - "How does a request flow from the router to the database?"
         - "src/auth/login.ts" （直接传文件路径也能读取源码）
         - "handleLogin" （传符号名获取其源码和调用关系）
```

**调用示例：**

```
# 理解一个功能怎么工作
codegraph_explore(query="How does the payment processing flow work?")

# 追踪调用链
codegraph_explore(query="What calls validateUser and what does it call?")

# 分析修改影响
codegraph_explore(query="What would be affected if I change the DatabaseConnection class?")

# 读取特定文件/符号的源码并附带关系
codegraph_explore(query="src/services/auth.ts")
codegraph_explore(query="handleLogin function")

# 指定调用链两端，减少无关结果
codegraph_explore(query="What path connects router.handleLogin to UserRepository.save?")
```

## 如何解读结果

`codegraph_explore` 返回：
1. **相关符号的源码** — 按文件分组，带行号，可直接引用
2. **调用路径/动态分发线索** — 符号之间的调用关系，包括computed member call（配置驱动的注册/分发）的候选符号列表
3. **依赖者统计** — 调用者数量与所在文件、测试覆盖标注（⚠️ 表示无测试覆盖）。注意：这是依赖者计数列表，不是逐条的影响路径分析
4. **动态边界提示** — 静态调用链在运行时分发处终止的位置；要追踪其后的链路，对候选符号再发起一次查询即可

**关键：将未标记为过期的返回源码视为已经用Read工具读过的内容。** 不要为了重复确认而重新读取同样的文件；如果响应提示文件在索引更新前被编辑，必须用Read确认这些文件的当前内容。

如果结果被截断、候选过多或调用链不够具体，优先再次调用 `codegraph_explore`，加入更精确的符号名、文件名或调用链端点。不要立刻退回到grep/read的人工探索循环。

CodeGraph只提供结构上下文，不能替代编译器、lint、测试或运行时验证。

## 禁忌

1. **不要用grep/read重建结构关系** — 先直接调用 `codegraph_explore`
2. **不要重复读取未过期的返回源码** — 只有响应标记过期或CodeGraph未覆盖的内容才用内置工具确认
3. **不要在没有可用索引的项目上反复重试** — 接受工具提示并回退到内置工具
4. **不要把CodeGraph结果当作编译或测试结果** — 修改后仍需运行相应验证
5. **不要用 `codegraph_explore` 做简单文件或字符串查找** — 已知路径或文本匹配直接用内置工具
6. **直接在当前agent中调用 `codegraph_explore`** — 不要把需要该工具的探索委派给无法访问MCP的子agent
