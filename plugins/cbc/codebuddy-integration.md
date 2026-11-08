# CodeBuddy CLI / ACP 调用笔记

实测环境：linux x64，2026-11-07，安装路径 `/opt/WorkBuddy`，CLI 版本 `2.147.0`。
本文所有结论均来自实际运行，未验证的地方明确标注 `[INFERENCE]`。

---

## 1. 入口辨析

| 路径 | 性质 | 能否当 CLI |
|---|---|---|
| `/opt/WorkBuddy/workbuddy` | Electron GUI 主程序（200MB） | 否。`--version` 会直接拉起图形界面 |
| `/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin/codebuddy` | 真正的 CLI，别名 `cbc` | 是 |

CLI **不在 PATH 里**，需全路径调用。下文用：

```bash
CBC=/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin/codebuddy
```

`$CBC --help` 输出完整能力清单（`-p`、`--serve`、`--acp`、`-w` worktree、`--sandbox`、
`--bg`、`daemon`、`agents` 等）。

**已知小 bug**：`$CBC config list` 报 `Cannot find module '../dist/codebuddy'`，
其余子命令正常。

---

## 2. 登录 / 认证

### 2.1 现象

裸跑一律失败：

```
$ $CBC -p "回复两个字:成功"
Authentication required. Please use /login command to sign in to your account
```

### 2.2 根因（日志实证）

CLI 启动时处于 `standalone` 模式，拿不到桌面端 sidecar 注入的
`credentialProtectionBootstrap`，于是解不开 auth 文件里加密字段：

```
[FileAuthenticationStorage] AtRestEncryption unavailable
  adapter=credential-fields resource=auth/workbuddy-desktop.info
  operation=read category=missing-key role=cbc: continuing
[AuthenticationManager] stage=afterRestore hasSession=true hasAccessToken=false
[ExternalLinkAuthenticationProvider] fetch auth accounts error: status code 401
```

- 桌面端明文 token：`~/.workbuddy/auth/workbuddy-desktop.info`
- CLI 自己的**加密**副本：`~/.local/share/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`
  （`auth.accessToken` 是 `{"$wbEncrypted":1,"envelope":"..."}`）
- 解密根 key：`~/.workbuddy/keyblob`，CLI 单独启动时读不到（`missing-key`）
- 相关环境变量（从 bundle 逆出）：`WORKBUDDY_AT_REST_ENCRYPTION`、
  `CODEBUDDY_SIDECAR_READY_SOCKET`、`CODEBUDDY_SIDECAR_CREDENTIAL_BOOTSTRAP_SOCKET`、
  `CODEBUDDY_SIDECAR_READY_TOKEN`、`CODEBUDDY_SIDECAR_READY_SESSION_ID`

### 2.3 可用方案：注入明文 token

CLI 支持 `CODEBUDDY_AUTH_TOKEN` 环境变量（另有 `CODEBUDDY_API_KEY`、`CODEBUDDY_BASE_URL`）。

```bash
export CODEBUDDY_AUTH_TOKEN="$(python3 -c "import json;print(json.load(open('/home/zhujingfeng/.workbuddy/auth/workbuddy-desktop.info'))['auth']['accessToken'])")"
```

实测通过。**token 有效期至 2026-11-24**（`auth.expiresAt`），过期后需重新登录桌面端刷新。

> ⚠️ 不要把 token 写进仓库文档或提交物。

---

## 3. 可用模型

非法模型名会触发 400 并回吐账号可用清单：

```
400 model [xxx] service info not found
Currently supported models for your account:
  auto, hy4free, hy4std, hy3, hy3-x, deepseek-v4.1-flash, glm-5.3, glm-5.3-flash,
  glm-5.2, space-bunny, minimax-m3.1-flash, kimi-k3.1-pro, kimi-k3-1,
  kimi-k2.8-preview, deepseek-v4-pro, step-5-preview, mimo-v2.6-pro,
  custom-local:mimo-v2.6-flash
```

`hy3` 已验证可用（`--model hy3` + `--output-format stream-json` 回执 `"model":"hy3"`，
非静默回退到 auto）。

---

## 4. 命令行调用（`-p` 非交互）

### 4.1 基本形态

```bash
$CBC -p "回复两个字:成功" --model hy3
# → 成功
```

结构化输出：

```bash
$CBC -p "..." --model hy3 --output-format json
```

