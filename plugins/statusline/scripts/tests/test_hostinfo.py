#!/usr/bin/env python3
"""Host detection and settings.json helpers."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hostinfo


class Detect(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {'HOME': self._tmp}, clear=False)
        self._env.start()
        for key in ('CODEBUDDY_PLUGIN_ROOT', 'CODEBUDDY_CONFIG_DIR',
                    'CLAUDE_PLUGIN_ROOT', 'CLAUDE_CONFIG_DIR'):
            os.environ.pop(key, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_script_in_claude_cache(self):
        path = '/home/u/.claude/plugins/cache/plugin-planet/statusline/2.0.0/scripts/statusline.py'
        self.assertEqual(hostinfo.detect({}, path), hostinfo.CLAUDE)

    def test_script_in_codebuddy_cache(self):
        path = '/home/u/.codebuddy/plugins/cache/plugin-planet/statusline/2.0.0/scripts/statusline.py'
        self.assertEqual(hostinfo.detect({}, path), hostinfo.CODEBUDDY)

    def test_codebuddy_env(self):
        with mock.patch.dict(os.environ, {'CODEBUDDY_PLUGIN_ROOT': '/x'}):
            self.assertEqual(hostinfo.detect({}, '/plain/statusline.py'),
                             hostinfo.CODEBUDDY)

    def test_claude_env(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': self._tmp}):
            self.assertEqual(hostinfo.detect({}, '/plain/statusline.py'),
                             hostinfo.CLAUDE)

    def test_stdin_codebuddy_keys(self):
        self.assertEqual(hostinfo.detect({'permission_mode': 'default'}, '/p/s.py'),
                         hostinfo.CODEBUDDY)
        self.assertEqual(hostinfo.detect({'team': {'name': 'x'}}, '/p/s.py'),
                         hostinfo.CODEBUDDY)

    def test_stdin_claude_keys(self):
        self.assertEqual(hostinfo.detect({'effort': {'level': 'high'}}, '/p/s.py'),
                         hostinfo.CLAUDE)
        self.assertEqual(hostinfo.detect({'prompt_cache': {}}, '/p/s.py'),
                         hostinfo.CLAUDE)

    def test_only_claude_dir_exists(self):
        os.makedirs(os.path.join(self._tmp, '.claude'))
        self.assertEqual(hostinfo.detect({}, '/p/s.py'), hostinfo.CLAUDE)

    def test_defaults_to_codebuddy(self):
        self.assertEqual(hostinfo.detect({}, '/p/s.py'), hostinfo.CODEBUDDY)

    def test_config_root_honors_env(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/custom/claude'}):
            self.assertEqual(hostinfo.config_root(hostinfo.CLAUDE), '/custom/claude')
            self.assertEqual(hostinfo.settings_path(hostinfo.CLAUDE),
                             '/custom/claude/settings.json')
        with mock.patch.dict(os.environ, {'CODEBUDDY_CONFIG_DIR': '/custom/cb'}):
            self.assertEqual(hostinfo.data_dir(hostinfo.CODEBUDDY),
                             os.path.join('/custom/cb', 'plugins', 'data', 'statusline'))


class PluginCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_newest_version(self):
        root = os.path.join(self._tmp, 'plugins', 'cache', 'plugin-planet', 'statusline')
        for name in ('1.0.4', '2.0.0', '2.10.0'):
            os.makedirs(os.path.join(root, name))
        with mock.patch.dict(os.environ, {'CODEBUDDY_CONFIG_DIR': self._tmp}):
            newest = hostinfo.newest_plugin_root(hostinfo.CODEBUDDY)
        self.assertTrue(newest.endswith('2.10.0'), newest)

    def test_version_key_sorts_numerically(self):
        self.assertGreater(hostinfo._version_key('2.10.0'),
                           hostinfo._version_key('2.9.9'))
        self.assertLess(hostinfo._version_key('dev'),
                        hostinfo._version_key('1.0.0'))

    def test_missing_root(self):
        with mock.patch.dict(os.environ, {'CODEBUDDY_CONFIG_DIR': self._tmp}):
            self.assertEqual(hostinfo.newest_plugin_root(hostinfo.CODEBUDDY), '')


class SettingsHelpers(unittest.TestCase):
    def test_command_target_quoted(self):
        command = '"C:/Program Files/Python/python.exe" "C:/a b/statusline.py"'
        self.assertEqual(hostinfo.command_target(command), 'C:/a b/statusline.py')

    def test_command_target_plain(self):
        self.assertEqual(hostinfo.command_target('python3 /x/statusline.py'),
                         '/x/statusline.py')

    def test_command_target_empty(self):
        self.assertEqual(hostinfo.command_target(''), '')
        self.assertEqual(hostinfo.command_target(None), '')

    def test_same_target(self):
        self.assertTrue(hostinfo.same_target('python3 /x/statusline.py', '/x/statusline.py'))
        self.assertFalse(hostinfo.same_target('python3 /x/other.py', '/x/statusline.py'))

    def test_build_command_quotes_both_paths(self):
        command = hostinfo.build_command('/usr/bin/python3', '/x/statusline.py')
        self.assertEqual(command, '"/usr/bin/python3" "/x/statusline.py"')

    def test_settings_round_trip(self):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, 'settings.json')
            hostinfo.write_settings(path, {'a': 1, 'statusLine': {'command': 'x'}})
            self.assertEqual(hostinfo.load_settings(path)['a'], 1)
            with open(path, 'r', encoding='utf-8') as handle:
                self.assertTrue(handle.read().endswith('\n'))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_load_missing_file(self):
        self.assertEqual(hostinfo.load_settings('/nonexistent/settings.json'), {})

    def test_load_bad_json_exits(self):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, 'settings.json')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('{oops')
            with self.assertRaises(SystemExit):
                hostinfo.load_settings(path)
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
