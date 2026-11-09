---
name: dispatch
description: 把任务派发给 CodeBuddy CLI（cbc）后台执行：审查 diff、让 cbc 独立完成一段单发任务。一次调用返回最终结果（阻塞至任务结束）；只回最终结果，不回传思考和中途输出。需要 cbc 二进制与可用认证。
disable-model-invocation: true
---

# cbc 后台任务派发（cbc:dispatch）

把任意 prompt 交给 cbc 非交互执行。用 `run` 一条命令拿到最终结果（stdout 仅结果文本，阻塞至任务结束）。

**重要**: `scripts/` 下脚本的相对路径按 skill 目录解析 !!!

## 调用形态（唯一，照抄）

```bash
scripts/cbc-task run [--model <id>] [--name <n>] [--timeout <s>] [--permission-mode <m>] <comment...>
```

示例：

```bash
scripts/cbc-task run --model hy3 <comment...>
```

- `comment`：任务正文，可多个词（空格拼接）；以 `-` 开头的 comment 用 `--` 分隔；审查类规则（如有）由调用方拼进 comment
- **超长 prompt 走 stdin**（argv 近 127KB 会报 `Argument list too long`）：把 `-` 作为唯一 comment，内容从 stdin 读：
  `python3 big.py | scripts/cbc-task run --name x -`（`-` 单独出现才是 stdin 模式）
- `--model`：透传给 cbc，不校验；缺省用 cbc 账号默认模型
- `--name`：任务 id，缺省自动生成（`list` 可查）
- `--timeout`：秒，默认 600，`0` 不限
- `--permission-mode`：默认 `dontAsk`（后台无交互：Read/Glob 可用、Bash 拒绝）；需要执行命令时显式传 `bypassPermissions`

**认证自动处理，无需任何export**：run 自动按优先级取 token——环境变量 `CODEBUDDY_AUTH_TOKEN` 已设则直接用；否则调用同目录 `wb-auth-token` 从本机 WorkBuddy 登录态提取并注入任务进程（只读登录态，token 不落盘）。token 有效期约 30 天。

**输出契约**（stdout 仅结果文本）：

- 成功 → stdout 结果文本，退出 0
- 任务失败 → stdout 错误文本（`result` 缺失时为 detail），退出 1；认证失败的错误文本自带处置提示
- 环境未就绪（找不到 cbc）→ stderr 错误 + `hint:` 设置提示块，退出 5
- 参数错退出 2、`--name` 重名退出 3

任务 id、轮询与预检在脚本内部完成，不出现在 stdout/stderr。轮询期间 shell 中断不影响后台任务，任务照常存档（`list` 找 id、`result <id>` 收结果）。无需任何预检或诊断命令。

## 工作目录（cwd）

cbc 继承执行 `cbc-task` 时所在 shell 的 cwd，skill 不做任何 chdir：任务正文里的「当前项目 / 本仓库」= 你执行命令时所在的目录。**在目标项目目录里派发**；切到 skill 目录执行会让 prompt 读错仓库。

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
| `Authentication required...` | token 缺失/过期（错误文本自带处置行） | 重新登录 WorkBuddy 后重跑（run 自动重新提取）；或显式设置 `CODEBUDDY_AUTH_TOKEN` |
| failed + `timeout` | 超过 `--timeout` 被杀 | 加大 timeout 或拆小任务 |
| failed + `stale` | 进程异常消失（无退出码） | 重新 run |

## 注意事项

- 任务目录 `${CBC_TASK_DIR:-${TMPDIR:-/tmp}/cbc-tasks-$UID}/`，重启即清；要留档给 `CBC_TASK_DIR` 指持久位置。目录内 `full.json`/`result.json` 为任务存档
- `status`/`list` 读取即最新状态（含陈旧检测）
