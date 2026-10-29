#!/usr/bin/env python3
"""Host detection and host-specific paths.

The statusline renders identically on CodeBuddy Code and Claude Code; the host
matters only for where we keep the runtime cache and which settings.json the
setup command rewrites.

Detection order (first match wins):
  1. the script own location, when it runs from a plugin cache
     (<config>/plugins/cache/<marketplace>/statusline/<version>/scripts);
  2. an explicit host environment variable;
  3. stdin keys that only one host sends;
  4. which config directory exists;
  5. CodeBuddy (our primary host).
"""

import json
import os

CODEBUDDY = 'codebuddy'
CLAUDE = 'claude'
HOSTS = (CODEBUDDY, CLAUDE)

# Stdin keys only Claude Code emits (statusline.md: effort/thinking/fast_mode/
# rate_limits/prompt_cache/prompt_id).
_CLAUDE_ONLY_KEYS = ('effort', 'thinking', 'rate_limits', 'prompt_cache',
                     'fast_mode', 'prompt_id')
# Stdin keys only CodeBuddy emits (collectStatusLineData: permission_mode,
# team, vim).
_CODEBUDDY_ONLY_KEYS = ('permission_mode', 'team', 'vim')


def _normalize(path):
    return os.path.abspath(path).replace('\\', '/').lower()


def detect(input_data=None, script_path=None):
    """Return 'codebuddy' or 'claude' for this invocation."""
    data = input_data if isinstance(input_data, dict) else {}

    path = _normalize(script_path or __file__)
    if '/.claude/plugins/cache/' in path:
        return CLAUDE
    if '/.codebuddy/plugins/cache/' in path:
        return CODEBUDDY

    if os.environ.get('CODEBUDDY_PLUGIN_ROOT') or os.environ.get('CODEBUDDY_CONFIG_DIR'):
        return CODEBUDDY
    if os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ.get('CLAUDE_CONFIG_DIR'):
        return CLAUDE

    if any(key in data for key in _CODEBUDDY_ONLY_KEYS):
        return CODEBUDDY
    if any(key in data for key in _CLAUDE_ONLY_KEYS):
        return CLAUDE

    has_cb = os.path.isdir(config_root(CODEBUDDY))
    has_claude = os.path.isdir(config_root(CLAUDE))
    if has_claude and not has_cb:
        return CLAUDE
    return CODEBUDDY


def config_root(host):
    """Per-host config directory (where that host keeps settings.json)."""
    if host == CLAUDE:
        return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
    return os.environ.get('CODEBUDDY_CONFIG_DIR') or os.path.expanduser('~/.codebuddy')


def settings_path(host):
    return os.path.join(config_root(host), 'settings.json')


def data_dir(host):
    """Persistent plugin data dir (layout config lives here)."""
    return os.path.join(config_root(host), 'plugins', 'data', 'statusline')


def plugin_cache_root(host):
    """Directory holding versioned copies of this plugin, e.g.
    ~/.claude/plugins/cache/plugin-planet/statusline/<version>/."""
    return os.path.join(config_root(host), 'plugins', 'cache', 'plugin-planet', 'statusline')


def _version_key(name):
    """Sort key for version dir names ('2.0.0' > '1.0.4', 'dev' sorts last)."""
    parts = []
    for piece in str(name).split('.'):
        digits = ''.join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else -1)
    return tuple(parts)


def newest_plugin_root(host):
    """Newest installed version directory for *host*, or '' when none."""
    root = plugin_cache_root(host)
    try:
        names = [n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))]
    except OSError:
        return ''
    if not names:
        return ''
    names.sort(key=_version_key)
    return os.path.join(root, names[-1])


# --- settings.json helpers (used by setup) ----------------------------------

def load_settings(path):
    """Read settings.json; {} when missing. Raises SystemExit on bad JSON."""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (IOError, ValueError) as exc:
        raise SystemExit('statusline: cannot read %s: %s' % (path, exc))
    return data if isinstance(data, dict) else {}


def write_settings(path, settings):
    """Atomically write settings.json (temp file + rename)."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, path)


def command_target(command):
    """Return the .py script a command line points at, or ''.

    setup always writes `<python> <script>`, so the last token ending in .py
    is the script; both quoted and plain tokens are accepted.
    """
    if not command or not isinstance(command, str):
        return ''
    tokens = []
    buf = []
    quote = ''
    for ch in command:
        if quote:
            if ch == quote:
                quote = ''
            else:
                buf.append(ch)
        elif ch in ('"', "'"):
            quote = ch
            if buf:
                tokens.append(''.join(buf))
                buf = []
        elif ch.isspace():
            if buf:
                tokens.append(''.join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        tokens.append(''.join(buf))
    for token in reversed(tokens):
        if token.lower().endswith('.py'):
            return token
    return ''


def same_target(command, script):
    """True when *command* already runs *script* (realpath comparison)."""
    target = command_target(command)
    if not target or not script:
        return False
    try:
        return (os.path.normcase(os.path.realpath(target))
                == os.path.normcase(os.path.realpath(script)))
    except OSError:
        return False


def build_command(python, script):
    """Statusline command string; quoted so paths with spaces survive."""
    return '"%s" "%s"' % (os.path.normpath(python), os.path.normpath(script))
