---
name: dispatch
description: 把任务派发给 CodeBuddy CLI（cbc）后台执行：审查 diff、让 cbc 独立完成一段单发任务。一次调用返回最终结果（阻塞至任务结束）；只回最终结果，不回传思考和中途输出。需要 cbc 二进制与可用认证。
disable-model-invocation: true
---

# cbc 后台任务派发（cbc:dispatch）

把任意 prompt 交给 cbc 非交互执行。用 `run` 一条命令拿到最终结果（stdout 仅结果文本，阻塞至任务结束）。

**重要**: `scripts/cbc-task` 的相对路径按 skill 目录解析 !!!

## 环境与派发前检查

`CODEBUDDY_AUTH_TOKEN` 由 shell 环境变量提供，脚本不做自动配置；认证失败会作为任务结果文本回传。cbc 二进制自动解析（`CBC_BIN` → PATH → 默认目录 `/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin`、`~/.local/bin`），通常无需设置。

**`run` 内置预检，无需先跑 `check`**。`export` 必须与 `run` 写在同一条 shell 命令里，或写入 shell 启动文件；换会话/机器后 `export` 不保留。

环境报错或需看 `hint:` 设置提示时再跑诊断命令（不启动任务；不是派发前置步骤）：

```bash
scripts/cbc-task check
```

- 退出 0（`ready: yes`）→ 直接派发。
- 退出 5（`ready: no`）→ 按输出中的 `hint:` 行处理后重试。
- `auth: warn` → 若任务以 `Authentication required` 失败，按下面「取 token」补齐。

### 取 CODEBUDDY_AUTH_TOKEN

三种来源，任取其一（按优先级）：

1. **环境已带**（CI secret、已配置的 shell rc）→ 直接用。
2. **cbc 自身登录**：交互跑一次 `cbc`，在 TUI 里 `/login`；登录态落盘后后续任务无需该变量。
3. **解密本机 WorkBuddy 登录态**（WorkBuddy 已登录、cbc 未登录时）：用签到助手脚本的 `load_credentials()` 解密登录态里的 `auth.accessToken`（只读，不打印、不外传 token）：

   ```bash
   export CODEBUDDY_AUTH_TOKEN="$(python3 -c "
   from importlib.machinery import SourceFileLoader
   m = SourceFileLoader('wbauth', '$HOME/.workbuddy/file-history/<签到脚本目录>/ef75a2c37b9af340@v1').load_module()
   t, d = m.load_credentials('$HOME/.local/share/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info')
   print(t, end='')")"
   ```

注意：
   - 路径中的 `~` 必须写成 `$HOME`（引号内裸 `~` 不展开）。
   - `load_credentials()` 必须显式传上述文件路径，勿传目录。
   - token 有效期约 30 天（登录态 `expiresAt`），过期后重新登录 WorkBuddy 再取。

## 调用形式（默认：只输出最终结果）

```
run [--model <id>] [--name <n>] [--timeout <s>] [--permission-mode <m>] <comment...>
```

用你的 shell 工具执行：

```bash
export CODEBUDDY_AUTH_TOKEN=<token>   # 需要认证时
scripts/cbc-task run --model hy3 --timeout 600 <comment...>
```

输出契约（失败静默，诊断一律走 `check`/`list`）：

- 成功 → stdout 仅结果文本，退出 0
- 任务失败 → stdout 仅错误文本（`result` 缺失时为 detail），退出 1
- 环境未就绪（找不到 cbc）→ stdout 空、stderr 一行错误并指向 `check`，退出 5
- 参数错退出 2、`--name` 重名退出 3

任务 id、轮询与预检在脚本内部完成，不出现在 stdout/stderr；失败需诊断时跑 `check`（`hint:` 块唯一出口）或 `list` 查任务 id。轮询期间 shell 中断不影响后台任务，任务照常存档（`list` 找 id、`result <id>` 收结果）。

- `comment`：任务正文，可多个词（空格拼接）；以 `-` 开头的 comment 用 `--` 分隔；审查类规则（如有）由调用方拼进 comment
- **超长 prompt 走 stdin**（argv 近 127KB 会报 `Argument list too long`）：把 `-` 作为唯一 comment，内容从 stdin 读：
  `python3 big.py | scripts/cbc-task run --name x -`（`-` 单独出现才是 stdin 模式）
- `--model`：透传给 cbc，不校验
- `--name`：任务 id，缺省自动生成（`list` 可查 id）
- `--timeout`：秒，默认 600，`0` 表示不限
- `--permission-mode`：默认 `dontAsk`（后台无交互：Read/Glob 可用、Bash 拒绝）；需要执行命令时显式传 `bypassPermissions`

## 工作目录（cwd）

cbc 继承执行 `cbc-task` 时所在 shell 的 cwd，skill 不做任何 chdir：任务正文里的「当前项目 / 本仓库」= 你执行命令时所在的目录。**在目标项目目录里派发**；切到 skill 目录执行会让 prompt 读错仓库。

## 子命令

| 命令 | 行为 | 退出码 |
|---|---|---|
| `run ...` | 默认形态：直接拿最终结果；输出契约见「调用形式」 | 0/1/2/3/5 |
| `check` | 预检 cbc 二进制与认证环境，失败时输出 `hint:` 设置提示，不启动任务 | 0=ready；5=未就绪 |
| `status <id>` | 第 1 行 `running/done/failed`，第 2 行 detail | 0；4 任务不存在 |
| `result <id>` | 只打印最终结果文本；failed 时打印错误文本 | 0=done；1=failed；2=仍在运行；4=不存在 |
| `list` | 每行：id、状态、创建时间、detail；无任务则无输出 | 0 |
| `kill <id>` | 杀掉任务进程组，状态随后转 failed | 0；4=不存在；5=未就绪/进程组已不归属 |

## 已知错误与处置

| 结果 / detail | 含义 | 处置 |
|---|---|---|
| `400 model [...] service info not found` | 模型名非法，附账号可用清单 | 换名重发 |
| `Authentication required...` | 认证缺失或 token 过期 | 按「取 CODEBUDDY_AUTH_TOKEN」补/刷新 |
| failed + `timeout` | 超过 `--timeout` 被杀 | 加大 timeout 或拆小任务 |
| failed + `stale` | 进程异常消失（无退出码） | 重新 run |

## 注意事项

- 任务目录 `${CBC_TASK_DIR:-${TMPDIR:-/tmp}/cbc-tasks-$UID}/`，重启即清；要留档给 `CBC_TASK_DIR` 指持久位置。目录内 `full.json`/`result.json` 为任务存档
- 不传 `--model` 时用 cbc 账号默认模型
- `status`/`list` 读取即最新状态（含陈旧检测）
