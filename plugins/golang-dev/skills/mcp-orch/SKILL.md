---
name: mcp-orch
description: 当gopls和codegraph MCP同时可用时，用于Go项目的理解、实现、调试、重构和代码审查。编排codegraph做跨文件结构、调用链和影响范围探索，编排gopls做Go符号、类型、包API、引用、重命名和诊断；文件内容读取、配置搜索、测试和行为验证仍使用agent的内置工具。
---

# Go开发工具编排

这个skill是上层工作流，不替代 `gopls` 和 `codegraph` 各自的skill。目标是先选对信息源，再用最少的重复探索完成Go开发任务。

## 工具边界

| 问题类型 | 首选工具 | 说明 |
| --- | --- | --- |
| 功能如何工作、跨文件调用流程、架构、宽泛影响范围 | `codegraph_explore` | 一次调用获取相关源码、关系和影响摘要 |
| 精确定位Go符号候选 | `go_search` | 模糊匹配，结果需要结合文件和限定名确认 |
| 查看Go包的导出API | `go_package_api` | 使用 `packagePaths`，不读取整个包源码 |
| 查找已解析Go符号的引用 | `go_symbol_references` | 使用包含符号的绝对文件路径和符号名 |
| Go文件的跨文件依赖摘要 | `go_file_context` | 在读取大文件或编辑前缩小范围 |
| Go符号重命名 | `go_rename_symbol` | 返回diff，不直接修改文件 |
| 编辑后的Go workspace检查 | `go_diagnostics` | 检查解析、构建和相关诊断，不替代测试 |
| Go workspace概览 | `go_workspace` | 只在需要Go workspace或模块信息时调用 |
| Go漏洞检查 | `go_vulncheck` | 仅在安全检查或依赖审计任务中调用 |
| 已知文件内容、配置、日志、普通字符串 | 宿主agent的内置读取和搜索工具 | 不需要代码关系图谱 |
| 编译、测试、lint和运行行为 | 宿主agent的shell或项目内置工具 | MCP结果不能替代这些验证 |

CodeGraph在本skill中只使用MCP暴露的 `codegraph_explore`。不要寻找或调用未暴露的窄化CodeGraph工具。

## 选择规则

1. 先判断用户要的是“关系”还是“事实”。调用、依赖、流程和影响属于关系；某个Go符号的精确引用、类型或重命名属于事实。
2. 关系问题先调用 `codegraph_explore`，并在查询中写出具体符号、文件或调用链两端。
3. 需要Go类型精度时，再用gopls对CodeGraph找到的文件和符号做确认。不要为了同一个宽泛问题同时调用两套探索工具。
4. 已知文件的完整内容直接使用宿主agent的内置读取工具；配置、文档、日志和环境变量使用内置文本搜索或读取工具。
5. 修改完成后使用 `go_diagnostics`，再运行与任务相关的测试、lint或构建命令。

## 常用调用格式

以下参数名以实际MCP tool schema为准；文件参数使用绝对路径。

```text
codegraph_explore(query="How does router.handleLogin reach UserRepository.save?")

go_search(query="UserService")
go_workspace()
go_package_api(packagePaths=["github.com/example/project/pkg/store"])
go_symbol_references(file="/absolute/path/service.go", symbol="UserService.Create")
go_file_context(file="/absolute/path/service.go")
go_rename_symbol(file="/absolute/path/service.go", symbol="OldName", new_name="NewName")
go_diagnostics(files=["/absolute/path/service.go"])
go_vulncheck()
```

`go_symbol_references` 需要从指定文件上下文解析符号。若解析失败，先用 `go_search` 找候选，再提供更准确的限定名。`go_rename_symbol` 返回需要应用的修改；只有应用diff后才算完成重命名。

## 标准工作流

### 理解功能或调用流程

1. 用 `codegraph_explore` 查询功能、入口和目标调用点，例如“请求从router到数据库的流程”。
2. 把返回的源码和调用路径视为已读内容；不要用内置搜索和读取工具重复重建同一关系。
3. 如果需要Go的精确符号引用或类型信息，用返回的绝对文件路径和符号名调用gopls。
4. 如果结果被截断、候选过多或路径不明确，继续用更具体的符号名、文件名或端点调用 `codegraph_explore`。

### 修改、重构或重命名

1. 先用 `codegraph_explore` 了解目标符号的实现、调用路径和宽泛影响范围。
2. 对Go符号用 `go_symbol_references` 评估精确引用；普通字段或API变化也要检查跨包使用。
3. 重命名优先调用 `go_rename_symbol`，应用其返回的diff，不要用正则替换。
4. 使用 `go_diagnostics(files=[...])` 检查workspace诊断。
5. 运行相关测试、lint或构建，确认行为和生成物没有回归。

### 修复bug或实现功能

1. 如果需要理解现有流程，先用 `codegraph_explore`，查询中包含功能名、入口符号或目标文件。
2. 对明确的Go类型、接口和引用问题使用gopls；对配置、协议样例、日志等非Go内容使用内置工具。
3. 编辑代码后检查CodeGraph响应是否提示索引滞后；被标记为过期的文件用宿主agent的内置读取工具确认当前内容。
4. 运行 `go_diagnostics`，然后执行能证明修复行为的测试，而不是只依据MCP返回结果下结论。

## 结果与失败处理

- CodeGraph返回的是索引中的结构上下文，可能受索引滞后、解析能力和动态行为影响；它不能证明代码编译或运行正确。
- 编辑后，如果CodeGraph响应标记相关文件尚未同步，直接读取这些文件，不要继续引用旧源码。
- gopls无诊断不等于测试通过；`go_rename_symbol` 返回diff不等于文件已经修改。
- 工具返回未索引、workspace未加载、符号歧义或参数错误时，不要原样重复调用。先缩小查询、修正绝对路径和参数，仍失败就使用内置工具并说明语义工具未能覆盖。
- CodeGraph没有可用索引时停止对该项目重试；索引建立是环境准备工作，不由本skill自动完成。

## 禁忌

1. 不要用CodeGraph做简单文件或字符串查找。
2. 不要用gopls处理配置、文档、日志或非Go文件。
3. 不要用两套工具重复回答同一个宽泛探索问题。
4. 不要把CodeGraph影响摘要或gopls diagnostics当作测试、lint或运行结果。
5. 不要在应用 `go_rename_symbol` 返回的diff前声称重命名已完成。
6. 需要CodeGraph时在当前agent直接调用 `codegraph_explore`；只有确认子agent同样能访问该MCP时才委派探索。
