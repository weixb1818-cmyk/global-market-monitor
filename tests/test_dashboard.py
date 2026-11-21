import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from scripts import update_data as u

T = u.CONFIG['thresholds']
ITEMS = {x['id']:x for x in u.CONFIG['indicators']}
NOW = datetime(2026, 11, 20, 23, 30, tzinfo=timezone.utc)


def cards(dxy=0, real=0, two=0, hy=0, vix=0, hynow=300, vixnow=15):
    changes={'dxy':dxy,'real10y':real,'us2y':two,'hy':hy,'vix':vix}
    return {k:{'name':ITEMS[k]['name'],'value':hynow if k=='hy' else vixnow if k=='vix' else 1,'change_20':v,'status':'ok'} for k,v in changes.items()}

class TestMathAndDefinitions(unittest.TestCase):
    def test_exact_17(self):
        self.assertEqual(len(ITEMS), 17)
        self.assertEqual(ITEMS['usdcnh']['symbol'],'USD/CNH')
        self.assertEqual(ITEMS['copper']['unit'],'USD/lb')
        self.assertEqual(ITEMS['spread10y2y']['symbol'],'T10Y2Y')

    def test_spread_and_yield_basis_points(self):
        p=lambda v: [{'date': '2026-11-19','value':v}]
        plus=u.calculate(ITEMS['spread10y2y'],p(0.30),'test',None,NOW,T)
        minus=u.calculate(ITEMS['spread10y2y'],p(-0.50),'test',None,NOW,T)
        hy=u.calculate(ITEMS['hy'],p(3.20),'test',None,NOW,T)
        self.assertAlmostEqual(plus['value'],30)
        self.assertAlmostEqual(minus['value'],-50)
        self.assertAlmostEqual(hy['value'],320)
        p2=[{'date':'2026-11-18','value':4.00},{'date':'2026-11-19','value':4.25}]
        self.assertAlmostEqual(u.calculate(ITEMS['us10y'],p2,'test',None,NOW,T)['change_1'],25)

    def test_20_periods_not_20_days(self):
        start=date(2026,10,1)
        points=[{'date':(start+timedelta(days=2*i)).isoformat(),'value':100+i} for i in range(21)]
        out=u.calculate(ITEMS['dxy'],points,'test',None,NOW,T)
        self.assertAlmostEqual(out['change_20'],20)
        self.assertAlmostEqual(out['change_1'],(120/119-1)*100)
        self.assertIsNone(u.calculate(ITEMS['dxy'],points[:20],'test',None,NOW,T)['change_20'])

    def test_fx_direction_and_inversion_text(self):
        for name, target in [('usdcnh','离岸人民币'),('usdjpy','日元')]:
            x={**ITEMS[name], 'value':7,'change_20':2,'status':'ok'}
            self.assertIn('美元相对'+target+'升值',u.interpret(x,T))
            x['change_20']=-2
            self.assertIn('美元相对'+target+'贬值',u.interpret(x,T))
        x={**ITEMS['spread10y2y'],'value':10,'change_20':30,'status':'ok'}
        self.assertIn('正利差',u.interpret(x,T)); self.assertIn('变陡',u.interpret(x,T))
        self.assertNotIn('经济复苏',u.interpret(x,T))

    def test_weekends_and_thanksgiving(self):
        self.assertEqual(u.market_sessions(date(2026,11,25),date(2026,11,29),'nyse'),1)
        self.assertEqual(u.market_sessions(date(2026,11,25),date(2026,11,29),'bond'),1)
        self.assertFalse(u.is_stale('2026-11-25','nyse',datetime(2026,11,29,23,tzinfo=timezone.utc),T))

    def test_crypto_boundary(self):
        self.assertFalse(u.is_stale('2026-11-19','crypto',datetime(2026,11,21,11,tzinfo=timezone.utc),T))
        self.assertTrue(u.is_stale('2026-11-19','crypto',datetime(2026,11,21,13,tzinfo=timezone.utc),T))

    def test_reject_bad_values(self):
        with self.assertRaises(ValueError): u.observations([{'date':'2026-01-01','value':'NaN'}])
        with self.assertRaises(ValueError): u.observations([{'date':'not-a-date','value':1}])

