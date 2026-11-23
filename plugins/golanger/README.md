# golanger

Rob Pike 的 Go Proverbs 编程哲学，纯知识包，无 MCP 依赖。

## 迁移说明（2.0.0）

原 `golang-dev` 插件已拆分为两个：

| 插件 | 内容 | 依赖 |
| --- | --- | --- |
| `golanger`（本插件） | `rob-pike` | 无 |
| `golang-mcp` | `gopls`、`mcp-orch` + MCP 服务器声明 | 需本机安装 `gopls` |

原 `golang-dev` 用户若需要 gopls 的 MCP 语义能力，改装 `golang-mcp`。只想要 Go Proverbs 的，本插件即可。

宿主已内置原生 LSP 工具（如 omp 的 `lsp`）时，不需要 `golang-mcp`。

## 参考资料
- [rob-pike](https://github.com/andrsj/go-proverbs-review-skill)
