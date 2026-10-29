#!/usr/bin/env python3
"""Unit tests for render.py module"""

import json
import os
import sys
import re
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest import mock

import stats

from render import (
    BLOCKS_LINE1,
    build_statusline,
    format_recent_calls,
    format_tools,
    resolve_layout,
    _render_recent,
    _display_dir_name,
    _format_tool_entry,
    _render_cwd_git,
    _render_context_bar,
    _render_speed,
    _merge_repeat_calls,
)

class TestFormatTools(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_tools({}), "")

    def test_single_tool(self):
        result = format_tools({"Bash": 1})
        self.assertIn("Bash", result)
        self.assertIn("✓", result)

    def test_tool_with_count(self):
        result = format_tools({"Bash": 5})
        self.assertIn("×5", result)

    def test_tool_order(self):
        result = format_tools({"Grep": 1, "Bash": 1, "Read": 1})
        bash_pos = result.index("Bash")
        read_pos = result.index("Read")
        grep_pos = result.index("Grep")
        self.assertLess(bash_pos, read_pos)
        self.assertLess(read_pos, grep_pos)

    def test_agent_running(self):
        result = format_tools({"Agent": 3}, running_agents=1)
        self.assertIn("↑", result)
        self.assertIn("✓", result)

    def test_agent_all_completed(self):
        result = format_tools({"Agent": 3}, running_agents=0)
        self.assertIn("✓", result)
        self.assertNotIn("↑", result)

    def test_agent_all_running(self):
        result = format_tools({"Agent": 2}, running_agents=2)
        self.assertIn("↑", result)
        self.assertNotIn("✓", result)

class TestFormatToolEntry(unittest.TestCase):
    def test_single(self):
        result = _format_tool_entry("✓", "\033[0;32m", "Bash", 1)
        self.assertIn("Bash", result)
        self.assertNotIn("×", result)

    def test_multiple(self):
        result = _format_tool_entry("✓", "\033[0;32m", "Bash", 5)
        self.assertIn("×5", result)

    def test_no_count(self):
        result = _format_tool_entry("↑", "\033[1;33m", "Agent")
        self.assertIn("Agent", result)
        self.assertNotIn("×", result)

class TestFormatRecentCalls(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_recent_calls([]), "")

    def test_single_call(self):
        calls = [{"name": "Bash", "summary": "ls -la"}]
        result = format_recent_calls(calls)
        self.assertIn("Bash", result)
        self.assertIn("ls -la", result)

    def test_multiple_calls_pipe_separated(self):
        calls = [
            {"name": "Bash", "summary": "ls -la"},
            {"name": "Read", "summary": "/data/app/main.py"},
        ]
        result = format_recent_calls(calls)
        self.assertIn("|", result)
        self.assertIn("Bash", result)
        self.assertIn("Read", result)

    def test_short_name_used(self):
        calls = [{"name": "WebSearch", "summary": "python async"}]
        result = format_recent_calls(calls)
        self.assertIn("Search", result)

    def test_no_summary(self):
        calls = [{"name": "Bash", "summary": "Bash"}]
        result = format_recent_calls(calls)
        self.assertIn("Bash", result)
        # Should not duplicate name when summary equals name

    def test_truncation_with_ellipsis(self):
        calls = [{"name": "Bash", "summary": "x" * 100}]
        result = format_recent_calls(calls)
        # Strip ANSI
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', result)
        self.assertIn("…", plain)
        self.assertLessEqual(len(plain), 70)