class TestRules(unittest.TestCase):
    def test_tight(self): self.assertEqual(u.classify(cards(dxy=1.5,real=20),T)['state'],'金融条件趋紧')
    def test_easing(self): self.assertEqual(u.classify(cards(dxy=-1.5,real=-20),T)['state'],'温和宽松')
    def test_high_level_disqualifies_easing(self): self.assertNotEqual(u.classify(cards(dxy=-1.5,real=-20,hynow=450),T)['state'],'温和宽松')
    def test_stress_priority(self): self.assertEqual(u.classify(cards(dxy=-1.5,real=-20,hy=40,vix=5),T)['state'],'金融压力扩散')
    def test_growth_concern(self): self.assertEqual(u.classify(cards(two=-40,hy=30),T)['state'],'增长担忧定价')
    def test_missing_or_stale_blocks_state(self):
        c=cards(dxy=2,real=20); c['hy']['change_20']=None
        self.assertEqual(u.classify(c,T)['state'],'数据不足：暂不判断')
        c=cards(dxy=2,real=20); c['hy']['status']='stale'
        self.assertEqual(u.classify(c,T)['state'],'数据不足：暂不判断')
    def test_does_not_label_high_but_falling_as_expanding(self):
        self.assertNotEqual(u.classify(cards(hy=-40,vix=-5,hynow=600,vixnow=35),T)['state'],'金融压力扩散')

class TestDataSafety(unittest.TestCase):
    def test_total_failure_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'data').mkdir()
            old={'indicators':[],'original':'keep'}
            (root/'data'/'snapshot.json').write_text(json.dumps(old))
            (root/'data'/'history.json').write_text('{"series": {}}')
            with patch.object(u,'ROOT',root),patch.object(u,'fetch',side_effect=ValueError('fail')):
                self.assertFalse(u.run(NOW))
            self.assertEqual(json.loads((root/'data'/'snapshot.json').read_text()),old)
            self.assertEqual(json.loads((root/'data'/'last_attempt.json').read_text())['status'],'failed')

    def test_auxiliary_success_does_not_hide_total_visible_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();old={'indicators':[],'original':'keep'}
            (root/'data'/'snapshot.json').write_text(json.dumps(old))
            (root/'data'/'history.json').write_text('{"series": {}}')
            def only_aux(item, now):
                if item['id']=='aux3m':return [{'date':'2026-11-19','value':4.0}],'test auxiliary'
                raise ValueError('visible source unavailable')
            with patch.object(u,'ROOT',root),patch.object(u,'fetch',side_effect=only_aux):
                self.assertFalse(u.run(NOW))
            self.assertEqual(json.loads((root/'data'/'snapshot.json').read_text()),old)

    def test_corrupt_existing_file_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'data').mkdir(); snap=root/'data'/'snapshot.json'; snap.write_text('corrupt')
            with patch.object(u,'ROOT',root):
                with self.assertRaises(ValueError): u.run(NOW)
            self.assertEqual(snap.read_text(),'corrupt')

    def test_twelve_data_enforces_offshore_symbol_and_completed_day(self):
        payload={'meta':{'symbol':'USD/CNH','exchange_timezone':'UTC'},'values':[{'datetime':'2026-11-20','close':'7.1'},{'datetime':'2026-11-19','close':'7.0'}]}
        with patch.dict('os.environ',{'TWELVE_DATA_API_KEY':'test-key'}), patch.object(u,'request_json',return_value=payload):
            rows,_=u.twelve('USD/CNH',datetime(2026,11,20,17,tzinfo=timezone.utc))
        self.assertEqual(rows,[{'date':'2026-11-19','value':7.0}])
        payload['meta']['symbol']='USD/CNY'
        with patch.dict('os.environ',{'TWELVE_DATA_API_KEY':'test-key'}), patch.object(u,'request_json',return_value=payload):
            with self.assertRaises(ValueError): u.twelve('USD/CNH',NOW)

    def test_utc_daily_samples_ignore_intraday(self):
        sample={'prices':[[1795046400000,100],[1795132800000,110],[1795136400000,999]]}
        with patch.object(u,'request_json',return_value=sample):
            rows,_=u.coingecko('bitcoin',datetime(2026,11,21,tzinfo=timezone.utc))
        self.assertEqual([r['value'] for r in rows],[100,110])
        self.assertEqual(rows[-1]['date'],(datetime.fromtimestamp(1795132800,timezone.utc).date()-timedelta(days=1)).isoformat())



