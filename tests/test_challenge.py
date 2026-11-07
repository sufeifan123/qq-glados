"""新签到协议回归测试：全部 HTTP 和等待均被拦截。"""
import hashlib
import unittest
from unittest.mock import Mock, patch

from test_accounts import checkin


class ChallengeTests(unittest.TestCase):
    def response(self, payload, status=200):
        return Mock(status_code=status, json=Mock(return_value=payload))

    def client(self):
        return checkin.GLaDOS('gld:sess=test; gld:sess.sig=test', 'test-agent')

    def test_proof_payload_and_wait_are_preserved(self):
        nonce = 'nonce-中文'
        with patch.object(checkin.requests, 'get', return_value=self.response({'code': 0, 'nonce': nonce})), patch.object(checkin.requests, 'post', return_value=self.response({'code': 0})) as post, patch.object(checkin.time, 'sleep') as sleep:
            self.assertEqual(self.client().checkin(), {'code': 0})
            sleep.assert_called_once_with(2.7)
            post.assert_called_once()
            self.assertEqual(post.call_args.args[0], checkin.DOMAINS[0] + '/api/user/checkin')
            self.assertEqual(post.call_args.kwargs['json'], {
                'token': 'glados.cloud', 'nonce': nonce,
                'proof': hashlib.sha256((nonce + '.glados-observe-v1').encode()).hexdigest(),
            })

    def test_challenge_fallback_pins_submission_to_issuing_domain(self):
        with patch.object(checkin.requests, 'get', side_effect=[self.response({}, 503), self.response({'code': 0, 'nonce': 'fresh'})]), patch.object(checkin.requests, 'post', return_value=self.response({}, 503)) as post, patch.object(checkin.time, 'sleep'):
            self.assertIsNone(self.client().checkin())
            post.assert_called_once()
            self.assertEqual(post.call_args.args[0], checkin.DOMAINS[1] + '/api/user/checkin')
            self.assertEqual(post.call_args.kwargs['json']['token'], 'glados.rocks')

    def test_invalid_challenges_never_submit(self):
        for payload in (None, [], {}, {'code': 4}, {'code': 0, 'nonce': ''}, {'code': 0, 'nonce': 1}, {'code': 0, 'nonce': 'n' * 4097}, *({'code': 0, 'nonce': 'n', 'ttl': ttl} for ttl in (None, True, '300000', -1, 2700, float('nan'), float('inf')))):
            with self.subTest(payload=payload), patch.object(checkin.requests, 'get', return_value=self.response(payload)), patch.object(checkin.requests, 'post') as post, patch.object(checkin.time, 'sleep') as sleep:
                result = self.client().checkin()
                self.assertFalse(checkin.is_normal_checkin_result(result))
                post.assert_not_called()
                sleep.assert_not_called()

    def test_expired_challenge_never_submits(self):
        with patch.object(checkin.requests, 'get', return_value=self.response({'code': 0, 'nonce': 'n', 'ttl': 3000})), patch.object(checkin.requests, 'post') as post, patch.object(checkin.time, 'sleep'), patch.object(checkin.time, 'monotonic', side_effect=[10, 13]):
            self.assertIn('过期', self.client().checkin()['message'])
            post.assert_not_called()

    def test_each_attempt_fetches_a_fresh_nonce(self):
        with patch.object(checkin.requests, 'get', side_effect=[self.response({'code': 0, 'nonce': 'first'}), self.response({'code': 0, 'nonce': 'second'})]) as get, patch.object(checkin.requests, 'post', side_effect=[self.response({}, 503), self.response({'code': 0})]) as post, patch.object(checkin.time, 'sleep'):
            client = self.client()
            client.checkin()
            client.checkin()
            self.assertEqual(get.call_count, 2)
            self.assertEqual([c.kwargs['json']['nonce'] for c in post.call_args_list], ['first', 'second'])

    def test_auth_rejection_stops_domain_fallback(self):
        for status in (401, 403):
            with self.subTest(status=status), patch.object(checkin.requests, 'get', return_value=self.response({}, status)) as get, patch.object(checkin.requests, 'post') as post:
                self.assertTrue(self.client().checkin()['stop_retry'])
                get.assert_called_once()
                post.assert_not_called()

    def test_one_point_and_repeats_are_not_retried_as_failures(self):
        for message in ('Checkin! Got 1 Points', 'Checkin Repeats! Please Try Tomorrow'):
            self.assertTrue(checkin.is_normal_checkin_result({'message': message}))


if __name__ == '__main__':
    unittest.main()