class TestResolveLayout(unittest.TestCase):
    def test_default_when_no_config(self):
        layout = resolve_layout(None)
        self.assertEqual(layout["line1_order"], BLOCKS_LINE1)
        self.assertTrue(layout["tools"])
        self.assertTrue(layout["recent"])

    def test_default_when_garbled(self):
        # Wrong shape must fall back to defaults, never raise.
        self.assertEqual(resolve_layout({"layout": "nope"})["line1_order"], BLOCKS_LINE1)
        self.assertEqual(resolve_layout({"layout": {"line1_order": 123}})["line1_order"], BLOCKS_LINE1)

    def test_hidden_omitted(self):
        cfg = {"layout": {"line1_hidden": ["credits", "time"]}}
        order = resolve_layout(cfg)["line1_order"]
        self.assertNotIn("credits", order)
        self.assertNotIn("time", order)

    def test_reorder_then_auto_append(self):
        # Only two blocks listed -> the rest auto-append in canonical order.
        cfg = {"layout": {"line1_order": ["model", "credits"]}}
        order = resolve_layout(cfg)["line1_order"]
        self.assertEqual(order[0], "model")
        self.assertEqual(order[1], "credits")
        # All known blocks still present (auto-appended).
        self.assertEqual(set(order), set(BLOCKS_LINE1))

    def test_hidden_overrides_order(self):
        # A block in both order and hidden must be excluded.
        cfg = {"layout": {"line1_order": ["cwd_git", "credits"], "line1_hidden": ["credits"]}}
        order = resolve_layout(cfg)["line1_order"]
        self.assertNotIn("credits", order)
        self.assertIn("cwd_git", order)

    def test_unknown_id_ignored(self):
        cfg = {"layout": {"line1_order": ["cwd_git", "bogus", "model"]}}
        order = resolve_layout(cfg)["line1_order"]
        self.assertNotIn("bogus", order)
        self.assertEqual(order[0], "cwd_git")
        self.assertEqual(order[1], "model")

    def test_recent_in_default_order(self):
        # 'recent' is a regular block now (line 2), between tokens and speed.
        order = resolve_layout(None)["line1_order"]
        self.assertIn("recent", order)
        self.assertLess(order.index("tokens"), order.index("recent"))
        self.assertLess(order.index("recent"), order.index("speed"))

    def test_recent_toggle_off_drops_block(self):
        layout = resolve_layout({"layout": {"recent": False}})
        self.assertNotIn("recent", layout["line1_order"])
        self.assertFalse(layout["recent"])

    def test_hide_recent_block(self):
        cfg = {"layout": {"line1_hidden": ["recent"]}}
        self.assertNotIn("recent", resolve_layout(cfg)["line1_order"])

    def test_legacy_lines_id_ignored(self):
        # Old configs referencing the removed 'lines' block: dropped, no error.
        cfg = {"layout": {"line1_order": ["cwd_git", "lines"],
                          "line1_hidden": ["lines"]}}
        order = resolve_layout(cfg)["line1_order"]
        self.assertNotIn("lines", order)
        self.assertEqual(set(order), set(BLOCKS_LINE1))

    def test_legacy_order_appends_recent_at_end(self):
        # A pre-recent config keeps its order; 'recent' auto-appends at the end.
        legacy = ["cwd_git", "model", "effort", "context_bar",
                  "compact_periodic", "tokens", "requests", "credits",
                  "time", "speed"]
        order = resolve_layout({"layout": {"line1_order": legacy}})["line1_order"]
        self.assertEqual(order[-1], "recent")

    def test_line_toggles_default_on(self):
        cfg = {"layout": {"tools": False, "recent": False}}
        layout = resolve_layout(cfg)
        self.assertFalse(layout["tools"])
        self.assertFalse(layout["recent"])


