# Statusline

CodeBuddy Code / Claude Code通用的三行状态行：第一行环境与上下文（含会话时长与Credits），第二行累计用量与最近一次交互，第三行工具调用与最近调用。

- 以CodeBuddy的状态行实现为基座，同一份代码兼容Claude Code的stdin与transcript格式。
- 增量解析transcript（主 + 子Agent），缓存放在系统临时目录，单次渲染约几十毫秒。
- 只显示Credits（CodeBuddy的计费单位），**不显示任何货币金额**，原因见下文。

## 环境要求

- Python 3.6+
- CodeBuddy Code或Claude Code（两者均可，同一套代码）
- macOS / Linux / Git Bash；Windows通过PowerShell安装插件，但 `statusLine` 命令会由 `sys.executable` 直接调用Python，路径带引号，空格安全。

## 安装

```
/plugin marketplace add jeffrey1205/claude-plugins
/plugin install statusline@cc-hub
/statusline:setup
```

`/statusline:setup` 会按宿主把 `statusLine` 写入 `~/.codebuddy/settings.json` 或 `~/.claude/settings.json`，指向当前插件版本的 `scripts/statusline.py`，写入后**重启会话**生效。

- 幂等：目标一致时不修改；`--check` 可查看是否stale。
- **插件升级后要重跑 `/statusline:setup`**：插件缓存的目录带版本号（`.../statusline/2.0.0/scripts/`），升级后路径变化，旧配置会失效。
- settings.json里已有其他人的 `statusLine` 时脚本会拒绝覆盖，需要 `--force`。

## 效果

```
claude-plugins on  main* +26/-4 | Step-5-Preview | █░░░░░░░░░ 5% 1.0M | Time:25m25s | Credits:67.20
Req:60 | In:2.1M Out:17.1K Cache:96% | Recent: In:51.5K Out:668 Cache:96% Speed:24.3t/s | Avg:11.6t/s
Tools: ✓ REPL×56 | ✓ TaskCreate×4 | ✓ TaskUpdate×2 | REPL await Task…
```

三行按**类型**分组：第一行「环境 + 上下文 + 会话信息」（目录/git/增删行、模型、effort、进度条、压缩、Time、Credits），第二行「累计用量 + 最近一次交互」（Req、In/Out/Cache%、Recent、Avg），第三行「活动」（Tools + 最近调用）。块仍可配置顺序与显隐：

| 块id | 内容 |
|-------|------|
| `cwd_git` | 目录名 + git分支/脏标记/ahead-behind，worktree会还原成主项目名；代码增删行数 `+N/-M` 拼在其后（空格连接，无 `|`） |
| `model` | 模型显示名 |
| `effort` | `effort.level`（仅Claude Code提供时显示） |
| `context_bar` | 上下文进度条 + 百分比 + 窗口上限（如 `██░░ 27% 1.0M`；已用量在 `tokens` 块里） |
| `compact_periodic` | `Compact×N`（上下文压缩次数）、`Periodic×M`（阶段性摘要，仅CodeBuddy） |
| `time` | 会话耗时（`Time:`，第一行） |
| `credits` | `Credits:` 累计计费credits（为0不显示；第一行最后） |
| `requests` | `Req:` API请求次数 |
| `tokens` | `In` / `Out` / `Cache:命中率`（Token数已是In的子集，不重复显示；不显示Think） |
| `recent` | `Recent:` 最近一次交互的In/Out/Cache命中率与 `Speed:` 最近速率（速率不可测时不显示；第二行） |
| `speed` | 会话平均输出吞吐 `Avg:`（累计Out ÷ 累计API时长；第二行末） |

第三行 `Tools:` 按固定顺序统计工具调用次数，`Agent` 区分运行中（`↑`）与已完成（`✓`）；随后是最近3次工具调用摘要（CJK/ANSI安全截断，多行命令压成一行）。
相邻重复的调用（同名同摘要）会合并成一条并标注 `×N`，不再占多份宽度；整行宽度与第二行基本一致，不随终端宽度拉伸。
宽度不够时先等比缩短每条调用摘要，仍放不下才舍弃最旧的调用，保证整行不折行、不被截断成半句。

## 双宿主字段支持

