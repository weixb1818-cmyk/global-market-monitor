import copy
import unittest
from scripts.verify_public import validate_publication


class TestPublicationEvidence(unittest.TestCase):
    def fixture(self, event='workflow_dispatch', schedule=None):
        ctx = {'event': event, 'schedule': schedule, 'run_url': 'https://github.com/example/actions/runs/1'}
        data = {'indicators': [None] * 17, 'generated_at': '2026-11-22T00:18:00+00:00',
                'macro': {'state': '有限风险提示', 'mode': 'limited'}, 'update_context': ctx}
        attempt = {'status': 'partial', 'update_context': copy.deepcopy(ctx)}
        expected = {'expected_at': data['generated_at'], 'run_url': ctx['run_url'],
                    'event': event, 'schedule': schedule}
        return data, attempt, expected

    def test_manual_success_is_never_schedule_proof(self):
        data, attempt, expected = self.fixture()
        result = validate_publication(data, attempt, **expected)
        self.assertTrue(result['data_updated'])
        self.assertFalse(result['native_daily_schedule_verified'])

    def test_only_matching_native_daily_run_is_schedule_proof(self):
        data, attempt, expected = self.fixture('schedule', '15 0 * * *')
        self.assertTrue(validate_publication(data, attempt, **expected)['native_daily_schedule_verified'])
        expected['schedule'] = '*/5 * * * *'
        with self.assertRaisesRegex(ValueError, 'cron'):
            validate_publication(data, attempt, **expected)

    def test_reject_false_trigger_and_old_run(self):
        data, attempt, expected = self.fixture()
        expected['event'] = 'schedule'
        with self.assertRaisesRegex(ValueError, 'GitHub event'):
            validate_publication(data, attempt, **expected)
        expected['event'] = 'workflow_dispatch'
        attempt['update_context']['run_url'] = 'https://github.com/example/actions/runs/old'
        with self.assertRaisesRegex(ValueError, 'earlier update'):
            validate_publication(data, attempt, **expected)

    def test_reject_mixed_snapshot_or_cdn_timestamp(self):
        data, attempt, expected = self.fixture()
        data['update_context']['run_url'] = 'old'
        with self.assertRaisesRegex(ValueError, 'different runs'):
            validate_publication(data, attempt, **expected)
        data['generated_at'] = '2026-11-21T00:18:00+00:00'
        with self.assertRaisesRegex(ValueError, 'earlier snapshot'):
            validate_publication(data, attempt, **expected)

    def test_retained_snapshot_is_not_successful_scheduled_update(self):
        data, attempt, expected = self.fixture('schedule', '15 0 * * *')
        data['update_context'] = {'event': 'workflow_dispatch', 'run_url': 'old'}
        attempt['status'] = 'failed'
        result = validate_publication(data, attempt, **expected, data_outcome='failure')
        self.assertFalse(result['native_daily_schedule_verified'])
        self.assertFalse(result['data_updated'])


if __name__ == '__main__':
    unittest.main()
