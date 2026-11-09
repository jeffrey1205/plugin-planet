# cbc dispatch skill — 设计文档

日期：2026-11-08（2026-11-09 增补 cwd 警示与静默默认调用形态） · 状态：已批准并实现（测试 26 个、全仓 361 个通过） · 调研依据：`codebuddy-integration.md`（2026-11-07）+ 本文"实测补充"

## 目标

一个通用的后台任务派发 skill：把任意 prompt 交给 CodeBuddy CLI（cbc）执行，
调用方不阻塞、只取最终结果、可随时查任务状态。review 是第一个用法：
规则与 diff 由调用方拼进 prompt，skill 不内置任何规则。

## 非目标

- ACP（stdio JSON-RPC）——后续版本再议
- 思考过程、中途输出的回传（不回传；完整消息数组仅本地存档）
- 模型名有效性校验、默认模型选择——开发者自己保证
- 专门的 rules 注入通道（`--append-system-prompt` / `--rules-file`）——v1 砍掉
- 工具白名单（`--tools`）、进度流、跨 agent 缓存共享

## 实测补充（2026-11-08，本机实跑）

1. `--output-format json` 输出为完整消息数组：
   `[message(user), file-history-snapshot, reasoning, message(assistant), result]`。
   最终结果在最后 `type:"result"` 条目的 `.result`（含 `is_error`、`subtype`、
   `duration_ms`、`num_turns`、`usage`）。思考在 `type:"reasoning"` 条目。
2. 原生 `--bg`：约 5 秒返回 shortId；状态/结果在 `~/.codebuddy/jobs/<shortId>/state.json`
   （`state: working→done`，`output.result` 为纯结果文本）。
3. **shortId 碰撞**：shortId = UUIDv7 前 8 hex（时间戳高位），65.5 秒窗口内派发的
   任务共用同一 jobs 目录，`state.json` 被覆盖（实测两任务相撞，前者状态丢失）
   → 原生 `--bg` 不能作为并行任务的状态存储。
4. API 错误（400 非法模型）在 `--bg` 下仍标 `state: done`，错误文本进 `output.result`
   → 失败判定不能只看 cbc 的 state。
5. cbc 二进制不在 PATH（位于 Electron 应用安装目录，随安装方式变化）。
6. 认证靠 `CODEBUDDY_AUTH_TOKEN` 或桌面端登录态（token 会过期，见调研 §2）。

## 决定

| 议题 | 决定 | 理由 |
|---|---|---|
| 后台机制 | C2：包装器自管后台——`setsid` 起同步 `-p --output-format json` | 规避 shortId 碰撞；只依赖已实测的 `-p` json 输出；不依赖 cbc 内部 `jobs/` 布局（升级风险） |
| 任务目录 | `${CBC_TASK_DIR:-${TMPDIR:-/tmp}/cbc-tasks-$UID}/`，0700 | 用户倾向 /tmp；重启即清可接受——结果即时消费，完整 transcript 永久在 `~/.codebuddy/projects/`；要长期留用 `CBC_TASK_DIR` 指走 |
| skill 名/位置 | `skills/dispatch/`，调用形式 `cbc:dispatch` | 已确认 |
| 调用形式 | `cbc:dispatch --model <id> [--name <n>] [--timeout <s>] [--permission-mode <m>] <comment>` | skill 层透传给 `cbc-task dispatch`，语义一一对应 |
| prompt | 位置参数直接传入（comment），调用方自行拼规则+diff | v1 砍 rules 通道 |
| 超长 prompt | comment 为单独的 `-` 时从 stdin 读，实测 cbc `-p` 支持 stdin 管道 | Linux argv 单参数上限 128KB，150KB 实测 `Argument list too long`（原"ARG_MAX 充足"假设错误） |
| model | `--model` 纯透传，不校验、不提供默认 | 开发者保证 |
| 权限 | `--permission-mode` 可选，默认 `dontAsk` | 后台无 TTY，交互权限询问会挂到超时；`dontAsk` 下 Read/Glob 可用、Bash 拒绝（调研 §4.2 实测） |
| 静默默认 | `run` 子命令一条命令（预检→dispatch→轮询→result）为默认；成功/任务失败仅结果文本，环境未就绪 stderr 一行指向 check；dispatch 族降为低层 | 调用方只要结果时，四步可见调用的中间输出全是噪音（2026-11-09 反馈）；二次反馈：失败 hint 块也算过程噪音；env 供给 export 前缀（token 不落盘）。曾回滚 run 系因 run/dispatch 并列冗余，本次 run 成唯一默认，冗余解除 |
| 工作目录 | cbc 继承派发 shell 的 cwd；SKILL.md 显式警示"在目标项目目录里派发" | 2026-11-09 实测：照旧文案在 skill 目录执行，`当前项目功能` 任务读错了仓库 |

