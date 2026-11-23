# golang-mcp

通过 MCP 接入 gopls 的 Go 语义分析能力，适用于支持 MCP 的宿主（Claude Code / Codex / CodeBuddy）。

## 前置条件

`gopls` 必须在 PATH 上，否则 MCP 服务器启动失败：

```bash
go install golang.org/x/tools/gopls@latest
export PATH="$PATH:$(go env GOPATH)/bin"
```

验证：`gopls version`。

## 内容

| 组件 | 作用 |
| --- | --- |
| `.mcp.json` | 声明 `gopls mcp` 服务器 |
| `skills/gopls` | gopls MCP 工具的使用指导 |
| `skills/mcp-orch` | codegraph / gopls 的选用编排：关系走 codegraph，事实走 gopls |

## 何时不需要它

宿主已内置原生 LSP 工具时（例如 omp 的 `lsp`，已覆盖 definition / references / hover / symbols / rename / code_actions / diagnostics / type_definition / implementation），本插件的 gopls MCP 属于重复路径，无需安装。

若同时使用 `codegraph` 插件，才需要 `mcp-orch` 的编排规则。

## 从 golang-dev 迁移

原 `golang-dev` 已拆分：Go Proverbs 知识移入 `golanger` 插件，本插件只保留 MCP 相关部分。
