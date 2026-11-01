---
name: mcp-orch
description: Go 项目的语义工具编排：先判断要「关系」还是「事实」，再决定用 codegraph 还是 gopls。关系（怎么工作、调用链、依赖、影响范围）走 codegraph_explore；事实（符号引用、类型、包 API、重命名、诊断）走 gopls；只有一个或都没有时按可用性降级并说明缺什么。文件读取、配置搜索、测试与行为验证始终用内置工具。
---

# Go 开发工具编排

只解决一件事：**同一个问题该用哪套语义工具**。工具用法看各自的 skill。

## 先分类

- **关系**：怎么工作、调用链、依赖、影响范围 → `codegraph_explore`
- **事实**：某个 Go 符号的引用、类型、包 API、重命名、诊断 → gopls

宽泛探索先走 codegraph；需要类型精度再用 gopls 确认。**不要为同一个宽泛问题两套都跑一遍。**

## 按可用工具降级

| 可用情况 | 做法 |
|---|---|
| 两个都在 | 关系用 codegraph，事实用 gopls（拿 codegraph 返回的绝对路径和符号名去问） |
| 只有 codegraph | 关系够用；事实类问题明说「无 gopls，引用未做类型级确认」 |
| 只有 gopls | 事实够用；关系类用 `go_search` + `go_file_context` 近似，并说明拿不到完整调用链 |
| 都没有 | 用内置 grep/read，并说明语义工具不可用 |

## 边界与失败

- 已知文件的完整内容、配置/日志/文档、测试与运行行为：用内置工具，不走 MCP。
- 参数错误、符号歧义、workspace 未加载：不要原样重试，缩小查询或修正绝对路径；仍失败就回退内置工具并说明。
- codegraph 没有 `.codegraph` 索引：停止重试，索引准备不属于本 skill。
- `go_diagnostics` 没报错 **不等于**测试通过；`go_rename_symbol` 返回 diff **不等于**文件已改。
