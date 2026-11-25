import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import local_trigger as timer
from scripts.schedule_audit import gate, report
from scripts.verify_public import validate_publication
from scripts.update_data import update_context


class LocalTimerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 25, 0, 15, tzinfo=timezone.utc)
        self.url = f'https://github.com/{timer.REPO}/actions/runs/1'
        self.healthy = {'status': 'ok', 'at': self.now.isoformat(), 'update_context': {'run_url': self.url}}
        self.done = [{'html_url': self.url, 'status': 'completed', 'conclusion': 'success'}]

    def decide(self, attempt=None, runs=None, state=None, verify=False, now=None):
        return timer.decision(now or self.now, '08:15', attempt or {}, runs or [], state, verify)

    def test_all_automatic_routes_skip_healthy_day(self):
        self.assertFalse(gate('schedule', '15 0 * * *', self.healthy, self.now))
        self.assertFalse(gate('workflow_dispatch', None, self.healthy, self.now, origin='host_cron'))
        self.assertEqual(self.decide(self.healthy, self.done), 'skip_healthy_published_day')
        self.assertTrue(gate('workflow_dispatch', None, self.healthy, self.now))
        self.assertTrue(gate('schedule', None, self.healthy, self.now, force=True))

    def test_partial_failed_old_future_or_invalid_are_not_healthy(self):
        for attempt in ({}, {'status': 'partial', 'at': self.now.isoformat()},
                        {'status': 'failed', 'at': self.now.isoformat()},
                        {'status': 'ok', 'at': 'bad'},
                        {'status': 'ok', 'at': (self.now-timedelta(days=1)).isoformat()},
                        {'status': 'ok', 'at': (self.now+timedelta(days=1)).isoformat()},
                        {'status': 'ok', 'at': '2026-11-25T08:15:00'}):
            with self.subTest(attempt=attempt):
                self.assertTrue(gate('schedule', '15 0 * * *', attempt, self.now))
                self.assertEqual(self.decide(attempt, self.done), 'dispatch')

    def test_failed_or_unconfirmed_deploy_does_not_suppress_retry(self):
        for conclusion in ('failure', 'cancelled', None):
            runs = [{'html_url': self.url, 'status': 'completed', 'conclusion': conclusion}]
            self.assertEqual(self.decide(self.healthy, runs), 'dispatch')
        self.assertEqual(self.decide(self.healthy), 'dispatch')

    def test_inflight_prevents_even_forced_duplicate(self):
        for status in timer.ACTIVE:
            self.assertEqual(self.decide(runs=[{'status': status}], verify=True), 'skip_workflow_active')

    def test_slot_bounds_and_once_per_slot(self):
        self.assertEqual(self.decide(now=self.now-timedelta(seconds=1)), 'skip_outside_slot_window')
        self.assertEqual(self.decide(now=self.now+timedelta(minutes=11)), 'skip_outside_slot_window')
        self.assertEqual(self.decide(state={'result': 'dispatch'}), 'skip_slot_already_attempted')
        self.assertEqual(self.decide(state={'result': 'dispatch'}, verify=True,
                                     now=self.now+timedelta(hours=4)), 'dispatch')

    def test_ambiguous_dispatch_persists_intent_and_does_not_blind_retry(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{}'
        with tempfile.TemporaryDirectory() as temp:
            argv = ['local_trigger.py', '--slot', '08:15', '--runtime-dir', temp]
            with patch('sys.argv', argv), patch.object(timer, 'decision', return_value='dispatch'), \
                 patch.object(timer, 'urlopen', return_value=Response()), \
                 patch.object(timer, 'gh_api', side_effect=[{'workflow_runs': []}, TimeoutError()]):
                with self.assertRaises(SystemExit): timer.main()
            states = list(Path(temp).glob('*.json'))
            self.assertEqual(len(states), 1)
            self.assertEqual(json.loads(states[0].read_text())['result'], 'dispatch')
            self.assertIn('trigger_error_or_ambiguous', (Path(temp)/'events.jsonl').read_text())

    def test_existing_auth_is_reused_without_token_on_command_line(self):
        with patch.object(timer.subprocess, 'run') as run:
            run.return_value.returncode = 0; run.return_value.stdout = ''
            timer.gh_api('repos/example/dispatches', {'inputs': {'origin': 'host_cron'}})
            args, kwargs = run.call_args
            self.assertEqual(args[0][0], '/usr/bin/gh')
            self.assertIn('--input', args[0]); self.assertNotIn('token', ' '.join(args[0]))
            self.assertEqual(json.loads(kwargs['input'])['inputs']['origin'], 'host_cron')
            run.return_value.returncode = 1
            with self.assertRaises(RuntimeError): timer.gh_api('repos/example')

    def test_origin_metadata_and_public_readback_remain_actual_dispatch(self):
        env = {'TRIGGER_EVENT': 'workflow_dispatch', 'TRIGGER_ORIGIN': 'host_cron',
               'TRIGGER_PLANNED_AT': '2026-11-25T08:15:00+08:00',
               'TRIGGER_REQUESTED_AT': '2026-11-25T08:15:01+08:00', 'TRIGGER_DISPATCH_ID': 'id'}
        with patch.dict('os.environ', env, clear=True): ctx = update_context()
        data = {'indicators': [None]*17, 'generated_at': 'time', 'macro': {'state': 'test'}, 'update_context': ctx}
        attempt = {'status': 'ok', 'update_context': ctx}
        result = validate_publication(data, attempt, event='workflow_dispatch', origin='host_cron',
                                      planned_at=env['TRIGGER_PLANNED_AT'], dispatch_id='id')
        self.assertFalse(result['native_daily_schedule_verified'])
        with self.assertRaisesRegex(ValueError, 'metadata mismatch'):
            validate_publication(data, attempt, dispatch_id='other')

    def test_diagnostic_dispatch_does_not_count_as_natural_scheduled_day(self):
        now = datetime(2026,11,25,5,tzinfo=timezone.utc)
        run = {'event':'workflow_dispatch','display_title':'host_timer_test | id', 'id':1,
               'html_url':self.url,'head_sha':'abc','created_at':'2026-11-25T04:00:00Z',
               'conclusion':'success','job_conclusions':{'update':'success','deploy':'success'}}
        result = report([run], now, days=1)
        self.assertEqual(result['observed_days'], 0)
        self.assertFalse(result['ten_days_update_deploy_success'])
        self.assertEqual(result['records'][0]['runs'][0]['trigger_origin'], 'host_timer_test')

class CronInstallationTests(unittest.TestCase):
    def test_preserve_other_jobs_and_install_exactly_once(self):
        from scripts.install_local_timer import render, without_block, BEGIN
        old = 'SHELL=/bin/bash\nCRON_TZ=Asia/Shanghai\n5 * * * * /some/unrelated/job\n'
        root = Path('/home/ubuntu/panel')
        first = render(old, root)
        self.assertEqual(render(first, root), first)
        self.assertEqual(without_block(first), old)
        self.assertEqual(first.count(BEGIN), 1)
        for slot in ('15 8 * * *', '45 8 * * *', '15 10 * * *'):
            self.assertIn(slot, first)
        self.assertEqual(render(first, root, remove=True), old)

    def test_broken_markers_fail_without_replacing_crontab(self):
        from scripts.install_local_timer import without_block, BEGIN
        with self.assertRaises(ValueError): without_block(BEGIN+'\n')