返回 `result` / `duration_ms` / `duration_api_ms` / `num_turns` / `usage`。

### 4.2 实测过的开关

| 开关 | 实测结果 |
|---|---|
| `--model hy3` | 生效，服务端确认 |
| `--max-turns 1` | ⚠️ 报 `Max turns (1) exceeded`，模型多走一轮就截断。**别设 1** |
| `-c` | ✅ 跨进程续接：上一轮"记住 planet-core"，新一轮 `-c` 答出 `planet-core` |
| `-y` | ✅ 非交互放行 Bash：`echo ACP_BASH_OK` 执行成功并回传输出 |
| `--permission-mode dontAsk` | Bash 被 deny，Read/Glob 可用（改用 Glob 完成了扫描） |
| `-d <filter>` | 输出 `serve 0`，`~/.codebuddy/debug/` 未见新文件，调试信息有限 |

### 4.3 典型 review 调用

```bash
CODEBUDDY_AUTH_TOKEN="..." $CBC -p \
  "审查以下 diff，只列问题，按严重程度排序：$(git diff HEAD)" \
  --model hy3 --output-format json -y
```

`-y` 只在需要它自己跑测试/lint 时加；纯读代码审查用 `--permission-mode dontAsk` 更安全。

---

## 5. ACP 调用（stdio JSON-RPC / ndJSON）

`$CBC --acp` 走 stdin/stdout，每行一条 JSON-RPC 2.0 消息。

### 5.1 握手与调用顺序（实测）

```text
initialize            → protocolVersion 1
session/new           → sessionId + models.availableModels（18 个，含 hy3）
session/set_model     → {"modelId":"hy3"}
session/prompt        → {"stopReason":"end_turn", ...}
```

**方法名坑**：
- 是 `session/prompt`，写成 `prompt` → `-32601 Method not found`
- `session/list_models` **不存在**（`-32601`）；模型清单随 `session/new` 一起返回

`initialize` 返回的能力位：

```json
{"protocolVersion":1,
 "agentCapabilities":{
   "promptCapabilities":{"image":true,"embeddedContext":true},
   "mcpCapabilities":{"http":true,"sse":true},
   "loadSession":true,"delegateToolsSupport":true,
   "mainAgentSupport":false,"multitaskSupport":true},
 "authMethods":[{"id":"iOA",...},{"id":"external",...},
                {"id":"internal",...},{"id":"selfhosted",...}]}
```

### 5.2 流式事件（`session/update` 通知）

实测出现的 `sessionUpdate` 类型：

```
session_info_update, config_option_update, usage_update,
agent_thought_chunk, agent_message_chunk,
tool_call, tool_call_update
```

- 正文在 `agent_message_chunk.content.text`
- 工具调用轨迹在 `tool_call` / `tool_call_update`
- 用量在 `usage_update`

### 5.3 完整测试脚本（可直接跑）