class TestDisplayDirName(unittest.TestCase):
    def test_normal_dir(self):
        self.assertEqual(_display_dir_name("/home/user/myproject"), "myproject")

    def test_trailing_slash(self):
        self.assertEqual(_display_dir_name("/home/user/myproject/"), "myproject")

    def test_codebuddy_worktree_shows_project_name(self):
        path = "/Users/runzhi/.codebuddy/statusline/.codebuddy/worktrees/worktree"
        self.assertEqual(_display_dir_name(path), "statusline")

    def test_git_linked_worktree_absolute_gitdir(self):
        # Simulate a git-linked worktree: .git is a file pointing at the
        # main repo's .git/worktrees/<name>.
        import tempfile
        import textwrap
        with tempfile.TemporaryDirectory() as d:
            wt = os.path.join(d, "my-wt")
            os.makedirs(wt)
            with open(os.path.join(wt, ".git"), "w") as f:
                f.write("gitdir: %s/myproject/.git/worktrees/my-wt\n"
                        % d)
            self.assertEqual(_display_dir_name(wt), "myproject")

    def test_git_linked_worktree_relative_gitdir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # Layout: <d>/checkouts/<wt>  with .git pointing at
            # ../myproject/.git/worktrees/<wt>
            wt = os.path.join(d, "checkouts", "wt")
            os.makedirs(wt)
            with open(os.path.join(wt, ".git"), "w") as f:
                f.write("gitdir: ../myproject/.git/worktrees/wt\n")
            self.assertEqual(_display_dir_name(wt), "myproject")

    def test_regular_git_repo_not_worktree(self):
        # A normal repo has a .git *directory*, not a link file.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "realproject")
            os.makedirs(os.path.join(repo, ".git"))
            self.assertEqual(_display_dir_name(repo), "realproject")

    def test_empty(self):
        self.assertEqual(_display_dir_name(""), "")
        self.assertEqual(_display_dir_name(None), "")


class TestRenderCwdGit(unittest.TestCase):
    def _call(self, current_dir, git_info):
        with mock.patch("render.get_git_info", return_value=git_info):
            return _render_cwd_git({"workspace": {"current_dir": current_dir}}, {})

    def test_worktree_shows_project_name_with_branch(self):
        out = self._call(
            "/Users/runzhi/.codebuddy/statusline/.codebuddy/worktrees/worktree",
            {"branch": "main", "dirty": False, "ahead": 0, "behind": 0},
        )
        self.assertIn("statusline", out)
        self.assertIn("main", out)

    def test_normal_dir(self):
        out = self._call(
            "/home/user/myproject",
            {"branch": "dev", "dirty": True, "ahead": 0, "behind": 0},
        )
        self.assertIn("myproject", out)
        self.assertIn("dev", out)


class TestRenderCwdGitLines(unittest.TestCase):
    """+N/-M is folded into the cwd_git block (space-joined, no '|')."""

    def _call(self, current_dir, git_info, cost):
        inp = {"workspace": {"current_dir": current_dir}, "cost": cost}
        with mock.patch("render.get_git_info", return_value=git_info):
            return re.sub(r'\033\[[0-9;]*m', '', _render_cwd_git(inp, {}))

    def test_glued_after_git_part(self):
        out = self._call(
            "/home/user/myproject",
            {"branch": "main", "dirty": False, "ahead": 0, "behind": 0},
            {"total_lines_added": 26, "total_lines_removed": 4},
        )
        self.assertIn("myproject on", out)
        self.assertTrue(out.endswith("+26/-4"))
        self.assertNotIn("|", out)

    def test_no_git_still_glued(self):
        out = self._call("/home/user/myproject", None,
                         {"total_lines_added": 3, "total_lines_removed": 1})
        self.assertEqual(out, "myproject +3/-1")

    def test_zero_lines_suppressed(self):
        out = self._call(
            "/home/user/myproject",
            {"branch": "main", "dirty": False, "ahead": 0, "behind": 0}, {})
        self.assertNotIn("+", out)
        self.assertNotIn("/-", out)

    def test_only_added_shows_both(self):
        # Old 'lines' semantics: whenever either side is >0 both numbers show.
        out = self._call("/home/user/myproject", None,
                         {"total_lines_added": 3, "total_lines_removed": 0})
        self.assertTrue(out.endswith("+3/-0"))

    def test_missing_cost_safe(self):
        out = self._call("/home/user/myproject", None, None)
        self.assertEqual(out, "myproject")


