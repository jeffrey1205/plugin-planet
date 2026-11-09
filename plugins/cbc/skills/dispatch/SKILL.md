---
name: dispatch
description: 把任务派发给 CodeBuddy CLI（cbc）后台执行且不阻塞调用方：审查 diff、让 cbc 独立完成一段单发任务。立即返回任务 id，之后查状态、取最终结果；只回最终结果，不回传思考和中途输出。需要 cbc 二进制与可用认证。
disable-model-invocation: true
---

# cbc 后台任务派发（cbc:dispatch）

把任意 prompt 交给 cbc 非交互执行。`dispatch` 立即返回任务 id；思考过程与
中途输出不回传，完整消息数组在任务目录存档（`full.json`）。

## 前置条件

- cbc 二进制：环境变量 `CBC_BIN`，或 PATH 中的 `codebuddy` / `cbc`
  （都没有 → 脚本报错并提示设置 `CBC_BIN`）
- 认证：环境已带可用的 `CODEBUDDY_AUTH_TOKEN`（或 cbc 自身已登录）；
  认证失败会作为任务结果文本回传
- 本 skill 目录下的 `scripts/cbc-task`（python3 标准库，无第三方依赖）

## 首次配置

缺 `CBC_BIN` 或 `CODEBUDDY_AUTH_TOKEN` 时按本节补齐；两者都只需设置一次
（写入 shell rc 或每次派发前 export）。

### 找 cbc 二进制

```bash
command -v codebuddy || command -v cbc     # PATH 里有就直接用
# 没有 → WorkBuddy 自带 CLI（本机实测路径）：
export CBC_BIN=/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin/codebuddy
```

### 取 CODEBUDDY_AUTH_TOKEN

三种来源，任取其一（按优先级）：

1. **环境已带**（CI secret、已配置的 shell rc）→ 直接用。
2. **cbc 自身登录**：交互跑一次 `cbc`，在 TUI 里 `/login`；登录态落盘后
   后续任务无需该变量。
3. **解密本机 WorkBuddy 登录态**（WorkBuddy 已登录、cbc 未登录时）：
   登录态 `~/.local/share/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`
   的 `auth.accessToken` 在 5.6.2+ 是 AES-256-GCM 信封，需用签到助手脚本的
   `load_credentials()` 解密（只读，不打印、不外传 token）：

   ```bash
   export CODEBUDDY_AUTH_TOKEN="$(python3 -c "
   from importlib.machinery import SourceFileLoader
   m = SourceFileLoader('wbauth', '$HOME/.workbuddy/file-history/<签到脚本目录>/ef75a2c37b9af340@v1').load_module()
   t, d = m.load_credentials('$HOME/.local/share/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info')
   print(t, end='')")"
   ```

   注意：
   - 路径用 `$HOME` 或 `os.path.expanduser('~...')`；**引号内的裸 `~` 不会被
     shell 展开**（`python3 -c "..."` 内的 `~` 同理），必须用 `$HOME`。
   - 签到脚本的 `find_login_state()` 缺 Linux 的
     `~/.local/share/CodeBuddyExtension` 候选路径，须显式传文件路径。
   - token 有效期 30 天（登录态 `expiresAt`），过期后重新登录 WorkBuddy 再取；
     解密依赖脚本内的密钥发现逻辑，客户端升级可能使其失效。

## 调用形式

```
dispatch --model <id> [--name <n>] [--timeout <s>] [--permission-mode <m>] <comment...>
```

用你的 shell 工具执行（skill 目录下）：

```bash
scripts/cbc-task dispatch --model hy3 --timeout 600 <comment...>
```

- `comment`：任务正文，可多个词（自动以空格拼接）；也可 `$(cat ...)` 注入
  文件内容（规则、diff）。以 `-` 开头的 comment 用 `--` 分隔
- **超长 prompt 走 stdin**：Linux 单个 argv 参数上限 127KB，超过会在启动前
  就报 `Argument list too long`。此时把 `-` 作为唯一 comment，内容从 stdin 读：
  `python3 big.py | scripts/cbc-task dispatch --name x -`（`-` 单独出现才是
  stdin 模式，与其它词同现时按字面处理）
- `--model`：透传给 cbc，不校验；错误模型的 400 错误会连同可用清单回传
- `--name`：任务 id，缺省自动生成；与已有任务重名直接报错
- `--timeout`：秒，默认 600，到点杀掉任务；`0` 表示不限
- `--permission-mode`：默认 `dontAsk`（后台无交互：Read/Glob 可用、Bash 拒绝）；
  需要执行命令时显式传 `bypassPermissions`

## 子命令

| 命令 | 行为 | 退出码 |
|---|---|---|
| `dispatch ...` | 立即打印任务 id | 0；2 参数错；3 重名；5 找不到 cbc |
| `status <id>` | 第 1 行 `running/done/failed`，第 2 行 detail | 0；4 任务不存在 |
| `result <id>` | 只打印最终结果文本；failed 时打印错误文本 | 0=done；1=failed；2=仍在运行；4=不存在 |
| `list` | 每行：id、状态、创建时间、detail；无任务则无输出 | 0 |
| `kill <id>` | 杀掉任务进程组，状态随后转 failed | 0；4=不存在；5=未就绪/进程组已不归属 |

## 调用方模式（不阻塞）

```bash
scripts/cbc-task dispatch --model hy3 --name pr-123 "审查这个 diff：$(git diff HEAD)"
# 立即拿到 pr-123，继续干别的事
scripts/cbc-task status pr-123    # running →（结束后）done / failed
scripts/cbc-task result pr-123     # 只有结果文本，退出码 0
```

不必空转等待：先去做别的，隔一段时间再 `status`；要连续拿结果就循环
`status` 直到第 1 行不是 `running`（间隔数秒）。

## review 用法示例

```bash
scripts/cbc-task dispatch --model hy3 --name pr-review \
  "审查以下 diff，只列问题，按严重程度排序：$(git diff main...HEAD)"
```

规则（如果有）由调用方拼进 comment，skill 不管理规则。

## 已知错误与处置

| 结果 / detail | 含义 | 处置 |
|---|---|---|
| `400 model [...] service info not found` | 模型名非法，附账号可用清单 | 换名重发 |
| `Authentication required...` | 认证缺失或 token 过期 | 按「首次配置」补/刷新 `CODEBUDDY_AUTH_TOKEN` |
| failed + `timeout` | 超过 `--timeout` 被杀 | 加大 timeout 或拆小任务 |
| failed + `stale` | 进程异常消失（无退出码） | 重新 dispatch |

## 注意事项

- 任务目录 `${CBC_TASK_DIR:-${TMPDIR:-/tmp}/cbc-tasks-$UID}/`，重启即清；
  要留档给 `CBC_TASK_DIR` 指持久位置。任务目录内 `full.json` 为完整消息
  数组（含思考，仅存档），`result.json` 为解析后的结构化结果
  （`result`/`is_error`/`model`/`duration_ms`/`num_turns`/`usage`）
- 不传 `--model` 时用 cbc 自身默认模型（实测为账号默认，非静默报错）
- `status` 读取时即完成状态收敛（含陈旧检测），`list` 同理
- cbc 的 API 错误（400、认证失败）写在 stderr 且退出码为 0；skill 已自动
  把 stderr 文本透出到 `status` detail 和 `result` 输出