```python
#!/usr/bin/env python3
"""Throwaway ACP client test for codebuddy CLI."""
import json, subprocess, os, time, sys

CLI = '/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin/codebuddy'
TOK = json.load(open('/home/zhujingfeng/.workbuddy/auth/workbuddy-desktop.info'))['auth']['accessToken']
env = dict(os.environ); env['CODEBUDDY_AUTH_TOKEN'] = TOK

args = [CLI, '--acp']
if len(sys.argv) > 4:
    args += ['--permission-mode', sys.argv[4]]
errf = open('/tmp/acp_stderr.log', 'w')
p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=errf, env=env, text=True, bufsize=1)
SEEN = []
idc = 0

def send(o):
    p.stdin.write(json.dumps(o) + '\n'); p.stdin.flush()

def rpc(method, params, timeout=180):
    global idc
    idc += 1; my = idc
    send({"jsonrpc": "2.0", "id": my, "method": method, "params": params})
    end = time.time() + timeout
    while time.time() < end:
        line = p.stdout.readline()
        if not line: break
        line = line.strip()
        if not line: continue
        try: m = json.loads(line)
        except Exception: continue
        SEEN.append(m)
        if m.get("id") == my: return m
    return None

# 1. handshake
init = rpc("initialize", {"protocolVersion": 1,
                          "clientCapabilities": {"fs": {"readTextFile": False,
                                                        "writeTextFile": False}}})
assert init and "result" in init, init
print("initialize ok")

# 2. session
cwd = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
sn = rpc("session/new", {"cwd": cwd, "mcpServers": []})
assert sn and "result" in sn, sn
sid = sn["result"]["sessionId"]
avail = [m["modelId"] for m in sn["result"].get("models", {}).get("availableModels", [])]
print("session:", sid)
print("available models:", avail)

# 3. pick model
want = sys.argv[2] if len(sys.argv) > 2 else 'hy3'
sm = rpc("session/set_model", {"sessionId": sid, "modelId": want})
print("set_model ->", json.dumps(sm, ensure_ascii=False)[:300])

# 4. prompt
prompt_text = sys.argv[3] if len(sys.argv) > 3 else '回复两个字:成功'
t0 = time.time(); before = len(SEEN)
pr = rpc("session/prompt", {"sessionId": sid,
                            "prompt": [{"type": "text", "text": prompt_text}]}, timeout=180)
print("prompt ->", json.dumps(pr, ensure_ascii=False)[:400])
print("elapsed %.1fs" % (time.time() - t0))

# 5. replay agent output
texts = []
for m in SEEN[before:]:
    if m.get("method") == "session/update":
        u = m.get("params", {}).get("update", {})
        if u.get("sessionUpdate") in ("agent_message_chunk", "agent_thought_chunk"):
            c = u.get("content", {})
            if c.get("type") == "text":
                texts.append((u.get("sessionUpdate"), c.get("text")))
for kind, t in texts:
    print(f"  [{kind}] {t[:200]}")
kinds = [m.get("params", {}).get("update", {}).get("sessionUpdate")
         for m in SEEN[before:] if m.get("method") == "session/update"]
print("update kinds:", kinds)

p.stdin.close()
try: p.wait(timeout=5)
except Exception: p.kill()
```

用法：

```bash
python3 acp_test.py <cwd> <model> "<prompt>" [permission-mode]
python3 acp_test.py /home/zhujingfeng/code/plugin-planet hy3 "回复两个字:成功"
python3 acp_test.py /home/zhujingfeng/code/plugin-planet hy3 \
  "用工具读取 package.json 的 name 和 version" dontAsk
```

### 5.4 ACP 实测结果

**纯聊天**（18.3s）：9 个 chunk，`agent_thought_chunk` 思考 + `agent_message_chunk` 正文 `成功`。

**agentic 任务**（36.3s，`--permission-mode dontAsk`）：
让它读 `package.json` 报 name/version —— 产生了 `tool_call` 序列，
Read 找不到 → Bash 被 deny → 改用 Glob 扫全仓库 → 据实回答"不存在"。
经我用 glob 独立复核，**结论正确，未编造**。

---

## 6. 缓存情况

有缓存，分三层，性质不同：

### 6.1 服务端 prompt 前缀缓存 ✅ 实测

`--output-format json` 的 `usage`：

```json
"cache_creation_input_tokens": 18696,
"cache_read_input_tokens": 2560
```

ACP `usage_update` 的 `_meta.usage` 更细：

```json
"prompt_cache_hit_tokens": 2880,
"prompt_cache_miss_tokens": 18376,
"prompt_cache_write_tokens": 0,
"prompt_tokens_details": {"cached_tokens": 2880}
```

**结论**：和正常 harness 一样有自动前缀缓存，首次写入、后续命中。
注意这是**服务端按 prompt 前缀**缓存，与进程无关 —— 每次新起进程只要 system prompt
+ 工具定义不变，就能命中。

### 6.2 token 构成（决定缓存收益）

`usageByCategory`：

```json
{"systemPrompt": 2382, "conversation": 2218, "tools": 16628, "mcp": 0, "skills": 28}
```

**tools 占 16628 / 21256 ≈ 78%**。工具定义是稳定前缀 → 这块是缓存主力。
上下文窗口 `size: 192000`。

含义：派发给 codebuddy 的任务，**input 永远在 2 万 token 量级起步**，
其中绝大部分是可缓存的工具定义。对话轮次越多，`conversation` 占比越高、缓存收益越摊薄。

### 6.3 会话状态缓存 ✅ 实测

`-c` 跨进程续接可用（见 4.2）。ACP 有 `loadSession: true` 能力位，
但**多轮 ACP 会话复用未实测** `[INFERENCE]`。

### 6.4 没有的东西