class TestLimitedRisks(unittest.TestCase):
    def missing_dxy(self, **kw):
        c=cards(**kw);c['dxy'].update(value=None,change_20=None,status='missing')
        return c
    def test_dxy_missing_keeps_limited_signals(self):
        m=u.classify(self.missing_dxy(vix=5,vixnow=28),T)
        self.assertEqual(m['state'],'有限风险提示');self.assertEqual(m['mode'],'limited')
        self.assertFalse(m['complete']);self.assertIn('DXY',m['uncertainty'])
        self.assertIn('波动率上升',m['reason'])
    def test_missing_dxy_never_labels_easing(self):
        m=u.classify(self.missing_dxy(real=-30),T)
        self.assertEqual(m['mode'],'limited');self.assertNotIn('温和宽松',m['state'])
    def test_limited_joint_stress(self):
        m=u.classify(self.missing_dxy(hy=40,vix=5),T)
        self.assertIn('共同上升',m['reason']);self.assertEqual(m['mode'],'limited')
    def test_limited_growth_concern(self):
        self.assertIn('增长担忧',u.classify(self.missing_dxy(two=-40,hy=30),T)['reason'])
    def test_other_missing_blocks_limited(self):
        c=self.missing_dxy();c['real10y']['change_20']=None
        self.assertEqual(u.classify(c,T)['mode'],'insufficient')
    def test_high_vix_even_when_flat_and_credit_stable(self):
        m=u.classify(cards(vix=0,hy=0,vixnow=25),T)
        self.assertEqual(m['risk_alerts'][0]['id'],'vix')
        self.assertIn('较高',m['risk_alerts'][0]['message'])
        self.assertNotEqual(m['state'],'金融压力扩散')
    def test_high_but_falling_is_still_high_not_expanding(self):
        m=u.classify(cards(vix=-8,hy=-50,vixnow=30,hynow=500),T)
        self.assertEqual(len(m['risk_alerts']),2)
        self.assertNotEqual(m['state'],'金融压力扩散')
    def test_stale_vix_level_is_not_current_warning(self):
        c=cards(vixnow=30);c['vix']['status']='stale'
        m=u.classify(c,T)
        self.assertEqual(m['risk_alerts'],[]);self.assertEqual(m['mode'],'insufficient')
    def test_high_level_valid_even_without_20_points(self):
        c=cards(vixnow=30);c['vix']['change_20']=None
        m=u.classify(c,T)
        self.assertEqual(m['mode'],'insufficient');self.assertEqual(m['risk_alerts'][0]['id'],'vix')
    def test_threshold_boundaries_and_priority(self):
        self.assertEqual(u.classify(cards(dxy=1,real=15),T)['state'],'金融条件趋紧')
        self.assertEqual(u.classify(cards(dxy=-1,real=-15,hy=25,vix=3),T)['state'],'金融压力扩散')
    def test_signal_dates_remain_independent(self):
        c=cards(dxy=2,real=20)
        for i,k in enumerate(c):c[k]['as_of']=f'2026-11-{14+i:02d}'
        m=u.classify(c,T)
        self.assertNotEqual(m['signal_dates']['hy'],m['signal_dates']['vix'])
        self.assertIn(c['vix']['as_of'],m['signals'][-1])
        self.assertIn('日期跨度',m['uncertainty'])

