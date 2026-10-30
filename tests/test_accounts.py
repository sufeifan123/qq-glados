"""离线验证账号配置和请求隔离；不发送真实签到或通知。"""
import importlib.util
import io
import os
from pathlib import Path
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


# 仅在本地缺少运行依赖时使用替身，所有测试均拦截 HTTP。
try:
    import requests
except ModuleNotFoundError:
    sys.modules['requests'] = types.SimpleNamespace(get=Mock(), post=Mock())

spec = importlib.util.spec_from_file_location('checkin', Path(__file__).resolve().parents[1] / 'checkin.py')
checkin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkin)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()

    def tearDown(self):
        self.redirect.__exit__(None, None, None)
        self.environment.stop()

    def test_legacy_formats_and_empty_new_mappings(self):
        for raw in ('first#second', '["first", {"cookie": "second"}]'):
            os.environ.update(GLADOS_COOKIE=raw, GLADOS_COOKIE_MAIN='')
            accounts = checkin.get_accounts()
            self.assertEqual([a['cookie'] for a in accounts], ['first', 'second'])
            self.assertEqual([a['id'] for a in accounts], ['LEGACY_1', 'LEGACY_2'])

    def test_independent_accounts_override_legacy_and_keep_identity(self):
        os.environ.update(GLADOS_COOKIE='old', GLADOS_COOKIE_MAIN='main-secret',
                          GLADOS_COOKIE_BACKUP='backup-secret', GLADOS_NAME_BACKUP='备用账号')
        before = {a['id']: a for a in checkin.get_accounts()}
        self.assertEqual(set(before), {'MAIN', 'BACKUP'})
        os.environ['GLADOS_COOKIE_BACKUP'] = 'updated-secret'
        after = {a['id']: a for a in checkin.get_accounts()}
        self.assertEqual(before['MAIN'], after['MAIN'])
        self.assertEqual(after['BACKUP']['name'], '备用账号')
        del os.environ['GLADOS_COOKIE_MAIN']
        self.assertEqual(checkin.get_accounts()[0]['id'], 'BACKUP')
        self.assertNotIn('updated-secret', self.output.getvalue())

    def test_name_default_and_user_agent_fallbacks(self):
        os.environ.update(GLADOS_COOKIE_MAIN='cookie', GLADOS_USER_AGENT='global-agent')
        account = checkin.get_accounts()[0]
        self.assertEqual(account['name'], 'MAIN')
        self.assertEqual(checkin.get_browser_headers(account['user_agent'])['User-Agent'], 'global-agent')
        self.assertEqual(checkin.get_browser_headers('private-agent')['User-Agent'], 'private-agent')
        del os.environ['GLADOS_USER_AGENT']
        self.assertEqual(checkin.get_browser_headers()['User-Agent'], checkin.DEFAULT_USER_AGENT)

    def test_requests_use_matching_cookie_and_user_agent(self):
        response = Mock(status_code=200)
        response.json.return_value = {'code': 0}
        with patch.object(checkin.requests, 'post', return_value=response) as post:
            for name in ('main', 'backup'):
                checkin.GLaDOS(f'gld:sess={name}; gld:sess.sig=sig', f'{name}-agent').checkin()
            for call, name in zip(post.call_args_list, ('main', 'backup')):
                self.assertEqual(call.kwargs['headers']['User-Agent'], f'{name}-agent')
                self.assertEqual(call.kwargs['headers']['Cookie'], f'gld:sess={name}; gld:sess.sig=sig')

    def test_invalid_new_configuration_does_not_fall_back(self):
        for raw in ('{"bad": true}', '["first", "second"]', 'first#second'):
            with self.subTest(raw=raw):
                os.environ.update(GLADOS_COOKIE='old', GLADOS_COOKIE_MAIN=raw)
                self.assertEqual(checkin.main(), 1)

    def test_removing_last_independent_account_restores_legacy(self):
        os.environ.update(GLADOS_COOKIE='old', GLADOS_COOKIE_MAIN='new')
        self.assertEqual(checkin.get_accounts()[0]['id'], 'MAIN')
        del os.environ['GLADOS_COOKIE_MAIN']
        self.assertEqual(checkin.get_accounts()[0]['cookie'], 'old')

    def test_failed_account_does_not_stop_next_account(self):
        os.environ.update(GLADOS_COOKIE_MAIN='main-secret', GLADOS_COOKIE_BACKUP='backup-secret')
        with patch.object(checkin, 'GLaDOS') as client, patch.object(checkin.time, 'sleep'), patch.object(checkin, 'wechat_push') as push:
            bad, good = Mock(), Mock()
            for instance in (bad, good):
                instance.email = 'account@example.com'
                instance.points = '10'
                instance.left_days = '20'
            bad.checkin.return_value = {'code': 1, 'message': 'expired'}
            good.checkin.return_value = {'code': 0}
            client.side_effect = [bad, good]
            self.assertEqual(checkin.main(), 1)
            good.checkin.assert_called_once()
            success, total, results = push.call_args.args
            self.assertEqual((success, total), (1, 2))
            self.assertEqual(results[0]['label'], 'BACKUP [BACKUP]')
            self.assertFalse(results[0]['success'])
            self.assertTrue(results[1]['success'])

    def test_wechat_includes_identity_and_failure(self):
        response = Mock()
        response.json.return_value = {'errcode': 0}
        with patch.multiple(checkin, WECHAT_APPID='app', WECHAT_APPSECRET='secret', WECHAT_TEMPLATE_ID='template', WECHAT_OPENID='openid'), patch.object(checkin, 'get_wechat_access_token', return_value='token'), patch.object(checkin.requests, 'post', return_value=response) as post:
            self.assertTrue(checkin.wechat_push(0, 1, [{'label': '备用账号 [BACKUP]', 'points': '?', 'days': '?', 'success': False}]))
            stats = post.call_args.kwargs['json']['data']['keyword2']['value']
            self.assertIn('备用账号 [BACKUP]', stats)
            self.assertIn('失败', stats)


if __name__ == '__main__':
    unittest.main()
