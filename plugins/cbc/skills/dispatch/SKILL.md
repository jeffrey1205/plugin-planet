---
name: dispatch
description: 把任务派发给 CodeBuddy CLI（cbc）后台执行：审查 diff、让 cbc 独立完成一段单发任务。一次调用返回最终结果（阻塞至任务结束）；只回最终结果，不回传思考和中途输出。需要 cbc 二进制与可用认证。
disable-model-invocation: true
---

# cbc 后台任务派发（cbc:dispatch）

把任意 prompt 交给 cbc 非交互执行。用 `run` 一条命令拿到最终结果（stdout 仅结果文本，阻塞至任务结束）。

`scripts/` 下的脚本路径按 skill 目录解析。

## 调用形态

```bash
scripts/cbc-task run [--model <id>] [--effort <level>] [--fallback-model <id>] \
  [--add-dir <dir>]... [--name <n>] [--timeout <s>] [--permission-mode <m>] <comment...>
```

示例：

```bash
scripts/cbc-task run --model hy3 <comment...>
```

- `comment`：任务正文，可多个词（空格拼接）；以 `-` 开头的 comment 用 `--` 分隔；审查类规则（如有）由调用方拼进 comment
- 超长 prompt 走 stdin（argv 近 127KB 会报 `Argument list too long`）：把 `-` 作为唯一 comment，内容从 stdin 读：
  `python3 big.py | scripts/cbc-task run --name x -`（`-` 单独出现才是 stdin 模式）
- `--model`：透传给 cbc，不校验；缺省用 cbc 账号默认模型
- `--name`：任务 id，缺省自动生成（`list` 可查）
- `--timeout`：秒，默认 600，`0` 不限；超时被杀不留结果，审查类任务按 3 倍估时给足
- `--permission-mode`：默认 `dontAsk`（后台无交互：Read/Glob 可用、Bash 拒绝）；需要执行命令时显式传 `bypassPermissions`

### 质量参数（透传 cbc，不校验）

| 参数 | 默认 | 作用 | 建议 |
|---|---|---|---|
| `--effort <level>` | `max` | 推理强度：`minimal`/`low`/`medium`/`high`/`xhigh`/`max` | 缺省即 `max`；机械改动用 `low`/`minimal` 省时省钱 |
| `--fallback-model <id>` | 无 | 主模型过载时自动回落（仅 `--print` 生效，本工具恒满足） | 长任务建议设置 |
| `--add-dir <dir>` | 无 | 追加任务可读目录，可重复 | 需读上游仓库/外部目录时 |

上下文压缩窗口与轮次上限不做透传：前者缺省就是跟随模型窗口，显式传参没有收益；后者是硬停（触顶即失败、不留部分结果），当保险丝用反而容易作废整段工作。真正的时间兜底是 `--timeout`。

**认证**：`run` 自行取 token 并注入任务进程，调用方不需要 export。优先使用环境变量 `CODEBUDDY_AUTH_TOKEN`；未设置时尝试读取本机客户端登录态（只读、不落盘，取不到就跳过）。目标机器上没有该登录态时，在调用方 harness 的环境里设置 `CODEBUDDY_AUTH_TOKEN` 即可，本工具不依赖某个特定宿主。token 有效期约 30 天。

**环境隔离**：任务进程只拿到白名单环境（HOME、PATH、代理与证书、`SSH_AUTH_SOCK`、`CODEBUDDY_AUTH_TOKEN` 等），与调用方 harness 无关。harness 注入的运行时 shim 与宿主路由变量一律不下传——带这些变量启动的 cbc 会静默挂死（无输出、不退出）。需要下传额外变量（如 `JAVA_HOME`）时用 `CBC_ENV_PASS=JAVA_HOME,GOPATH` 显式放行。

**输出契约**（stdout 仅结果文本）：

- 成功 → stdout 结果文本，退出 0
- 任务失败 → stdout 错误文本（`result` 缺失时为 detail），退出 1；认证失败的错误文本自带处置提示
- 环境未就绪（找不到 cbc）→ stderr 错误 + `hint:` 设置提示块，退出 5
- 参数错退出 2、`--name` 重名退出 3

任务 id、轮询与预检在脚本内部完成，不出现在 stdout/stderr。轮询期间 shell 中断不影响后台任务，任务照常存档（`list` 找 id、`result <id>` 收结果）。无需任何预检或诊断命令。

## 工作目录（cwd）

cbc 继承执行 `cbc-task` 时所在 shell 的 cwd，skill 不做任何 chdir：任务正文里的「当前项目 / 本仓库」= 你执行命令时所在的目录。应当在目标项目目录里派发；切到 skill 目录执行会让 prompt 读错仓库。

## 子命令

| 命令 | 行为 | 退出码 |
|---|---|---|
| `run ...` | 唯一派发形态，见「调用形态」；输出契约同上 | 0/1/2/3/5 |
| `result <id>` | 只打印最终结果文本；failed 时打印错误文本 | 0=done；1=failed；2=仍在运行；4=不存在 |
| `list` | 每行：id、状态、创建时间、detail；无任务则无输出 | 0 |
| `kill <id>` | 杀掉任务进程组，状态随后转 failed | 0；4=不存在；5=未就绪/进程组已不归属 |

## 已知错误与处置

| 结果 / detail | 含义 | 处置 |
|---|---|---|
| `400 model [...] service info not found` | 模型名非法，附账号可用清单 | 换名重发 |
| `Authentication required...` | token 缺失/过期 | 设置 `CODEBUDDY_AUTH_TOKEN` 后重跑；本机有桌面客户端时重新登录也可（run 会自动重新提取） |
| failed + `timeout` | 超过 `--timeout` 被杀 | 加大 timeout 或拆小任务 |
| failed + `stale` | 进程异常消失（无退出码） | 重新 run |

## 注意事项

- 任务目录 `${CBC_TASK_DIR:-${TMPDIR:-/tmp}/cbc-tasks-$UID}/`，重启即清；要留档给 `CBC_TASK_DIR` 指持久位置。目录内 `full.json`/`result.json` 为任务存档
- `list`/`result` 读取即最新状态（含陈旧检测）
- cbc 定位顺序：`CBC_BIN` → PATH 中的 `codebuddy`/`cbc` → 常见安装目录（`~/.local/bin`；可用 `CBC_BIN_DIRS` 覆盖）。换机器时把 cbc 放进 PATH 最省事