class TestDatesAndSpreadAlignment(unittest.TestCase):
    def test_good_friday_bonds_closed_fx_open(self):
        self.assertEqual(u.market_sessions(date(2026,4,2),date(2026,4,3),'bond'),0)
        self.assertEqual(u.market_sessions(date(2026,4,2),date(2026,4,3),'forex'),1)
    def test_veterans_day_bonds_closed_equities_open(self):
        self.assertEqual(u.market_sessions(date(2026,11,10),date(2026,11,11),'bond'),0)
        self.assertEqual(u.market_sessions(date(2026,11,10),date(2026,11,11),'nyse'),1)
    def test_three_expected_sessions_are_stale(self):
        self.assertTrue(u.is_stale('2026-11-25','nyse',datetime(2026,12,1,23,tzinfo=timezone.utc),T))
    def test_weekend_does_not_add_sessions(self):
        self.assertEqual(u.market_sessions(date(2026,11,20),date(2026,11,22),'nyse'),0)
    def spread_cards(self,value=30):
        return {'spread10y2y':{'as_of':'2026-11-19','value':value},'spread10y3m':{'as_of':None,'value':None}}
    def test_never_subtract_yields_across_dates(self):
        c=self.spread_cards();series={'us10y':[{'date':'2026-11-19','value':4.3}],'us2y':[{'date':'2026-11-18','value':4.0}]}
        checks=u.compare_spreads(c,series,T)
        self.assertEqual(checks[0]['status'],'not_comparable');self.assertNotIn('warning',c['spread10y2y'])
    def test_same_date_positive_and_negative_spread(self):
        for long,short,expected in [(4.3,4.0,30),(4.0,4.5,-50)]:
            c=self.spread_cards(expected);series={'us10y':[{'date':'2026-11-19','value':long}],'us2y':[{'date':'2026-11-19','value':short}]}
            self.assertEqual(u.compare_spreads(c,series,T)[0]['status'],'ok')
            self.assertEqual(c['spread10y2y']['value'],expected)
    def test_spread_mismatch_warns_but_keeps_official(self):
        c=self.spread_cards(40);series={'us10y':[{'date':'2026-11-19','value':4.3}],'us2y':[{'date':'2026-11-19','value':4.0}]}
        self.assertEqual(u.compare_spreads(c,series,T)[0]['status'],'warning')
        self.assertEqual(c['spread10y2y']['value'],40)
    def test_curve_drivers_require_common_endpoints(self):
        c={'spread10y2y':{'as_of':'2026-11-20','value':30,'change_20':30,'status':'ok','interpretation':'当前为正利差，曲线变陡'},'spread10y3m':{'status':'missing','change_20':None}}
        curve=[{'date':(date(2026,10,31)+timedelta(days=i)).isoformat(),'value':i} for i in range(21)]
        series={'spread10y2y':curve,'us10y':[{'date':'2026-11-19','value':4}],'us2y':[{'date':'2026-11-20','value':3}]}
        u.curve_drivers(c,series,T)
        self.assertNotIn('驱动',c['spread10y2y']['interpretation'])

class TestLicensedDxyAdapter(unittest.TestCase):
    def test_no_key_is_not_a_free_price(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'授权'):u.barchart_dxy(ITEMS['dxy'],NOW)
    def test_reject_futures_instead_of_cash(self):
        payload={'status':{'code':200},'results':[{'symbol':'DXZ26','name':'U.S. Dollar Index Futures'}]}
        with patch.dict('os.environ',{'BARCHART_API_KEY':'fixture'}),patch.object(u,'request_json',return_value=payload):
            with self.assertRaisesRegex(ValueError,'非DXY现货'):u.barchart_dxy(ITEMS['dxy'],NOW)
    def test_exact_cash_metadata_and_daily_history(self):
        q={'status':{'code':200},'results':[{'symbol':'DXY00','name':'U.S. Dollar Index Cash'}]}
        h={'status':{'code':200},'results':[{'symbol':'DXY00','tradingDay':'2026-11-19','close':103.0}]}
        with patch.dict('os.environ',{'BARCHART_API_KEY':'fixture'}),patch.object(u,'request_json',side_effect=[q,h]):
            rows,source=u.barchart_dxy(ITEMS['dxy'],NOW)
        self.assertEqual(rows,[{'date':'2026-11-19','value':103.0}]);self.assertIn('DXY00',source)
    def test_preserve_real_schedule_event_context(self):
        with patch.dict('os.environ',{'TRIGGER_EVENT':'schedule','TRIGGER_SCHEDULE':'15 0 * * *','WORKFLOW_RUN_URL':'https://github.com/example/actions/runs/1'}):
            self.assertEqual(u.update_context()['event'],'schedule');self.assertEqual(u.update_context()['schedule'],'15 0 * * *')

if __name__=='__main__': unittest.main()
