import unittest
import json
from unittest.mock import patch
from scripts import analyze_macro as analysis
from datetime import datetime,timezone,timedelta
from scripts.analyze_macro import outcome
from scripts.schedule_audit import gate,report

class ReviewTests(unittest.TestCase):
    def test_returns_only_use_first_complete_close_after_signal(self):
        # These synthetic rows live only in a unit test, never in market JSON.
        rows=[{'date':f'2026-11-{i:02d}','value':v} for i,v in [(1,100),(2,80),(3,90),(4,70)]]
        r=outcome(rows,datetime(2026,11,2,23,tzinfo=timezone.utc),'btc',1)
        self.assertEqual(r['entry_date'],'2026-11-02')
        self.assertEqual(r['end_date'],'2026-11-03')
        self.assertAlmostEqual(r['return_pct'],12.5)
        self.assertEqual(outcome(rows,datetime(2026,11,5,tzinfo=timezone.utc),'btc',5)['status'],'pending')

    def test_missing_future_window_never_zero_return(self):
        r=outcome([],datetime.now(timezone.utc),'sp500',20)
        self.assertEqual(r['status'],'pending');self.assertNotIn('return_pct',r)

    def test_mdd_is_peak_to_trough_and_distinct_from_entry_loss(self):
        rows=[{'date':f'2026-11-{d:02d}','value':v} for d,v in [(1,100),(2,120),(3,108)]]
        r=outcome(rows,datetime(2026,11,1,tzinfo=timezone.utc),'btc',2)
        self.assertAlmostEqual(r['max_close_drawdown_pct'],-10)
        self.assertEqual(r['max_adverse_from_entry_pct'],0)

    def test_backup_skips_only_healthy_current_attempt(self):
        now=datetime(2026,11,23,2,15,tzinfo=timezone.utc)
        self.assertFalse(gate('schedule','15 2 * * *',{'status':'ok','at':'2026-11-23T00:20:00+00:00'},now))
        for a in [{},{'status':'partial','at':now.isoformat()},{'status':'failed','at':now.isoformat()},{'status':'ok','at':'2026-11-22T00:20:00+00:00'}]:
            self.assertTrue(gate('schedule','45 0 * * *',a,now))
        self.assertTrue(gate('schedule','15 0 * * *',{'status':'ok','at':now.isoformat()},now))

    def test_ten_day_report_does_not_fabricate_operating_days(self):
        now=datetime(2026,11,23,12,tzinfo=timezone.utc)
        r=report([],now);self.assertFalse(r['ten_days_observed']);self.assertEqual(len(r['records']),10)
        self.assertEqual(r['records'][-1]['status'],'no_observed_run')
        self.assertTrue(any(x['status']=='not_in_operation' for x in r['records']))

    def test_missing_expected_close_is_invalid_not_a_longer_horizon(self):
        rows=[{'date':'2026-11-02','value':100},{'date':'2026-11-04','value':95}]
        result=outcome(rows,datetime(2026,11,2,tzinfo=timezone.utc),'sp500',1)
        self.assertEqual(result['status'],'invalid')
        self.assertIn('missing expected',result['reason'])

    def test_archived_failed_attempt_on_next_day_blocks_old_ok_snapshot(self):
        snap={'generated_at':'2026-11-20T23:00:00+00:00','indicators':[{'id':k,'name':k,'value':1,'change_20':0,'status':'ok','as_of':'2026-11-20','calendar':'bond'} for k in ['dxy','real10y','us2y','hy','vix']]}
        def git(args,**kwargs):
            if args[1]=='log':
                self.assertIn('data/last_attempt.json',args);return 'a\nb\n'
            if '--format=%cI' in args:return '2026-11-20T23:10:00+00:00' if 'a' in args else '2026-11-21T23:10:00+00:00'
            if args[-1].endswith(':data/snapshot.json'):return json.dumps(snap).encode()
            return json.dumps({'status':'failed' if args[-1].startswith('b:') else 'ok','at':'2026-11-21T23:00:00+00:00'}).encode()
        with patch.object(analysis.subprocess,'check_output',side_effect=git):r=analysis.archived()
        self.assertEqual(len(r),2)
        self.assertEqual(r[1]['macro']['mode'],'insufficient')
        self.assertTrue(all(s=='error' for s in r[1]['input_statuses'].values()))