## 文件结构

```
plugins/cbc/
  codebuddy-integration.md          # 既有调研（不动）
  dispatch-design.md                # 本文
  skills/dispatch/
    SKILL.md                        # 机制说明、参数、轮询模式、review 用法示例
    scripts/cbc-task                # python3 单文件，无第三方依赖
    tests/test_cbc_task.py          # 黑盒测试（fake cbc），26 个
```

v1 不内置任何规则文件：prompt 完全由调用方构造（规则、diff、任务描述都是
comment 的内容）。用一段时间后有需要再考虑规则集管理。

## cbc-task 命令

### dispatch

```
cbc-task dispatch [--model <id>] [--name <n>] [--timeout <s>] [--permission-mode <m>] <prompt...>
cbc-task dispatch [...] -        # comment 为单独的 "-"：prompt 从 stdin 读
```

- `--model`：透传给 cbc；不传则用 cbc 自身默认
- `--name`：任务 id；缺省自动生成 `<词>-<ts>-<rand>`；与已有任务重名直接报错
- `--timeout`：默认 600s，超时杀进程、标 failed（detail `timeout`）；`0` 不限
- `--permission-mode`：默认 `dontAsk`
- prompt：位置参数；调用方可 `$(cat ...)` 注入文件内容（规则、diff）；
  超过 127KB 走 stdin（`-`）
- 行为：`setsid` 启动 `cbc -p <prompt> --output-format json ...`（继承调用方 cwd），
  stdout/stderr/退出码写入任务目录；**立即**打印 task id

### run

```
cbc-task run [--model <id>] [--name <n>] [--timeout <s>] [--permission-mode <m>] <prompt...>
cbc-task run [...] -        # 同 dispatch：单独 "-" 从 stdin 读
```

默认形态：一条命令完成预检（resolve cbc，失败 stderr 一行指向 `check`、退出 5，不打
hint 块）→ dispatch（不打印 task id）→ 每 2s 轮询至终态 → 打印结果并以对应退出码结束
（成功 0；任务失败打印错误文本、1）。参数与 dispatch 一致（`add_task_args` 共用）；
不做 auth 硬预检，认证失败以任务错误文本回传；不落盘 token、不内置本机路径；
失败不打印 task id（诊断用 `list` 查）。

### check

```
cbc-task check
```

派发前预检，不启动任务：解析 cbc 二进制（复用 `CBC_BIN` → PATH 发现逻辑）
并报告认证环境（`CODEBUDDY_AUTH_TOKEN` 是否设置；未设置时只 warn，因为无法
静态验证 cbc 自身登录态）。输出 `cbc:`/`auth:`/`ready:` 三行，检查不通过时
额外输出 `hint:` 设置提示（纯文本，脚本不内置任何本机路径）。
退出码 0=ready，5=找不到 cbc。SKILL.md 中 `run` 内部已预检（找不到 cbc 直接一行
stderr 退出 5）；`check` 是 `hint:` 块唯一出口，需诊断时单独跑。

### status / result / list / kill

| 命令 | 行为 | 退出码 |
|---|---|---|
| `status <id>` | 输出 `running\|done\|failed` + 一行 detail | 0；id 不存在 4 |
| `result <id>` | done→打印结果文本；failed→打印错误文本 | 0 / 1 / 2（running）/ 4（不存在） |
| `list` | 枚举任务（id、状态、name、创建时间） | 0 |
| `kill <id>` | 杀进程组（按 pid 文件），状态转 failed | 0；4（不存在）；5（未就绪/进程组已不归属） |