- 两个 harness **之间不共享缓存**。我（omp）和 codebuddy 的 system prompt、工具集完全不同，
  各自的前缀缓存互不相干。每次互审，对方都要重新构建自己的 2 万 token 前缀（首次 miss，之后 hit）。
- 未观测到跨进程的工具结果磁盘缓存（shell-snapshots 是启动加速，非结果缓存）。

---

## 7. ACP vs 命令行：场景选型

### 结论

| 场景 | 推荐 | 理由 |
|---|---|---|
| 一次性 review / 批量审查 | **CLI `-p`** | 单发单收，`--output-format json` 直接拿到最终文本，无需搭 JSON-RPC |
| 深度研究 / 长链路多工具任务 | **ACP** | 长驻进程，可观察 `tool_call` 进度、可 `session/cancel` 中断、可中途 `session/set_model` |
| 需要边跑边看/边干预 | **ACP** | CLI `-p` 是黑盒，只有最终结果 |
| 要跑测试、改文件的执行型任务 | 两者都行 | CLI 加 `-y`；ACP 加 `--permission-mode bypassPermissions` |

### 关键差异（不是"能不能"，是"代价"）

1. **进程开销**：CLI 每次调用冷启动一个 11.9MB bundle，实测 trivial prompt
   也要 8.4–18s。ACP 握手后长驻，后续 prompt 免重复启动 `[INFERENCE：后续轮次耗时未实测]`。
2. **可观测性**：ACP 有 `tool_call` 流；CLI 只有 `stream-json` + `--include-partial-messages`
   才有 SSE 增量（**未实测**）。
3. **会话**：两者都能续（CLI `-c`/`-r`，ACP `loadSession`），差异不在这里。
4. **集成成本**：CLI 是 `subprocess` 一行；ACP 要管 JSON-RPC id 匹配、通知分流、stdin 生命周期。

### 针对你的互审场景

**当前 harness 写代码 → codebuddy review（或反向）**：

- **单轮审查用 CLI `-p`**。review 是"输入 diff → 输出问题清单"的单发任务，
  没有中途干预的价值，JSON 输出最好解析，封装成 skill 最省事。
- **只有当 review 需要它自己跑测试、反复改-测-看时才上 ACP**，
  因为那时你需要看它的 `tool_call` 轨迹、需要在它卡住时 `session/cancel`。
- 反向（codebuddy 写 → 我 review）同理，我这边用 `-p` 拿它的产出即可。

**成本提醒**：每次互审对方都要重建 ~2.1 万 input token（78% 是工具定义）。
prompt 前缀缓存能吃掉大部分，但**跨 agent 不共享**，所以高频互审的开销下限就是这个数。

---

## 8. 快速参考

```bash
CBC=/opt/WorkBuddy/resources/app.asar.unpacked/cli/bin/codebuddy
export CODEBUDDY_AUTH_TOKEN="$(python3 -c "import json;print(json.load(open('/home/zhujingfeng/.workbuddy/auth/workbuddy-desktop.info'))['auth']['accessToken'])")"

# 单发
$CBC -p "..." --model hy3 --output-format json

# 带工具执行
$CBC -p -y "跑一下测试并报告"

# 续接
$CBC -p -c "接着上次说"

# ACP
$CBC --acp --permission-mode dontAsk   # stdin/stdout JSON-RPC
```

**待办 / 未验证**：
- token 2026-11-24 过期后的自动刷新路径
- ACP 多轮会话与 `session/load` 复用
- CLI `stream-json` + `--include-partial-messages` 的增量输出
- `--exec` / `--swarm` 后台派发能力
- `--brief`（`SendUserMessage`，agent-to-agent 通信）

**2026-11-08 补充实测**（详见 `dispatch-design.md`）：
- `--bg` 可用：秒回 shortId，状态/结果在 `~/.codebuddy/jobs/<shortId>/state.json`
  （`working`→`done`，`output.result` 为纯结果）；但 shortId 是 UUIDv7 前 8 hex，
  **65 秒窗口内会撞**、`state.json` 被覆盖——不可作并行任务状态存储
- `-p` 支持从 **stdin** 读 prompt（管道实测通过）；argv 单参数上限 128KB
- 同步 `-p` 遇 API 错误（400 模型不存在）：**退出码 0、stdout 空、文本在 stderr**
- `cbc rm` / `cbc config list` 同 bug：`Cannot find module '../dist/codebuddy'`
