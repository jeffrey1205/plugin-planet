#!/usr/bin/env python3
"""Black-box tests for scripts/cbc-task using a fake cbc binary."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), 'scripts', 'cbc-task')

FAKE_CBC = '''#!/bin/sh
# State lives next to this script, not in the environment: cbc-task hands the
# child a whitelisted env, so FAKE_* vars would not survive. No dirname(1)
# either — some tests run with a PATH that holds only cat and sleep.
D=${0%/*}; [ "$D" = "$0" ] && D=.
printf '%s\\n' "$@" > "$D/argv.txt"
printf '%s\\n' "${CODEBUDDY_AUTH_TOKEN:-}" > "$D/token.txt"
env > "$D/env.txt"
cat > "$D/stdin.actual"
[ -f "$D/stderr.txt" ] && cat "$D/stderr.txt" >&2
if [ "$(cat "$D/mode" 2>/dev/null)" = sleep ]; then sleep "$(cat "$D/sleep")"; fi
cat "$D/stdout.json" 2>/dev/null
code=0; [ -f "$D/exit.code" ] && code=$(cat "$D/exit.code")
exit "$code"
'''

SUCCESS_JSON = json.dumps([
    {"type": "message", "role": "user",
     "content": [{"type": "input_text", "text": "q"}]},
    {"type": "reasoning",
     "rawContent": [{"type": "reasoning_text", "text": "SECRET_THOUGHT"}]},
    {"type": "message", "role": "assistant",
     "providerData": {"model": "hy3"},
     "content": [{"type": "output_text", "text": "最终结果OK"}]},
    {"type": "result", "subtype": "success", "is_error": False,
     "result": "最终结果OK", "duration_ms": 1234, "duration_api_ms": 1200,
     "num_turns": 3, "usage": {"input_tokens": 10, "output_tokens": 5}},
])

ISERROR_JSON = json.dumps([
    {"type": "message", "role": "assistant",
     "providerData": {"model": "hy3"},
     "content": [{"type": "output_text", "text": "err"}]},
    {"type": "result", "subtype": "error", "is_error": True,
     "result": "400 model [nope] service info not found",
     "duration_ms": 10, "num_turns": 1, "usage": {}},
])

AUTHERR_JSON = json.dumps([
    {"type": "message", "role": "assistant",
     "providerData": {"model": "hy3"},
     "content": [{"type": "output_text", "text": "err"}]},
    {"type": "result", "subtype": "error", "is_error": True,
     "result": "Authentication required. Please use /login command "
               "to sign in to your account",
     "duration_ms": 10, "num_turns": 1, "usage": {}},
])


class CbcTaskCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='cbc-task-test-')
        self.tasks = os.path.join(self.tmp, 'tasks')
        self.fake = os.path.join(self.tmp, 'fake-cbc')
        with open(self.fake, 'w') as f:
            f.write(FAKE_CBC)
        os.chmod(self.fake, 0o755)
        self.args_file = os.path.join(self.tmp, 'argv.txt')
        self.out_file = os.path.join(self.tmp, 'stdout.json')
        self.stdin_file = os.path.join(self.tmp, 'stdin.actual')
        self.env_file = os.path.join(self.tmp, 'token.txt')
        self.stderr_file = os.path.join(self.tmp, 'stderr.txt')
        self.mode_file = os.path.join(self.tmp, 'mode')
        self.sleep_file = os.path.join(self.tmp, 'sleep')
        self.exit_file = os.path.join(self.tmp, 'exit.code')
        self._children = []
        self.wb_log = os.path.join(self.tmp, 'wb.log')
        self.extractor = os.path.join(self.tmp, 'fake-wb')
        with open(self.extractor, 'w') as f:
            f.write('#!/bin/sh\n'
                    'echo x >> "$FAKE_WB_LOG"\n'
                    'if [ -n "$FAKE_WB_FAIL" ]; then '
                    'echo "no login state" >&2; exit 1; fi\n'
                    'printf "auto-token\\n"\n')
        os.chmod(self.extractor, 0o755)
        self._write_out(SUCCESS_JSON)

    def tearDown(self):
        for child in self._children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def _write_out(self, content):
        with open(self.out_file, 'w') as f:
            f.write(content)

    def set_sleep(self, seconds):
        with open(self.mode_file, 'w') as f:
            f.write('sleep')
        with open(self.sleep_file, 'w') as f:
            f.write(str(seconds))

    def set_exit(self, code):
        with open(self.exit_file, 'w') as f:
            f.write(str(code))

    def set_stderr(self, text):
        with open(self.stderr_file, 'w') as f:
            f.write(text + '\n')

    def read_argv(self, path=None):
        with open(path or self.args_file) as f:
            return f.read().splitlines()

    def read_child_env(self, path=None):
        with open(path or os.path.join(self.tmp, 'env.txt')) as f:
            return dict(line.split('=', 1) for line in f.read().splitlines()
                        if '=' in line)

    def _env(self, **over):
        env = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': self.tmp,
            'CBC_BIN': self.fake,
            'CBC_BIN_DIRS': '',
            'CBC_TASK_DIR': self.tasks,
            'WB_AUTH_TOKEN_BIN': self.extractor,
            'FAKE_WB_LOG': self.wb_log,
            'FAKE_WB_FAIL': '',
        }
        env.update(over)
        return env

    def cli(self, *args, **kw):
        env = self._env(**kw.pop('env', {}))
        inp = kw.pop('input', None)
        return subprocess.run([sys.executable, SCRIPT, *args],
                              capture_output=True, text=True,
                              env=env, input=inp, timeout=60)

    def bg_run(self, *args, **kw):
        """Start `run` in background; returns Popen. Caller must p.wait()."""
        env = self._env(**kw.pop('env', {}))
        return subprocess.Popen(
            [sys.executable, SCRIPT, 'run', *args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    def status(self, tid, env=None):
        """state+detail synthesized from a `list` row (no status subcommand)."""
        r = self.cli('list', **({'env': env} if env else {}))
        for line in r.stdout.splitlines():
            f = line.split('\t')
            if len(f) >= 4 and f[0] == tid:
                out = f[1] + (('\n' + f[3]) if f[3] else '')
                return subprocess.CompletedProcess(r.args, 0, out, r.stderr)
        return subprocess.CompletedProcess(r.args, 4, '',
                                           'task not found: %s\n' % tid)

    @staticmethod
    def _state(r):
        return r.stdout.splitlines()[0].strip() if r.stdout.strip() else ''

    def wait_state(self, tid, want, deadline=15):
        end = time.time() + deadline
        while True:
            r = self.status(tid)
            if self._state(r) == want:
                return r
            if time.time() > end:
                self.fail(f'task {tid} never reached {want}: '
                          f'state={self._state(r)!r} rc={r.returncode} '
                          f'out={r.stdout!r} err={r.stderr!r}')
            time.sleep(0.15)

    # -- tests ------------------------------------------------------------

    def test_result_returns_final_text_only(self):
        r = self.cli('run', '--name', 'res1', 'do something')
        self.assertEqual(r.returncode, 0, r.stderr)
        rr = self.cli('result', 'res1')
        self.assertEqual(rr.returncode, 0, rr.stderr)
        self.assertEqual(rr.stdout.strip(), '最终结果OK')
        self.assertNotIn('SECRET_THOUGHT', rr.stdout)
        with open(os.path.join(self.tasks, 'res1', 'result.json')) as f:
            meta = json.load(f)
        self.assertFalse(meta['is_error'])
        self.assertEqual(meta['model'], 'hy3')
        self.assertEqual(meta['duration_ms'], 1234)
        self.assertEqual(meta['num_turns'], 3)

    def test_args_passthrough(self):
        r = self.cli('run', '--name', 'args1', '--model', 'hy3',
                     'hello world')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.args_file) as f:
            argv = f.read().splitlines()
        self.assertIn('-p', argv)
        self.assertIn('hello world', argv)
        self.assertIn('--output-format', argv)
        self.assertIn('json', argv)
        self.assertIn('--permission-mode', argv)
        self.assertIn('dontAsk', argv)
        self.assertIn('--model', argv)
        self.assertIn('hy3', argv)
        # no --model -> not injected
        r2 = self.cli('run', '--name', 'args2', 'plain')
        self.assertEqual(r2.returncode, 0, r2.stderr)
        with open(self.args_file) as f:
            argv2 = f.read().splitlines()
        self.assertNotIn('--model', argv2)

    def test_nonzero_exit_marks_failed(self):
        self._write_out('cbc exploded\n')
        self.set_exit(1)
        r = self.cli('run', '--name', 'bad1', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('exit 1', r.stdout)
        s = self.status('bad1')
        self.assertEqual(self._state(s), 'failed', s.stdout)
        self.assertIn('exit 1', s.stdout)
        rr = self.cli('result', 'bad1')
        self.assertEqual(rr.returncode, 1)
        self.assertIn('exit 1', rr.stdout)

    def test_is_error_json_marks_failed_with_error_text(self):
        self._write_out(ISERROR_JSON)
        r = self.cli('run', '--name', 'bad2', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('400 model [nope]', r.stdout)
        s = self.status('bad2')
        self.assertEqual(self._state(s), 'failed', s.stdout)
        self.assertIn('is_error', s.stdout)
        rr = self.cli('result', 'bad2')
        self.assertEqual(rr.returncode, 1)
        self.assertIn('400 model [nope]', rr.stdout)

    def test_garbage_output_marks_failed(self):
        self._write_out('not json at all\n')
        r = self.cli('run', '--name', 'bad3', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rr = self.cli('result', 'bad3')
        self.assertEqual(rr.returncode, 1)

    def test_running_then_kill(self):
        self.set_sleep(60)
        p = self.bg_run('--name', 'long1', 'x')
        self.wait_state('long1', 'running')
        s = self.status('long1')
        self.assertEqual(self._state(s), 'running', s.stdout)
        rr = self.cli('result', 'long1')
        self.assertEqual(rr.returncode, 2, rr.stdout + rr.stderr)
        k = self.cli('kill', 'long1')
        self.assertEqual(k.returncode, 0, k.stderr)
        self.wait_state('long1', 'failed', deadline=10)
        p.wait(timeout=15)

    def test_timeout_kills_and_marks_failed(self):
        self.set_sleep(60)
        r = self.cli('run', '--name', 'to1', 'x', '--timeout', '1')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('timeout', r.stdout)
        s = self.status('to1')
        self.assertEqual(self._state(s), 'failed', s.stdout)
        self.assertIn('timeout', s.stdout)
        rr = self.cli('result', 'to1')
        self.assertEqual(rr.returncode, 1)

    def test_duplicate_name_rejected(self):
        self.set_sleep(10)
        p = self.bg_run('--name', 'dup', 'x')
        self.wait_state('dup', 'running')
        r2 = self.cli('run', '--name', 'dup', 'y')
        self.assertEqual(r2.returncode, 3, r2.stdout + r2.stderr)
        self.assertIn('already exists', r2.stderr)
        self.cli('kill', 'dup')
        p.wait(timeout=15)

    def test_unknown_task(self):
        r = self.cli('result', 'no-such-task')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not found', r.stderr)

    def test_binary_not_found(self):
        empty = os.path.join(self.tmp, 'emptybin')
        os.makedirs(empty)
        r = self.cli('run', 'x', env={'CBC_BIN': '', 'PATH': empty})
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn('CBC_BIN', r.stderr)

    def test_default_bin_dirs_used_when_env_and_path_empty(self):
        d = os.path.join(self.tmp, 'defaultbin')
        os.makedirs(d)
        shutil.copy(self.fake, os.path.join(d, 'codebuddy'))
        with open(os.path.join(d, 'stdout.json'), 'w') as f:
            f.write(SUCCESS_JSON)
        # PATH holds coreutils the fake needs, but no codebuddy/cbc:
        # only the default dirs can resolve a binary.
        pdir = os.path.join(self.tmp, 'pathbin')
        os.makedirs(pdir)
        for tool in ('cat', 'sleep'):
            shutil.copy(shutil.which(tool), os.path.join(pdir, tool))
        env = {'CBC_BIN': '', 'PATH': pdir, 'CBC_BIN_DIRS': d}
        r = self.cli('run', '--name', 'defbin', 'x', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        # the copied fake keeps its state next to itself, not in self.tmp
        self.assertIn('-p', self.read_argv(os.path.join(d, 'argv.txt')))

    def test_check_subcommand_removed(self):
        r = self.cli('check')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_status_subcommand_removed(self):
        r = self.cli('status', 'x')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_list_shows_done_task(self):
        r = self.cli('run', '--name', 'listed1', 'x')
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli('list')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('listed1', r.stdout)
        self.assertIn('done', r.stdout)

    def test_stale_running_reported_failed(self):
        d = os.path.join(self.tasks, 'stale1')
        os.makedirs(d)
        with open(os.path.join(d, 'prompt.log'), 'w') as f:
            f.write('x')
        with open(os.path.join(d, 'status'), 'w') as f:
            f.write('running\n')
        p = subprocess.Popen([sys.executable, '-c', 'pass'])
        p.wait()
        with open(os.path.join(d, 'pid'), 'w') as f:
            f.write(str(p.pid))
        s = self.status('stale1')
        self.assertEqual(self._state(s), 'failed', s.stdout)
        self.assertIn('stale', s.stdout)

    def test_exit_code_arriving_after_pid_death_is_not_stale(self):
        """monitor 在 waitpid 回收与写 exit.code 之间时，不得把完成的任务判死。"""
        d = os.path.join(self.tasks, 'race1')
        os.makedirs(d)
        for name, text in (('prompt.log', 'x'), ('status', 'running\n'),
                           ('full.json', SUCCESS_JSON)):
            with open(os.path.join(d, name), 'w') as f:
                f.write(text)
        p = subprocess.Popen([sys.executable, '-c', 'pass'])
        p.wait()
        with open(os.path.join(d, 'pid'), 'w') as f:
            f.write(str(p.pid))
        late = os.path.join(d, 'exit.code')
        self._children.append(subprocess.Popen(
            ['/bin/sh', '-c', 'sleep 0.3; printf 0 > "%s"' % late]))
        s = self.status('race1')
        self.assertEqual(self._state(s), 'done', s.stdout)

    def test_stdin_prompt(self):
        text = 'STDIN_PROMPT 内容\n第二行'
        r = self.cli('run', '--name', 'stdin1', '-', input=text)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.args_file) as f:
            argv = f.read().splitlines()
        self.assertIn('-p', argv)
        self.assertNotIn(text, argv, 'prompt must not go through argv')
        with open(os.path.join(self.tasks, 'stdin1', 'prompt.log')) as f:
            self.assertEqual(f.read(), text)
        with open(self.stdin_file) as f:
            self.assertEqual(f.read(), text)

    def test_stdin_prompt_large(self):
        big = 'A' * 150000
        r = self.cli('run', '--name', 'stdin-big', '-', input=big)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.tasks, 'stdin-big', 'prompt.log')) as f:
            self.assertEqual(len(f.read()), 150000)
        rr = self.cli('result', 'stdin-big')
        self.assertEqual(rr.returncode, 0, rr.stderr)

    def test_failed_task_surfaces_stderr_text(self):
        self._write_out('')
        self.set_stderr('400 model [nope] service info not found')
        r = self.cli('run', '--name', 'stderr1', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('400 model [nope]', r.stdout)
        s = self.status('stderr1')
        self.assertEqual(self._state(s), 'failed', s.stdout)
        self.assertIn('400 model [nope]', s.stdout)
        rr = self.cli('result', 'stderr1')
        self.assertEqual(rr.returncode, 1)
        self.assertIn('400 model [nope]', rr.stdout)

    def test_auto_names_are_unique(self):
        r1 = self.cli('run', 'a')
        r2 = self.cli('run', 'b')
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        r = self.cli('list')
        ids = [line.split('\t')[0] for line in r.stdout.splitlines() if line]
        self.assertEqual(len(ids), 2, r.stdout)
        self.assertNotEqual(ids[0], ids[1])

    def test_task_dir_derives_from_tmpdir(self):
        env = {'CBC_TASK_DIR': '', 'TMPDIR': self.tmp}
        r = self.cli('run', '--name', 'tmpdir1', 'x', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        root = os.path.join(self.tmp, 'cbc-tasks-%d' % os.getuid())
        self.assertTrue(os.path.isdir(os.path.join(root, 'tmpdir1')),
                        'task dir should derive from TMPDIR')
        s = self.status('tmpdir1', env=env)
        self.assertEqual(self._state(s), 'done', s.stdout)


    def test_run_success_prints_only_result_text(self):
        r = self.cli('run', '--name', 'run1', 'do x')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '最终结果OK\n')
        self.assertEqual(r.stderr, '')
        self.assertNotIn('run1', r.stdout, 'tid must stay internal')
        self.assertNotIn('cbc: ok', r.stdout, 'check output must stay internal')
        self.assertNotIn('SECRET_THOUGHT', r.stdout)
        self.wait_state('run1', 'done')

    def test_run_failure_prints_error_text_exit1(self):
        self._write_out(ISERROR_JSON)
        r = self.cli('run', '--name', 'run2', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('400 model [nope] service info not found', r.stdout)
        self.assertEqual(r.stderr, '')

    def test_run_env_unready_prints_hint_block(self):
        empty = os.path.join(self.tmp, 'emptybin')
        os.makedirs(empty)
        r = self.cli('run', 'x', env={'CBC_BIN': '', 'PATH': empty})
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertEqual(r.stdout, '')
        self.assertIn('hint:', r.stderr)
        self.assertIn('CBC_BIN', r.stderr)

    def test_run_auto_extracts_token_when_env_unset(self):
        r = self.cli('run', '--name', 'auth1', 'x')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.env_file) as f:
            self.assertEqual(f.read().strip(), 'auto-token')
        self.assertTrue(os.path.exists(self.wb_log))

    def test_run_env_token_wins_no_extraction(self):
        r = self.cli('run', '--name', 'auth2', 'x',
                     env={'CODEBUDDY_AUTH_TOKEN': 'envtok'})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.env_file) as f:
            self.assertEqual(f.read().strip(), 'envtok')
        self.assertFalse(os.path.exists(self.wb_log))

    def test_auth_failure_surfaces_extractor_error(self):
        self._write_out(AUTHERR_JSON)
        r = self.cli('run', '--name', 'auth3', 'x', env={'FAKE_WB_FAIL': '1'})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('Authentication required', r.stdout)
        self.assertIn('wb-auth-token 提取失败', r.stdout)
        self.assertIn('no login state', r.stdout)
        self.assertIn('CODEBUDDY_AUTH_TOKEN', r.stdout)

    def test_auth_failure_after_extraction_appends_remedy(self):
        self._write_out(AUTHERR_JSON)
        r = self.cli('run', '--name', 'auth4', 'x')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('Authentication required', r.stdout)
        self.assertIn('CODEBUDDY_AUTH_TOKEN', r.stdout)
        self.assertNotIn('提取失败', r.stdout)

    def test_run_timeout_fails_quietly(self):
        self.set_sleep(60)
        r = self.cli('run', '--name', 'run4', 'x', '--timeout', '1')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('timeout', r.stdout)
        self.assertEqual(r.stderr, '')

    def test_run_args_and_stdin_passthrough(self):
        r = self.cli('run', '--name', 'run3', '--model', 'hy3', '-',
                     input='STDIN')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.args_file) as f:
            argv = f.read().splitlines()
        self.assertIn('--model', argv)
        self.assertIn('hy3', argv)
        with open(self.stdin_file) as f:
            self.assertEqual(f.read(), 'STDIN')

    def test_quality_flags_passthrough(self):
        r = self.cli('run', '--name', 'q1', '--effort', 'high',
                     '--fallback-model', 'hy3', '--add-dir', '/tmp/a',
                     '--add-dir', '/tmp/b', 'review this')
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = self.read_argv()
        for pair in (['--effort', 'high'], ['--fallback-model', 'hy3']):
            self.assertIn(pair[0], argv)
            self.assertIn(pair[1], argv)
        self.assertEqual(argv.count('--add-dir'), 1, argv)
        self.assertIn('/tmp/a', argv)
        self.assertIn('/tmp/b', argv)

    def test_quality_defaults(self):
        r = self.cli('run', '--name', 'q2', 'plain')
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = self.read_argv()
        self.assertEqual(argv[argv.index('--effort') + 1], 'max')
        for flag in ('--autocompact', '--max-turns', '--fallback-model',
                     '--add-dir'):
            self.assertNotIn(flag, argv)

    def test_removed_flags_rejected(self):
        for flag in ('--autocompact', '--max-turns'):
            r = self.cli('run', '--name', 'gone', flag, 'auto', 'x')
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn('unrecognized arguments', r.stderr)

    def test_child_env_scrubbed_of_harness_vars(self):
        r = self.cli('run', '--name', 'env1', 'x', env={
            'CODEBUDDY_HOST': 'workbuddy-desktop',
            'CODEBUDDY_SERVICE_PROXY_URL': 'http://127.0.0.1:1/x',
            'NODE_OPTIONS': '--require=/nonexistent/shim.cjs',
            'PYTHONPATH': '/nonexistent/shim',
            'BASH_ENV': '/nonexistent/shim.sh',
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        env = self.read_child_env()
        for scrubbed in ('CODEBUDDY_HOST', 'CODEBUDDY_SERVICE_PROXY_URL',
                         'NODE_OPTIONS', 'PYTHONPATH', 'BASH_ENV'):
            self.assertNotIn(scrubbed, env)
        self.assertEqual(env.get('CODEBUDDY_AUTH_TOKEN'), 'auto-token')
        self.assertIn('PATH', env)

    def test_child_env_pass_escape_hatch(self):
        r = self.cli('run', '--name', 'env2', 'x', env={
            'CBC_ENV_PASS': 'JAVA_HOME,GOPATH',
            'JAVA_HOME': '/opt/jdk',
            'GOPATH': '/tmp/gopath',
            'SECRET_UNRELATED': 'nope',
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        env = self.read_child_env()
        self.assertEqual(env.get('JAVA_HOME'), '/opt/jdk')
        self.assertEqual(env.get('GOPATH'), '/tmp/gopath')
        self.assertNotIn('SECRET_UNRELATED', env)


if __name__ == '__main__':
    unittest.main()
