---
name: gopls
description: 使用gopls MCP工具进行Go代码语义分析。当项目包含Go文件且gopls能加载对应workspace，任务涉及符号搜索、引用、包API、重命名、workspace诊断、项目结构或Go漏洞检查时使用；优先确认go.mod或go.work。适合Go特有的类型和AST分析，不用于非Go文件、普通文本搜索或行为验证。
---

# gopls 语义代码工具

**gopls 是 Go 官方语言服务器，理解 AST 和类型系统，不是文本搜索。** 结果作为语义上下文，不能替代编译器、测试或人工确认。

**前置**：目标文件属于 gopls 已加载的 Go workspace（通常有 `go.mod` 或 `go.work`）。

## 8 个工具

| 工具 | 用途 |
|---|---|
| `go_workspace` | workspace 摘要：类型、根目录、主模块 |
| `go_search` | 模糊搜符号，大小写不敏感，最多 100 个 |
| `go_package_api` | 包的导出 API 与文档注释 |
| `go_symbol_references` | 指定文件内某符号的引用位置 |
| `go_file_context` | 文件的跨文件依赖摘要 |
| `go_rename_symbol` | 生成 AST 级重命名 diff |
| `go_diagnostics` | workspace 的解析、构建与诊断 |
| `go_vulncheck` | workspace 漏洞检查 |

## 两个工作流

- **读**：`go_workspace` → `go_search` 定位符号 → `go_file_context`（首次读文件后必做）→ `go_package_api`（看对外 API）
- **改**：`go_symbol_references` 评估影响 → 改代码 → `go_diagnostics` → 依赖有变更再 `go_vulncheck` → 跑相关测试

## 参数与陷阱

- `go_symbol_references` / `go_file_context` / `go_rename_symbol` 要**绝对路径**；符号用限定名（如 `UserService.Create`）。
- `go_rename_symbol` **只返回 diff，不改文件**；应用后再跑 `go_diagnostics`。
- `go_file_context` 返回的"所属包"是 `go.mod` 的 module 名，**不是** `package` 子句，别据此推断包名。
- `go_vulncheck` **没有可达性标注**：报出只代表依赖存在该漏洞，不代表当前代码走到；要精确结果用官方 CLI。
- `go_diagnostics` 没有报错 **不等于测试通过**。
- 非 Go 文件（配置、日志、前端）和普通文本搜索用内置 grep/read，不要用这些工具。
