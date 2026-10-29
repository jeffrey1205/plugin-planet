# AGENTS.md

供AI开发助手阅读。改动前先看「不变量」一节，那里每一条都对应真实踩过的坑。

## 架构

```
stdin JSON ──▶ statusline.py (薄编排)
                 │ hostinfo.detect → stats.configure(host)
                 │ parsing.parse_transcript_incremental
                 │ stats.update_rate_snapshot
                 ▼
              render.build_statusline ──▶ stdout（三行）
```

| 文件 | 职责 |
|------|------|
| `statusline.py` | 入口：读stdin、判定宿主、解析、渲染、打印；全局异常兜底 |
| `hostinfo.py` | 宿主判定、config/settings/data/cache路径、settings.json读写、命令解析 |
| `parsing.py` | 双宿主transcript增量解析（`extract_usage` / `iter_calls` / `iter_results` / `add_line_to_stats`） |
| `stats.py` | stats schema、临时缓存（`<tmp>/codebuddy/statusline-<host>-<uid>/cache/`，含state）、速率快照、7天清理、每日git自更新 |
| `render.py` | 三行渲染、块渲染器 `RENDERERS`（含 `recent` 块）、布局解析、工具/最近调用格式化 |
| `formatting.py` | 颜色、token/时长格式化、进度条、宽度来源、ANSI/CJK安全截断 |
| `gitinfo.py` | git分支/脏标记/ahead-behind |
| `config.py` | `/statusline:config` 的后端（hide/show/move/enable/disable/reset/list） |
| `setup-statusline.py` | 写入宿主settings.json的statusLine |
| `tests/` | 单测 + fixtures（双宿主transcript与stdin） |

## 不变量（改代码必读）

1. **解析按行形状分支，不按宿主开关**：`providerData` ⇒ CodeBuddy，`type == 'assistant'` ⇒ Claude。宿主只影响路径与setup。
2. **`input` 含cache**：CodeBuddy的 `usage.inputTokens` 已含缓存；Claude的 `input_tokens` 不含，必须加 `cache_creation_input_tokens + cache_read_input_tokens`。`total_input` 不能再次加cache。
3. **金额不显示**：CodeBuddy的 `cost.total_cost_usd` 恒为0，credit没有官方汇率；Claude的三方模型费用无意义。不要重新引入 `Cost` / `format_cost` / 任何货币符号。
4. **去重**：Claude同一 `message.id` 可能出现在多行 ⇒ `state.seen_msg_ids`（16）只让usage计一次；`state.tool_ids`（128）保证同一 `tool_use.id` 只计一次工具调用；`state.agent_ids`（64）用于按id关闭Agent。三个集合随缓存持久化。
5. **`isSidechain` 只在主transcript跳过**：子Agent文件整份都是sidechain，`is_main=False` 时照常计数，否则会漏。子Agent token以本实现（主 + `subagents/*.jsonl`）为准。
6. **Compact只认一种标记**：Claude用 `system/compact_boundary`（忽略 `isCompactSummary`，那是同一事件的另一条消息）；CodeBuddy用 `message + providerData.isCompactInternal && isSummary`。
7. **缓存目录在临时目录的codebuddy子目录**：`<tmp>/codebuddy/statusline-<host>-<uid>/cache/`；布局配置是持久数据，在 `<config>/plugins/data/statusline/config.json`。缓存丢失只允许导致一次全量重解析。
8. **`CACHE_VERSION` 必须随解析语义升级**：改usage提取、去重、计数口径都要 +1，否则旧缓存会以新语义读出错误数字。当前为9。
9. **宽度顺序**：stdin `terminal_width` → `COLUMNS`（Claude官方要求）→ `/dev/tty` → Windows Console → 0（0表示不截断）。不要把 `COLUMNS` 移到 `/dev/tty` 之后。
10. **三行按类型分组**：LINE1_BLOCKS（环境+上下文+Time+Credits）→ 第一行，LINE2_BLOCKS（requests/tokens/recent/speed）→ 第二行，其余（Tools + 最近调用）→ 第三行。line1_order只控制块顺序与显隐，不控制落在哪一行；新增块必须加进其中一个集合，否则不会渲染。`recent` 兼任块id与行开关：关闭时从顺序中移除该块，且第三行最近调用不渲染。
11. **第三行宽度对齐第二行**：_recent_calls_layout() 的 `max_total` 传入第二行可见宽度，第三行基本与第二行同宽、不随终端宽度拉伸（第二行比工具段还窄时保底两条调用）。相邻重复调用先经 _merge_repeat_calls合并为 `×N`（同名同summary才合并，拷贝副本不改缓存），再按预算均分每条长度；不要在format_recent_calls里用固定60列，否则整行会被行级截断。
12. **不要重复展示同一信息**：context_bar只显示百分比与上限（已用量在tokens），Cache只显示百分比（Token数是In的子集），第二行的Recent块不再重复Credits。
13. **多行命令必须压平**：工具摘要里的换行/制表符会注入额外状态行，format_recent_calls先join(split()) 压成单行。
14. **截断只能用truncate_to_width**：len() 会切坏CJK与ANSI；不要用连续空格做对齐（宿主会折叠）。
15. **null安全**：`model` / `cost` / `context_window` / `current_usage` 都可能是null；统一 `or {}`。
16. **Python 3.6兼容**：不用walrus、dataclasses、`capture_output`、`datetime.fromisoformat`、`str.isascii()`。
17. **Windows**：stdout需 `reconfigure(encoding='utf-8')`；所有文件I/O显式 `encoding='utf-8'`（settings用 `utf-8-sig`）；命令用 `sys.executable` 并双引号包裹。

## 数据来源

- CodeBuddy：`providerData.usage`（CamelCase，`inputTokensDetails[].cached_tokens`、`outputTokensDetails[].reasoning_tokens`）与 `providerData.rawUsage`（`prompt_cache_hit_tokens`、`cache_creation_input_tokens`、`credit`）。`rawUsage` 没有 `cost`。
- Claude：`assistant.message.usage`（snake_case）与 `content[].tool_use` / `user.message.content[].tool_result`。
- 子Agent：`<transcript 去掉 .jsonl>/subagents/*.jsonl`。

## 测试

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
```

`tests/` 不需要 `__init__.py`；每个测试文件自行把 `scripts/` 加进 `sys.path`。fixtures里的两份transcript与stdin是断言「宿主方言差异」的唯一依据，改解析逻辑必须同步扩展它们。

## 性能

单次调用主要是Python启动 + 一次 `git status` fork；transcript走增量（offset缓存），稳态只读新增行。缓存写入是「临时文件 + `os.replace`」原子替换。不要在渲染路径加网络请求或同步等待。
