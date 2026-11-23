import unittest
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
