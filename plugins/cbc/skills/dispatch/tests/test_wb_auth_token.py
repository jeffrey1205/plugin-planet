#!/usr/bin/env python3
"""Black-box tests for scripts/wb-auth-token (read-only login-state extractor)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), 'scripts', 'wb-auth-token')

# 信封 fixture：明文 "fixture.jwt.token"，
# key = base64(bytes(range(32)))，nonce = bytes(range(12))，
# 由移植源 workbuddy_checkin.py v3.1.7 的 _aes_gcm_encrypt 一次性生成后写死。
ATREST_KEY = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8='
ENVELOPE_FIXTURE = (
    'eyJzdWl0ZSI6MSwia2V5SWQiOiJjY2I2NzIxNjU1ZGFkZTNiIiwibm9uY2UiOiJBQUVD'
    'QXdRRkJnY0lDUW9MIiwiYXV0aFRhZyI6IkR0RVNlYW0wdjI3KzB2bDczZ2pMWXc9PSIs'
    'ImNpcGhlcnRleHQiOiJ1dy9lcG9uSVNDbGUxWFUvSndUdTJ2MD0ifQ=='
)


class WbAuthToken(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='wb-auth-token-test-')
        self.auth_dir = os.path.join(self.tmp, '.workbuddy', 'auth')
        os.makedirs(self.auth_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def _write_auth(self, access_token, expires_at=None):
        auth = {'accessToken': access_token, 'domain': 'www.codebuddy.cn'}
        if expires_at is not None:
            auth['expiresAt'] = expires_at
        path = os.path.join(self.auth_dir, 'workbuddy-desktop.info')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'auth': auth}, f)
        return path

    def run_script(self, **env):
        full_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                    'HOME': self.tmp}
        full_env.update(env)
        return subprocess.run([sys.executable, SCRIPT],
                              capture_output=True, text=True,
                              env=full_env, timeout=60)

    # -- cases ------------------------------------------------------------

    def test_plaintext_login_state(self):
        self._write_auth('tok_abc', expires_at=int(time.time()) + 3600)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'tok_abc')
        self.assertEqual(r.stderr, '')

    def test_encrypted_envelope_with_env_key(self):
        self._write_auth({'$wbEncrypted': 1, 'envelope': ENVELOPE_FIXTURE},
                         expires_at=int(time.time()) + 3600)
        r = self.run_script(WORKBUDDY_ATREST_KEY=ATREST_KEY)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'fixture.jwt.token')
        self.assertEqual(r.stderr, '')

    def test_encrypted_envelope_with_persisted_key_file(self):
        """密钥落盘（~/.workbuddy/scripts/atrest.key）时无需任何环境变量。"""
        key_dir = os.path.join(self.tmp, '.workbuddy', 'scripts')
        os.makedirs(key_dir)
        with open(os.path.join(key_dir, 'atrest.key'), 'w') as f:
            f.write(ATREST_KEY + '\n')
        self._write_auth({'$wbEncrypted': 1, 'envelope': ENVELOPE_FIXTURE},
                         expires_at=int(time.time()) + 3600)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'fixture.jwt.token')
        self.assertEqual(r.stderr, '')

    def test_foreign_key_file_is_skipped(self):
        """落盘的是别的密钥（keyId 不匹配）时不得误用，仍需报错退出。"""
        key_dir = os.path.join(self.tmp, '.workbuddy', 'scripts')
        os.makedirs(key_dir)
        with open(os.path.join(key_dir, 'atrest.key'), 'w') as f:
            f.write('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n')
        self._write_auth({'$wbEncrypted': 1, 'envelope': ENVELOPE_FIXTURE},
                         expires_at=int(time.time()) + 3600)
        r = self.run_script()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')
        self.assertNotEqual(r.stderr.strip(), '')

    def test_missing_login_state_fails_cleanly(self):
        shutil.rmtree(self.auth_dir)  # 干净 HOME：无任何登录态候选
        r = self.run_script()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')
        self.assertNotEqual(r.stderr.strip(), '')

    def test_expired_login_state_rejected(self):
        self._write_auth('tok_old', expires_at=int(time.time()) - 3600)
        r = self.run_script()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')
        self.assertIn('过期', r.stderr)


if __name__ == '__main__':
    unittest.main()