class TestBuildStatuslineConfig(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._orig_plugin_data = stats._PLUGIN_DATA
        stats._PLUGIN_DATA = self._tmp
        # Pin the width so assertions never depend on the ambient terminal.
        self._env = mock.patch.dict(os.environ, {"COLUMNS": "200"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        stats._PLUGIN_DATA = self._orig_plugin_data

    def _write_config(self, layout):
        with open(os.path.join(self._tmp, "config.json"), "w") as f:
            json.dump({"layout": layout}, f)

    def _sample(self):
        inp = {
            "model": {"display_name": "claude-sonnet"},
            "cost": {"total_cost_usd": 0.02, "total_duration_ms": 65000,
                     "total_api_duration_ms": 40000,
                     "total_lines_added": 3, "total_lines_removed": 1},
            "context_window": {"used_percentage": 12.5, "context_window_size": 200000,
                              "current_usage": {"input_tokens": 25000}},
        }
        stats = {
            "total_input": 3200, "total_output": 800, "total_cache_read": 1500,
            "total_reasoning": 0, "total_credits": 0, "request_count": 5,
            "tool_counts": {"Bash": 2, "Read": 1}, "running_agents": 0,
            "compact_count": 0, "periodic_count": 0,
            "recent_calls": [{"name": "Bash", "summary": "ls -la"}],
            "last_input": 3200, "last_output": 800, "last_cache_read": 1500,
            "last_credits": 0,
        }
        return inp, stats

    def test_default_output_unchanged(self):
        # No config file -> identical to the pre-config build.
        inp, stats = self._sample()
        out = build_statusline(inp, stats)
        self.assertIn("claude-sonnet", out)
        # No monetary amount is rendered on either host.
        self.assertNotIn("$", out)
        self.assertNotIn("¥", out)
        # 800 output tokens / 40s API time -> 20.0 t/s
        self.assertIn("20.0t/s", out)
        self.assertIn("Tools:", out)
        self.assertIn("Recent:", out)
        # 65s wall clock -> Time on line 1 (strip ANSI: the reset sits
        # between the "Time:" label and the value).
        plain = re.sub(r'\033\[[0-9;]*m', '', out)
        self.assertIn("Time:1m5s", plain)

    def test_hidden_removes_from_output(self):
        self._write_config({"line1_hidden": ["credits", "time"]})
        inp, stats = self._sample()
        out = build_statusline(inp, stats)
        # credits value 0 here so weak signal; check 'Time:' absence instead.
        self.assertNotIn("Time:", out)

    def test_disable_lines(self):
        self._write_config({"tools": False, "recent": False})
        inp, stats = self._sample()
        out = build_statusline(inp, stats)
        self.assertNotIn("Tools:", out)
        self.assertNotIn("Recent:", out)
        # The recent toggle also gates the line-3 recent calls (unchanged).
        self.assertNotIn("ls -la", out)

    def test_compact_periodic_own_slot(self):
        # compact_periodic must render as its own " | "-separated block,
        # not glued onto the previous segment (the pre-config behavior).
        self._write_config({})
        inp, stats = self._sample()
        stats["compact_count"] = 1
        stats["periodic_count"] = 2
        out = re.sub(r'\033\[[0-9;]*m', '', build_statusline(inp, stats))
        self.assertIn("| Compact×1", out)
        self.assertIn("Compact×1 Periodic×2", out)

    def test_compact_periodic_only_periodic_no_double_space(self):
        # When only Periodic is present, the block must not gain a leading
        # space (which would produce " |  Periodic" with a double space).
        self._write_config({})
        inp, stats = self._sample()
        stats["compact_count"] = 0
        stats["periodic_count"] = 1
        out = re.sub(r'\033\[[0-9;]*m', '', build_statusline(inp, stats))
        self.assertIn("| Periodic×1", out)
        self.assertNotIn("|  Periodic", out)

    def test_cache_total_hit_rate(self):
        # tokens块的Cache显示总命中率，与第三行格式一致。
        # _sample(): total_input=3200, total_cache_read=1500 -> int(1500/3200*100)=46%
        self._write_config({})
        inp, stats = self._sample()
        out = re.sub(r'\033\[[0-9;]*m', '', build_statusline(inp, stats))
        self.assertIn("Cache:46%", out)


class TestRenderContextBar(unittest.TestCase):
    """Context bar fallbacks when model metadata is incomplete.

    Models without max-context metadata (e.g. hy4-dev) report
    context_window_size=0 / used_percentage=null while still reporting
    current_usage.input_tokens. The block must still show something.
    """

    def _call(self, ctx):
        return re.sub(r'\033\[[0-9;]*m', '',
                      _render_context_bar({"context_window": ctx}, {}))

    def test_no_max_context_shows_current_usage(self):
        # hy4-dev case: no context_window_size, no used_percentage,
        # but current_usage.input_tokens is present.
        out = self._call({"used_percentage": None, "context_window_size": 0,
                          "current_usage": {"input_tokens": 45678}})
        self.assertEqual(out, "45.7K")

    def test_no_max_context_with_used_percentage(self):
        # used_percentage present but no max size: bar + pct, no used count.
        out = self._call({"used_percentage": 25, "context_window_size": 0,
                          "current_usage": {"input_tokens": 45678}})
        self.assertIn("25%", out)
        self.assertNotIn("45.7K", out)
        self.assertIn("█", out)

    def test_bar_has_no_borders(self):
        # '░' carries the track through to the end, so no opening '▕' or
        # closing '▏' borders are drawn around the bar.
        out = self._call({"used_percentage": 34, "context_window_size": 200000,
                          "current_usage": {"input_tokens": 68000}})
        self.assertIn("█", out)
        self.assertNotIn("▕", out)
        self.assertNotIn("▏", out)

    def test_max_context_no_percentage_shows_ceiling(self):
        # No percentage, but max size known: the ceiling is enough; the used
        # count is already in the Tokens block and would only add width.
        out = self._call({"used_percentage": None, "context_window_size": 200000,
                          "current_usage": {"input_tokens": 25000}})
        self.assertEqual(out, "Max:200.0K")

    def test_max_context_only_unchanged(self):
        # Pre-existing behavior: max known, no current usage -> "Max:" only.
        out = self._call({"used_percentage": None, "context_window_size": 200000,
                          "current_usage": None})
        self.assertEqual(out, "Max:200.0K")

    def test_full_data_shows_pct_and_ceiling(self):
        out = self._call({"used_percentage": 12.5, "context_window_size": 200000,
                          "current_usage": {"input_tokens": 25000}})
        # 12.5% -> round() gives 12 (banker's rounding), not 13.
        self.assertIn("12%", out)
        self.assertIn("200.0K", out)
        # Used tokens are the Tokens block's job; repeating them here overflowed.
        self.assertNotIn("25.0K/", out)

    def test_cache_heavy_usage_sums_all_parts(self):
        # Cache-heavy session: input_tokens is the non-cached part and can be
        # 0; the context length is the sum of input + cache_creation + cache_read.
        out = self._call({"used_percentage": 4, "context_window_size": 1_000_000,
                          "current_usage": {"input_tokens": 0,
                                            "cache_creation_input_tokens": 2000,
                                            "cache_read_input_tokens": 38000}})
        self.assertIn("4%", out)
        self.assertIn("1.0M", out)
        self.assertNotIn("40.0K", out)

    def test_size_and_pct_without_usage_shows_ceiling(self):
        # Model reports window size + percentage but omits
        # current_usage.input_tokens: derive used count so the block reads
        # `used/total` instead of only the ceiling.
        out = self._call({"used_percentage": 4, "context_window_size": 1_000_000,
                          "current_usage": None})
        self.assertIn("4%", out)
        self.assertIn("1.0M", out)

    def test_empty_context_window_renders_nothing(self):
        # Nothing to show at all -> block suppressed (not a stray separator).
        self.assertEqual(self._call({}), "")
        self.assertEqual(self._call({"used_percentage": None,
                                     "context_window_size": 0,
                                     "current_usage": {}}), "")

    def test_zero_tokens_renders_nothing(self):
        # input_tokens=0 means "not reported", not "empty context".
        self.assertEqual(self._call({"used_percentage": None,
                                     "context_window_size": 0,
                                     "current_usage": {"input_tokens": 0}}), "")

    def test_null_context_window_renders_nothing(self):
        self.assertEqual(_render_context_bar({"context_window": None}, {}), "")

    def test_non_numeric_used_percentage_falls_back(self):
        # A malformed host payload must not crash the statusline: treat a
        # non-numeric used_percentage as absent and fall through.
        out = self._call({"used_percentage": "abc", "context_window_size": 0,
                          "current_usage": {"input_tokens": 5000}})
        self.assertEqual(out, "5.0K")

    def test_non_numeric_used_percentage_with_max(self):
        out = self._call({"used_percentage": "abc", "context_window_size": 200000,
                          "current_usage": {"input_tokens": 5000}})
        self.assertEqual(out, "Max:200.0K")


class TestRenderSpeed(unittest.TestCase):
    """Session-average throughput = total_output / cost.total_api_duration_ms.

    The denominator must be the host's pure API time, never the wall-clock
    total_duration_ms (tool runs and idle waits would deflate the rate).
    Shown as `Avg:` on line 2; the recent delta is the `Speed:` item inside
    the line-2 `recent` block.
    """

    def _call(self, inp, st):
        return re.sub(r'\033\[[0-9;]*m', '', _render_speed(inp, st))

    def test_rate(self):
        # 4000 tokens over 40s of API time -> 100.0 t/s
        inp = {"cost": {"total_api_duration_ms": 40000}}
        self.assertEqual(self._call(inp, {"total_output": 4000}), "Avg:100.0t/s")

    def test_uses_api_duration_not_wall_clock(self):
        # Same tokens, 40s API vs 200s wall -> must report 100.0, not 20.0.
        inp = {"cost": {"total_api_duration_ms": 40000,
                        "total_duration_ms": 200000}}
        self.assertIn("Avg:100.0t/s", self._call(inp, {"total_output": 4000}))

    def test_zero_api_duration_suppressed(self):
        inp = {"cost": {"total_api_duration_ms": 0}}
        self.assertEqual(self._call(inp, {"total_output": 4000}), "")

    def test_zero_output_suppressed(self):
        inp = {"cost": {"total_api_duration_ms": 4000}}
        self.assertEqual(self._call(inp, {"total_output": 0}), "")

    def test_missing_cost_suppressed(self):
        self.assertEqual(self._call({}, {"total_output": 100}), "")

    def test_null_cost_suppressed(self):
        self.assertEqual(self._call({"cost": None}, {"total_output": 100}), "")

    def test_wall_clock_only_suppressed(self):
        # Only total_duration_ms present: must not fall back to it.
        inp = {"cost": {"total_duration_ms": 30000}}
        self.assertEqual(self._call(inp, {"total_output": 100}), "")

    def test_null_api_duration_suppressed(self):
        inp = {"cost": {"total_api_duration_ms": None}}
        self.assertEqual(self._call(inp, {"total_output": 100}), "")


class TestRenderRecent(unittest.TestCase):
    """The 'recent' block: last-turn In/Out/Cache% and Speed (recent rate)."""

    def _call(self, st, recent_rate=None):
        st = dict(st)
        st['recent_rate'] = recent_rate
        return re.sub(r'\033\[[0-9;]*m', '', _render_recent({}, st))

    def test_full(self):
        out = self._call({"last_input": 1000, "last_output": 200,
                          "last_cache_read": 500}, 12.3)
        self.assertEqual(out, "Recent: In:1.0K Out:200 Cache:50% Speed:12.3t/s")

    def test_rate_none_omitted(self):
        out = self._call({"last_input": 1000, "last_output": 200}, None)
        self.assertEqual(out, "Recent: In:1.0K Out:200")

    def test_zero_rate_shown(self):
        # A measured 0.0 t/s is still a measurement (not None) -> render it.
        out = self._call({"last_input": 1000, "last_output": 200}, 0.0)
        self.assertIn("Speed:0.0t/s", out)

    def test_no_cache_key_omits_cache(self):
        out = self._call({"last_input": 1000, "last_output": 200,
                          "last_cache_read": 0})
        self.assertNotIn("Cache:", out)

    def test_no_last_tokens_suppressed(self):
        self.assertEqual(self._call({}), "")
        self.assertEqual(self._call({"last_input": 0, "last_output": 0}), "")



class TestLineGrouping(unittest.TestCase):
    """Three semantic rows: environment+context / totals / activity."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._orig = stats._PLUGIN_DATA
        stats._PLUGIN_DATA = self._tmp
        self._env = mock.patch.dict(os.environ, {"COLUMNS": "200"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        stats._PLUGIN_DATA = self._orig

    def _st(self):
        return {
            "total_input": 3200, "total_output": 800, "total_cache_read": 1500,
            "total_reasoning": 5000, "total_credits": 4.5, "request_count": 7,
            "tool_counts": {"Bash": 2}, "running_agents": 0,
            "compact_count": 1, "periodic_count": 0,
            "recent_calls": [{"name": "Bash", "summary": "ls -la"}],
            "last_input": 900, "last_output": 100, "last_cache_read": 450,
            "last_credits": 1.0,
        }

    def _inp(self):
        return {
            "model": {"display_name": "m"},
            "cost": {"total_duration_ms": 65000, "total_api_duration_ms": 40000},
            "context_window": {"used_percentage": 27, "context_window_size": 1000000,
                              "current_usage": {"input_tokens": 265100}},
        }

    def _lines(self, inp=None, st=None):
        out = build_statusline(inp or self._inp(), st or self._st())
        plain = re.sub(r'\033\[[0-9;?]*[A-Za-z]', '', out)
        return plain.split("\n")

    def test_three_rows(self):
        lines = self._lines()
        self.assertEqual(len(lines), 3)

    def test_row1_is_environment_and_context(self):
        line = self._lines()[0]
        self.assertIn("m", line)
        self.assertIn("27%", line)
        self.assertIn("1.0M", line)
        self.assertIn("Compact×1", line)
        self.assertIn("Time:1m5s", line)
        self.assertIn("Credits:4.50", line)
        self.assertLess(line.index("Time:"), line.index("Credits:"))
        self.assertNotIn("In:", line)
        self.assertNotIn("Tools:", line)

    def test_row2_is_session_totals(self):
        line = self._lines()[1]
        self.assertIn("In:3.2K", line)
        self.assertIn("Req:7", line)
        self.assertIn("Recent: In:900 Out:100 Cache:50%", line)
        self.assertIn("Avg:20.0t/s", line)
        # Credits moved to line 1; requests lead the row.
        self.assertNotIn("Credits:", line)
        self.assertLess(line.index("Req:"), line.index("In:"))
        self.assertLess(line.index("In:"), line.index("Recent:"))
        self.assertLess(line.index("Recent:"), line.index("Avg:"))
        self.assertNotIn("Tools:", line)

    def test_row3_is_activity(self):
        line = self._lines()[2]
        self.assertIn("Tools:", line)
        self.assertIn("Bash", line)

    def test_recent_speed_only_when_rate_given(self):
        # The recent rate is None until the second render with new output.
        self.assertNotIn("Speed:", "\n".join(self._lines()))
        with_rate = build_statusline(self._inp(), self._st(), 12.3)
        plain = re.sub(r'\033\[[0-9;?]*[A-Za-z]', '', with_rate).split("\n")
        self.assertIn("Speed:12.3t/s", plain[1])

    def test_think_not_rendered(self):
        self.assertNotIn("Think", "\n".join(self._lines()))

    def test_cache_is_percentage_only(self):
        text = "\n".join(self._lines())
        self.assertIn("Cache:46%", text)
        self.assertIn("Cache:50%", text)
        self.assertNotIn("Cache:1.5K", text)

    def test_context_hides_used_tokens(self):
        line = self._lines()[0]
        self.assertNotIn("265.1K", line)

    def test_credits_not_duplicated_in_recent(self):
        # Credits lives on line 1 only; the line-2 Recent block never repeats it.
        text = "\n".join(self._lines())
        self.assertEqual(text.count("Credits:"), 1)
        self.assertIn("Credits:", text.split("\n")[0])

    def test_multiline_summary_flattened(self):
        out = format_recent_calls([{"name": "Bash", "summary": "a\nb\tc"}])
        self.assertNotIn("\n", out)
        self.assertIn("a b c", re.sub(r'\033\[[0-9;]*m', '', out))

    def test_all_rows_fit_narrow_terminal(self):
        st = self._st()
        st["recent_calls"] = [
            {"name": "Bash", "summary": "cmd-%d %s" % (i, "x" * 200)} for i in range(3)
        ]
        with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
            lines = self._lines(st=st)
        for line in lines:
            self.assertLessEqual(len(line), 100, line)
        # Most recent calls survive (shrunk, or the oldest dropped if needed).
        self.assertGreaterEqual(lines[2].count("cmd-"), 1)

    def test_wide_terminal_keeps_three_calls(self):
        st = self._st()
        st["recent_calls"] = [
            {"name": "Bash", "summary": "cmd-%d" % i} for i in range(3)
        ]
        with mock.patch.dict(os.environ, {"COLUMNS": "260"}):
            lines = self._lines(st=st)
        self.assertEqual(lines[2].count("cmd-"), 3)

    def test_merge_repeat_calls_collapses_adjacent(self):
        calls = [{"name": "Bash", "summary": "git status"},
                 {"name": "Bash", "summary": "git status"},
                 {"name": "Bash", "summary": "ls"}]
        merged = _merge_repeat_calls(calls)
        self.assertEqual([c.get("count", 1) for c in merged], [2, 1])
        self.assertEqual(merged[1]["summary"], "ls")

    def test_merge_repeat_calls_keeps_non_adjacent(self):
        calls = [{"name": "Bash", "summary": "a"},
                 {"name": "Bash", "summary": "b"},
                 {"name": "Bash", "summary": "a"}]
        self.assertEqual(len(_merge_repeat_calls(calls)), 3)

    def test_merge_repeat_calls_does_not_mutate_input(self):
        calls = [{"name": "Bash", "summary": "a"},
                 {"name": "Bash", "summary": "a"}]
        _merge_repeat_calls(calls)
        self.assertNotIn("count", calls[0])

    def test_format_recent_calls_shows_repeat_count(self):
        merged = _merge_repeat_calls(
            [{"name": "Bash", "summary": "git status"}] * 3)
        out = re.sub(r"\033\[[0-9;]*m", "", format_recent_calls(merged))
        self.assertIn("×3", out)

    def test_line3_tracks_line2_width_not_terminal(self):
        # Even on a 260-column terminal the activity row stays roughly as
        # wide as the totals row instead of stretching with the terminal.
        st = self._st()
        st["recent_calls"] = [
            {"name": "Bash", "summary": "cmd-%d %s" % (i, "x" * 200)}
            for i in range(3)]
        with mock.patch.dict(os.environ, {"COLUMNS": "260"}):
            lines = self._lines(st=st)
        self.assertLessEqual(len(lines[2]), len(lines[1]) + 2)
        self.assertGreaterEqual(lines[2].count("cmd-"), 1)

    def test_repeated_calls_merge_and_free_budget(self):
        st = self._st()
        st["recent_calls"] = [
            {"name": "Bash", "summary": "git status --short"}] * 3
        with mock.patch.dict(os.environ, {"COLUMNS": "260"}):
            lines = self._lines(st=st)
        self.assertIn("×3", lines[2])
        self.assertIn("git status --short", lines[2])
        self.assertLessEqual(len(lines[2]), len(lines[1]) + 2)

    def test_tiny_line2_still_shows_calls(self):
        # Line 2 reduced to Req only: the parity cap falls below the floor,
        # but the newest calls must not vanish.
        with open(os.path.join(self._tmp, "config.json"), "w") as f:
            json.dump({"layout": {"line1_hidden":
                                  ["tokens", "recent", "speed"]}}, f)
        st = self._st()
        st["recent_calls"] = [{"name": "Bash", "summary": "cmd-%d" % i}
                              for i in range(3)]
        lines = self._lines(st=st)
        self.assertGreaterEqual(lines[2].count("cmd-"), 2)


if __name__ == "__main__":
    unittest.main()
