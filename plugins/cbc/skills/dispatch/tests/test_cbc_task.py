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
printf '%s\\n' "$@" > "$FAKE_ARGS_FILE"
if [ -n "$FAKE_STDIN_FILE" ]; then cat > "$FAKE_STDIN_FILE"; fi
if [ -n "$FAKE_STDERR" ]; then printf '%s\\n' "$FAKE_STDERR" >&2; fi
if [ "$FAKE_MODE" = sleep ]; then sleep "${FAKE_SLEEP:-2}"; fi
cat "$FAKE_STDOUT_FILE"
exit "${FAKE_EXIT:-0}"
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


class CbcTaskCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='cbc-task-test-')
        self.tasks = os.path.join(self.tmp, 'tasks')
        self.fake = os.path.join(self.tmp, 'fake-cbc')
        with open(self.fake, 'w') as f:
            f.write(FAKE_CBC)
        os.chmod(self.fake, 0o755)
        self.args_file = os.path.join(self.tmp, 'argv.txt')
        self.out_file = os.path.join(self.tmp, 'cbc-out.txt')
        self.stdin_file = os.path.join(self.tmp, 'cbc-stdin.txt')
        self._write_out(SUCCESS_JSON)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def _write_out(self, content):
        with open(self.out_file, 'w') as f:
            f.write(content)

    def _env(self, **over):
        env = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'CBC_BIN': self.fake,
            'CBC_TASK_DIR': self.tasks,
            'FAKE_ARGS_FILE': self.args_file,
            'FAKE_STDOUT_FILE': self.out_file,
            'FAKE_STDIN_FILE': self.stdin_file,
            'FAKE_MODE': 'run',
            'FAKE_EXIT': '0',
        }
        env.update(over)
        return env

    def cli(self, *args, **kw):
        env = self._env(**kw.pop('env', {}))
        inp = kw.pop('input', None)
        return subprocess.run([sys.executable, SCRIPT, *args],
                              capture_output=True, text=True,
                              env=env, input=inp, timeout=60)

    def dispatch(self, *args, **kw):
        r = self.cli('dispatch', *args, **kw)
        tid = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ''
        return r, tid

    def status(self, tid):
        return self.cli('status', tid)

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

    def test_dispatch_returns_immediately_with_task_id(self):
        t0 = time.time()
        r, tid = self.dispatch('--name', 'quick', '回复两个字:成功',
                               env={'FAKE_MODE': 'sleep', 'FAKE_SLEEP': '3'})
        elapsed = time.time() - t0
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(elapsed, 2.5,
                        'dispatch must not wait for the task to finish')
        self.assertRegex(tid, r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
        s = self.status(tid)
        self.assertEqual(self._state(s), 'running', s.stdout)
        self.assertEqual(s.returncode, 0)
        self.wait_state(tid, 'done')

    def test_result_returns_final_text_only(self):
        r, tid = self.dispatch('--name', 'res1', 'do something')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'done')
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 0, rr.stderr)
        self.assertEqual(rr.stdout.strip(), '最终结果OK')
        self.assertNotIn('SECRET_THOUGHT', rr.stdout)
        with open(os.path.join(self.tasks, tid, 'result.json')) as f:
            meta = json.load(f)
        self.assertFalse(meta['is_error'])
        self.assertEqual(meta['model'], 'hy3')
        self.assertEqual(meta['duration_ms'], 1234)
        self.assertEqual(meta['num_turns'], 3)

    def test_args_passthrough(self):
        r, tid = self.dispatch('--name', 'args1', '--model', 'hy3',
                               'hello world')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'done')
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
        r2, tid2 = self.dispatch('--name', 'args2', 'plain')
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.wait_state(tid2, 'done')
        with open(self.args_file) as f:
            argv2 = f.read().splitlines()
        self.assertNotIn('--model', argv2)

    def test_nonzero_exit_marks_failed(self):
        self._write_out('cbc exploded\n')
        r, tid = self.dispatch('--name', 'bad1', 'x', env={'FAKE_EXIT': '1'})
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.wait_state(tid, 'failed')
        self.assertIn('exit 1', s.stdout)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 1)
        self.assertIn('exit 1', rr.stdout)

    def test_is_error_json_marks_failed_with_error_text(self):
        self._write_out(ISERROR_JSON)
        r, tid = self.dispatch('--name', 'bad2', 'x')
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.wait_state(tid, 'failed')
        self.assertIn('is_error', s.stdout)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 1)
        self.assertIn('400 model [nope]', rr.stdout)

    def test_garbage_output_marks_failed(self):
        self._write_out('not json at all\n')
        r, tid = self.dispatch('--name', 'bad3', 'x')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'failed')
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 1)

    def test_running_then_kill(self):
        r, tid = self.dispatch('--name', 'long1', 'x',
                               env={'FAKE_MODE': 'sleep', 'FAKE_SLEEP': '60'})
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.status(tid)
        self.assertEqual(self._state(s), 'running', s.stdout)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 2, rr.stdout + rr.stderr)
        k = self.cli('kill', tid)
        self.assertEqual(k.returncode, 0, k.stderr)
        self.wait_state(tid, 'failed', deadline=10)

    def test_timeout_kills_and_marks_failed(self):
        r, tid = self.dispatch('--name', 'to1', 'x', '--timeout', '1',
                               env={'FAKE_MODE': 'sleep', 'FAKE_SLEEP': '60'})
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.wait_state(tid, 'failed', deadline=15)
        self.assertIn('timeout', s.stdout)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 1)

    def test_duplicate_name_rejected(self):
        r1, _ = self.dispatch('--name', 'dup', 'x',
                              env={'FAKE_MODE': 'sleep', 'FAKE_SLEEP': '10'})
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2, _ = self.dispatch('--name', 'dup', 'y')
        self.assertEqual(r2.returncode, 3, r2.stdout + r2.stderr)
        self.assertIn('already exists', r2.stderr)
        self.cli('kill', 'dup')

    def test_unknown_task(self):
        r = self.cli('status', 'no-such-task')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not found', r.stderr)
        r = self.cli('result', 'no-such-task')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not found', r.stderr)

    def test_binary_not_found(self):
        empty = os.path.join(self.tmp, 'emptybin')
        os.makedirs(empty)
        r, _ = self.dispatch('x', env={'CBC_BIN': '', 'PATH': empty})
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn('CBC_BIN', r.stderr)

    def test_list_shows_done_task(self):
        r, tid = self.dispatch('--name', 'listed1', 'x')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'done')
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

    def test_stdin_prompt(self):
        text = 'STDIN_PROMPT 内容\n第二行'
        r, tid = self.dispatch('--name', 'stdin1', '-', input=text)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'done')
        with open(self.args_file) as f:
            argv = f.read().splitlines()
        self.assertIn('-p', argv)
        self.assertNotIn(text, argv, 'prompt must not go through argv')
        with open(os.path.join(self.tasks, tid, 'prompt.log')) as f:
            self.assertEqual(f.read(), text)
        with open(self.stdin_file) as f:
            self.assertEqual(f.read(), text)

    def test_stdin_prompt_large(self):
        big = 'A' * 150000
        r, tid = self.dispatch('--name', 'stdin-big', '-', input=big)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.wait_state(tid, 'done')
        with open(os.path.join(self.tasks, tid, 'prompt.log')) as f:
            self.assertEqual(len(f.read()), 150000)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 0, rr.stderr)

    def test_failed_task_surfaces_stderr_text(self):
        self._write_out('')
        r, tid = self.dispatch('--name', 'stderr1', 'x',
                               env={'FAKE_STDERR':
                                    '400 model [nope] service info not found'})
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.wait_state(tid, 'failed')
        self.assertIn('400 model [nope]', s.stdout)
        rr = self.cli('result', tid)
        self.assertEqual(rr.returncode, 1)
        self.assertIn('400 model [nope]', rr.stdout)

    def test_auto_names_are_unique(self):
        r1, t1 = self.dispatch('a')
        r2, t2 = self.dispatch('b')
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertNotEqual(t1, t2)
        self.wait_state(t1, 'done')
        self.wait_state(t2, 'done')

    def test_task_dir_derives_from_tmpdir(self):
        env = {'CBC_TASK_DIR': '', 'TMPDIR': self.tmp}
        r, tid = self.dispatch('x', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        root = os.path.join(self.tmp, 'cbc-tasks-%d' % os.getuid())
        self.assertTrue(os.path.isdir(os.path.join(root, tid)),
                        'task dir should derive from TMPDIR')
        end = time.time() + 15
        while True:
            s = self.cli('status', tid, env=env)
            if self._state(s) == 'done':
                break
            if time.time() > end:
                self.fail(f'never done: {s.stdout!r} {s.stderr!r}')
            time.sleep(0.15)


if __name__ == '__main__':
    unittest.main()
