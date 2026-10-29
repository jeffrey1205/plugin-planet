# plugin-planet

个人Claude Code / Codex / CodeBuddy插件集合，包含MCP服务器、编程哲学Skill、开发工具、思维工具Skill等扩展。

## 安装方式

### Claude Code

```bash
/plugin marketplace add jeffrey1205/plugin-planet

/plugin install codegraph@plugin-planet
/plugin install golang-dev@plugin-planet
/plugin install coder@plugin-planet
/plugin install thinker@plugin-planet
/plugin install rtk@plugin-planet
/plugin install statusline@plugin-planet
/plugin install docs@plugin-planet
/plugin install agents@plugin-planet
```

### Codex

```bash
codex plugin marketplace add jeffrey1205/plugin-planet

codex plugin add codegraph@plugin-planet
codex plugin add golang-dev@plugin-planet
codex plugin add coder@plugin-planet
codex plugin add thinker@plugin-planet
codex plugin add docs@plugin-planet
```

### CodeBuddy

```bash
/plugin marketplace add jeffrey1205/plugin-planet

/plugin install codegraph@plugin-planet
/plugin install golang-dev@plugin-planet
/plugin install coder@plugin-planet
/plugin install thinker@plugin-planet
/plugin install docs@plugin-planet
/plugin install statusline@plugin-planet
/plugin install agents@plugin-planet
```

## 插件列表

| 插件名 | 类型 | 描述 |
|--------|------|------|
| [codegraph](./plugins/codegraph) | MCP Server + Skill | 代码图谱MCP服务器，提供语义搜索、调用图分析、影响分析 |
| [golang-dev](./plugins/golang-dev) | MCP Server + Skill | Go开发工具集：gopls MCP语义分析、MCP编排工具、Rob Pike的Go Proverbs编程哲学指导 |
| [coder](./plugins/coder) | Skill | 编程大师思维工具集：Karpathy编码指南与Linus Torvalds的代码品味、架构哲学 |
| [thinker](./plugins/thinker) | Skill | 思维工具集：deepen需求深度重构、grill-me前提拷问，适合放在brainstorming后使用 |
| [rtk](./plugins/rtk) | Hook | CLI输出过滤工具，减少LLM token消耗（节省60-90%） |
| [statusline](./plugins/statusline) | Command + Script | 双宿主状态行（CodeBuddy Code / Claude Code）：上下文进度、Git、Token、请求数、Credits、Effort |
| [docs](./plugins/docs) | Skill | 写作辅助Skill：基于283万字语料统计的去AI味改写，白名单式规则只改命中文字 |
| [agents](./plugins/agents) | Agent | 双宿主开发agent集（CodeBuddy Code / Claude Code）：worker实施已确认计划的代码修改，tester负责Go/Python测试 |

## 目录结构

```
.
├── .agents/
│   └── plugins/
│       └── marketplace.json    # Codex 插件市场目录文件
├── .claude-plugin/
│   └── marketplace.json    # Claude Code 插件市场目录文件
├── .codebuddy-plugin/
│   └── marketplace.json    # CodeBuddy 插件市场目录文件
└── plugins/
    ├── codegraph/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   ├── .mcp.json         # MCP 服务器配置
    │   └── skills/
    │       └── codegraph/
    │           └── SKILL.md  # codegraph 使用指导
    ├── golang-dev/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   ├── .mcp.json         # gopls MCP 服务器配置
    │   └── skills/
    │       ├── gopls/
    │       │   └── SKILL.md  # gopls 语义分析工具使用指导
    │       ├── mcp-orch/
    │       │   └── SKILL.md  # MCP 编排工具
    │       └── rob-pike/
    │           ├── SKILL.md      # Go Proverbs 全阶段指导
    │           └── proverbs/     # 19 条 proverb 详细规则
    ├── coder/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   └── skills/
    │       ├── karpathy/
    │       │   └── SKILL.md  # Karpathy 编码指南
    │       └── linus-torvalds/
    │           └── SKILL.md  # Linus 编程哲学
    ├── thinker/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   └── skills/
    │       ├── deepen/
    │       │   └── SKILL.md  # 需求深度重构
    │       └── grill-me/
    │           └── SKILL.md  # 前提拷问
    ├── rtk/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   ├── hooks/
    │   │   └── hooks.json    # PreToolUse hook 配置
    │   └── README.md
    ├── statusline/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # Claude Code 插件清单
    │   ├── .codebuddy-plugin/
    │   │   └── plugin.json   # CodeBuddy 插件清单
    │   ├── commands/          # setup/config
    │   └── scripts/           # 入口、解析、渲染、setup 与测试
    │       ├── statusline.py  # 入口（薄编排）
    │       ├── parsing.py     # 双宿主 transcript 解析
    │       ├── render.py      # 三行渲染 + 布局配置
    │       └── tests/         # 297 个用例
    ├── docs/
    │   ├── .claude-plugin/
    │   │   └── plugin.json      # 插件清单
    │   ├── .codex-plugin/
    │   │   └── plugin.json      # Codex 插件清单
    │   ├── .codebuddy-plugin/
    │   │   └── plugin.json      # CodeBuddy 插件清单
    │   └── skills/
    │       └── less-ai-tone/
    │           ├── SKILL.md     # 去AI味规则集
    │           └── scripts/     # 语料测量脚本
    ├── agents/
    │   ├── .claude-plugin/
    │   │   └── plugin.json   # 插件清单
    │   ├── .codebuddy-plugin/
    │   │   └── plugin.json   # CodeBuddy 插件清单
    │   └── agents/
    │       ├── worker.md     # 代码实施 agent
    │       └── tester.md     # 测试 agent
```

## 添加新插件

以Claude Code插件为例，Codex / CodeBuddy插件流程类似
在 `plugins/` 目录下新建插件目录，包含：
- `.claude-plugin/plugin.json` — Claude Code插件清单（name, description, version等）
- `.codex-plugin/plugin.json` — Codex插件清单（如支持Codex）
- `.codebuddy-plugin/plugin.json` — CodeBuddy插件清单（如支持CodeBuddy）
- `.mcp.json` — MCP服务器配置（如适用）
- `skills/` — Skill文件（如适用）
- `hooks/` — Hook配置（如适用）

然后在 `.claude-plugin/marketplace.json` 的 `plugins` 数组中添加新条目；Codex和CodeBuddy分别同步到 `.agents/plugins/marketplace.json` 和 `.codebuddy-plugin/marketplace.json`。

## 参考文档

[Claude Code插件](https://code.claude.com/docs/zh-CN/plugins)

[Claude Code插件参考](https://code.claude.com/docs/zh-CN/plugins-reference)

[codex插件](https://developers.openai.com/plugins/build/plugins)

[CodeBuddy插件](https://www.codebuddy.cn/docs/cli/plugins)

[CodeBuddy插件市场](https://www.codebuddy.cn/docs/cli/plugin-marketplaces)

## 许可证

MIT