dispatch 退出码：0 成功；2 参数错；3 重名；5 找不到 cbc。
run 退出码（一条命令：预检→dispatch→轮询→result）：0 成功；1 任务失败；2 参数错；3 重名；5 未就绪（找不到 cbc，stderr 一行指向 check）。

### 任务目录布局

```
<taskdir>/<id>/
  prompt.log     # 原始 prompt（追溯）
  status         # running → done | failed
  pid            # cbc 进程 pid
  exit.code      # 进程退出码（结束后写）
  full.json      # 完整消息数组（存档，含思考；不回传调用方）
  result.json    # 解析后 {result, is_error, subtype, duration_ms, num_turns, model, usage}
  stderr.log
```

### 状态与失败判定

- `running`：status=running 且 pid 存活；**pid 已死但 status=running → 报 failed**
  （陈旧检测，防包装器自身被杀留下假 running）
- `failed`：退出码非零 ∨ full.json 解析失败 ∨ `is_error=true` ∨ `subtype≠success`
- API 错误文本（认证失败、400 模型不存在）出现在 result 文本中；SKILL.md 记录
  已知错误样例与处置（400 会回吐账号可用模型清单，可据此重发）

## 通用性约束（必须遵守）

- **零绝对路径**：SKILL.md 与 `cbc-task` 脚本中不出现任何绝对目录路径（含 `~` 展开）。
  二进制发现 `CBC_BIN` → PATH（`codebuddy`、`cbc`）→ 报错提示设置 `CBC_BIN`；
  任务目录由 `CBC_TASK_DIR`/`TMPDIR` 推导；唯一字面量回退是标准目录 `/tmp`
  （`TMPDIR` 缺省时）。不出现 `/opt`、`/home/<user>`、`~/.codebuddy` 等
- **SKILL.md 中性措辞**：只说"用你的 shell 工具执行"，不引用 omp 专属工具或异步能力；
  任何能读 skill 文件并跑 shell 的 harness 可用
- **不写入 token/凭证**：认证靠环境（`CODEBUDDY_AUTH_TOKEN` 或已登录态），
  认证失败作为普通失败回传文本

## 实现时验证结果（2026-11-08，全部实测）

1. 同步 `-p` 遇 API 错误（400 非法模型）：**退出码 0、stdout 为空、
   错误文本在 stderr** → `finish()` 将 stderr 文本（前 300 字符）透出到
   status detail 与 `result` 输出；分类为 failed
2. 无 TTY 后台 `--permission-mode dontAsk`：**不挂起**；Bash 请求被拒，
   拒绝说明作为 result 文本正常回传（done）
3. `--model` 缺省：使用 cbc 账号默认模型（实测回执 `glm-5.3-flash`）
4. argv 传递：**单参数上限 128KB**（`MAX_ARG_STRLEN`），150KB 报
   `Argument list too long` → 新增 stdin 模式（`-` 单独作 comment），
   150KB 经 stdin + 真实 cbc 实测通过

## 验收

- [x] `dispatch` 秒回 task id；`status` 轮询见 running→done；`result` 只含最终结果文本
- [x] 同一分钟内并行 3 个任务互不干扰（10:58:33/34 派发 3 个，全部正确收敛）
- [x] 非法模型 → failed，detail 含 400 文本 + 账号可用模型清单
- [x] 默认调用形态（`run`）只输出最终结果：成功 stdout 仅结果文本 rc=0；环境未就绪
      stdout 为空、stderr 一行无 hint 块、rc=5；任务失败 stdout 仅错误文本、rc=1
      （2026-11-09 真实 cbc 实测 + 黑盒测试）
- [x] 换一台机器：设 `CBC_BIN`/`CODEBUDDY_AUTH_TOKEN` 即可用，无其他本机依赖
     （全部冒烟仅经这两个环境变量 + PATH 完成）