| 能力 | CodeBuddy Code | Claude Code |
|------|----------------|-------------|
| stdin的model / workspace / context_window / cost时长 | 有 | 有 |
| `cost.total_cost_usd` | 恒为0（CLI写死），不使用 | 真实美元，本插件不展示 |
| `rawUsage.credit` | 有（Credits来源） | 无 |
| `effort.level` | 无 | 有（可选块） |
| transcript格式 | `function_call` + `providerData.usage/rawUsage` | `assistant.message.usage` + `tool_use/tool_result` |
| 压缩事件 | `providerData.isCompactInternal && isSummary` | `system/compact_boundary` |
| 阶段摘要Periodic | 有 | 无（不渲染） |
| 终端宽度 | `/dev/tty` | `COLUMNS` 环境变量（宿主设置） |
| 子Agent token | `subagents/*.jsonl` 增量合并 | 同左；主transcript的 `isSidechain` 行跳过，避免双计 |

解析按**行形状**分支，不按宿主开关；宿主只决定缓存目录与setup目标文件。因此即使宿主判断错了，也不会丢token。

## 关于Credits（为什么不显示金额）

- CodeBuddy的计费单位是 **credits**：服务端在每次响应的usage里下发 `rawUsage.credit`，CLI上报时是 `cost:{amount: credit, currency:""}`，**没有** credit到货币的官方汇率。
- 早期版本用「credits × 0.01当美元，再 × 7当人民币」显示 `Cost`，两个系数都是拍脑袋，数字不可信，已移除。
- Claude Code的 `total_cost_usd` 只对官方计价的模型有意义，三方模型下没有参考价值，也一并移除。
- 已知边界：插件只累加transcript里的 `rawUsage.credit`，**不含**图像/视频生成与team_member通道记账，因此可能小于WebUI的本轮credits汇总。

## 布局配置

配置文件：`<config>/plugins/data/statusline/config.json`（CodeBuddy为 `~/.codebuddy/...`，Claude为 `~/.claude/...`）。

```json
{
  "layout": {
    "line1_order": ["cwd_git", "model", "effort", "context_bar", "compact_periodic", "time", "credits", "requests", "tokens", "recent", "speed"],
    "line1_hidden": [],
    "tools": true,
    "recent": true
  }
}
```

- `line1_order`：块的顺序（按类型自动分到三行内，见上表）；`line1_hidden`：隐藏指定块（优先级高于顺序）。
- `tools`：第三行 `Tools:` 段开关；`recent`：第二行 `Recent:` 块开关（同时控制第三行最近调用）。
- 新版本新增的块若未出现在配置里，会自动追加到末尾显示；要隐藏必须写进 `line1_hidden`。
- 配置损坏时回退默认布局，不会让状态行变空白；修改后下一次刷新即生效。

用命令调整（推荐）：

```
/statusline:config hide credits time
/statusline:config show credits
/statusline:config move tokens after model
/statusline:config disable tools
/statusline:config reset
/statusline:config list
```

> `cost` 块已移除。旧配置里若还留着 `cost`，会被当作未知块忽略，不会报错。

## 临时文件

- 运行时缓存（transcript偏移、最近速率快照、更新标记）放在系统临时目录的 `codebuddy` 子目录下：`<tmp>/codebuddy/statusline-<host>-<uid>/cache/`，Unix上是 `/tmp/codebuddy/statusline-codebuddy-1000/cache`，Windows上是 `%TEMP%\codebuddy`。目录权限0700，7天自动清理。
- 布局配置是持久数据，留在 `<config>/plugins/data/statusline/config.json`。
- 临时目录丢失只会触发一次全量重解析，不影响结果正确性；从旧路径（`/tmp/statusline-*`）升级后旧目录不自动迁移，可手动删除。

## 从旧安装迁移

1. **旧git-clone版**（`~/.codebuddy/statusline/`）：先跑 `bash ~/.codebuddy/statusline/uninstall.sh`，否则它的 `statusLine` 命令仍会优先生效；再按上面的方式安装插件并执行 `/statusline:setup`。
2. **旧Claude单文件插件（1.0.4）**：升级后重跑 `/statusline:setup`，会把命令从 `.../statusline/1.0.4/scripts/statusline.py` 改到新版本目录。
3. 布局配置路径不变（`plugins/data/statusline/config.json`），块id除 `cost`、`lines` 外保持兼容：`lines` 已折叠进 `cwd_git`（旧配置里的 `lines` 按未知id忽略，不报错）；`recent` 是新块id，旧配置会自动把它追加到顺序末尾，建议执行一次 `/statusline:config reset` 应用新默认顺序。

## 测试

```bash
cd plugins/statusline
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
```

覆盖：双宿主解析、增量与截断、去重（同message id / 同tool id）、isSidechain防双计、宿主判定、setup、宽度与ANSI安全截断。

## License

MIT
