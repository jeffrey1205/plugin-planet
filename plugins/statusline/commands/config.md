---
description: "Adjust statusline display: show/hide blocks, reorder, toggle lines"
argument-hint: "<hide|show|move|enable|disable|reset|list> [args]"
---

Invoke as `/statusline:config`. Adjust the statusline layout by running the
`config.py` helper. The helper reads
and writes `<config>/plugins/data/statusline/config.json` atomically (CodeBuddy:
`~/.codebuddy/...`, Claude: `~/.claude/...`); changes take effect on the next
statusline render (no restart needed).

Resolve the plugin root at the start of the Bash call (each call is a fresh
shell, so the four lines must be repeated), then translate the user's request
into one of these commands:

```bash
ROOT="$CODEBUDDY_PLUGIN_ROOT"
[ -n "$ROOT" ] || ROOT="$CLAUDE_PLUGIN_ROOT"
[ -n "$ROOT" ] || ROOT=$(ls -d "$HOME"/.codebuddy/plugins/cache/plugin-planet/statusline/*/ 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d "$HOME"/.claude/plugins/cache/plugin-planet/statusline/*/ 2>/dev/null | sort -V | tail -1)

# Hide / show blocks (block-level)
python3 "$ROOT/scripts/config.py" hide credits time
python3 "$ROOT/scripts/config.py" show credits

# Reorder blocks (the order applies within the row each block belongs to)
python3 "$ROOT/scripts/config.py" move tokens after model
python3 "$ROOT/scripts/config.py" move requests to end

# Toggle whole lines (Tools / Recent)
python3 "$ROOT/scripts/config.py" disable tools
python3 "$ROOT/scripts/config.py" enable recent

# Reset to defaults (deletes the config file)
python3 "$ROOT/scripts/config.py" reset

# Show the current effective layout
python3 "$ROOT/scripts/config.py" list
```

Available blocks: `cwd_git`, `model`, `effort`, `context_bar`, `compact_periodic`,
`time`, `credits`, `requests`, `tokens`, `recent`, `speed`. The first seven
render on line 1, the last four on line 2. The `recent` toggle additionally
gates the line-3 recent calls; `lines` was folded into `cwd_git` and `cost`
was removed (both are rejected as unknown ids).

After running the command, read its printed "Layout (effective)" output and
confirm the change to the user in one short line. If the helper prints "Unknown
block(s)", correct the block name from the "Valid blocks" list and retry.
