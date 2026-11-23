import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from scripts import update_data as u

NOW = datetime(2026,11,22,1,tzinfo=timezone.utc)
ITEMS = {i['id']:i for i in u.CONFIG['indicators']}


class TestPortalSources(unittest.TestCase):
    def dxy(self, text=None, quote=None):
        text = text if text is not None else 'var _DATA=('+json.dumps('2026-11-20,103.95,103.58,103.96,103.8404,')+');'
        return [Mock(text=quote or 'var hq_str_DINIW="05:59:00,103.8404,美元指数,2026-11-21";'),Mock(text=text)]

    def test_dxy_close_column_and_comment_jsonp(self):
        responses = self.dxy(); responses[1].text='/*<script>ignored</script>*/\n'+responses[1].text
        with patch.object(u.requests,'get',side_effect=responses): rows,source=u.sina_dxy(ITEMS['dxy'],NOW)
        self.assertEqual(rows,[{'date':'2026-11-20','value':103.8404}])
        self.assertIn('非DX期货',source)

    def test_dxy_rejects_executable_or_wrong_envelope(self):
        for text in ['var _DATA=("2026-11-20,1,1,1,1");alert(1);','other=("2026-11-20,1,1,1,1");','var _DATA=(function(){return "x"}());']:
            with self.subTest(text=text),patch.object(u.requests,'get',side_effect=self.dxy(text)):
                with self.assertRaises(ValueError):u.sina_dxy(ITEMS['dxy'],NOW)

    def test_dxy_rejects_wrong_instrument(self):
        with patch.object(u.requests,'get',side_effect=self.dxy(quote='var hq_str_DINIW="美元期货";')):
            with self.assertRaises(ValueError):u.sina_dxy(ITEMS['dxy'],NOW)
        with self.assertRaises(ValueError):u.sina_dxy({**ITEMS['dxy'],'vendor_symbol':'DX'},NOW)

    def test_dxy_rejects_bad_ohlc_and_duplicate_dates(self):
        for data in ['2026-11-20,103,103,104,105','2026-11-20,103,0,104,103','2026-11-20,103,102,104,NaN',
                     '2026-11-20,103,102,104,103|2026-11-20,103,102,104,103']:
            with self.subTest(data=data),patch.object(u.requests,'get',side_effect=self.dxy('var _DATA=('+json.dumps(data)+');')):
                with self.assertRaises(ValueError):u.sina_dxy(ITEMS['dxy'],NOW)

    def test_dxy_filters_unconfirmed_current_day(self):
        now=datetime(2026,11,20,23,tzinfo=timezone.utc)
        points=[{'date':'2026-11-19','value':103.94},{'date':'2026-11-20','value':103.84}]
        with patch.object(u,'sina_dxy',return_value=(points,'sina')):
            rows,_=u.fetch(ITEMS['dxy'],now)
        self.assertEqual(rows,[points[0]])

    def copper_responses(self):
        return [{'vcode':'HG','vname':'COMEX铜','bjdw':'美元和美分/磅','zxbddw':'0.0005美元/磅'},
                requests.ConnectionError('history unavailable'),
                {'data':{'f57':'HG00Y','f58':'COMEX铜','f107':101,'f59':4,'f43':54650,'f86':1795212000,'f60':56335}}]

    def test_copper_completed_snapshot_scaled_once_no_fake_previous_close(self):
        with patch.object(u,'request_json',side_effect=self.copper_responses()):
            rows,source=u.fetch(ITEMS['copper'],NOW)
        self.assertEqual(rows,[{'date':'2026-11-20','value':5.465}])
        self.assertIn('非官方结算',source)
        card=u.calculate(ITEMS['copper'],rows,source,None,NOW,u.CONFIG['thresholds'])
        self.assertIsNone(card['change_1']);self.assertIsNone(card['change_20'])
        self.assertIn('不足',card['interpretation'])

    def test_copper_rejects_wrong_unit_or_instrument_metadata(self):
        for field,value in [('vcode','CU'),('bjdw','元/吨'),('bjdw','美分/磅')]:
            data=self.copper_responses();data[0][field]=value
            with self.subTest(field=field),patch.object(u,'request_json',side_effect=data):
                with self.assertRaises(ValueError):u.eastmoney_copper(ITEMS['copper'],NOW)

    def test_copper_tick_is_validated_independently_of_quote_unit(self):
        for tick in ['0.005美元/磅','0.0005美分/磅','','NaN美元/磅']:
            data=self.copper_responses();data[0]['zxbddw']=tick
            with self.subTest(tick=tick),patch.object(u,'request_json',side_effect=data):
                with self.assertRaisesRegex(ValueError,'最小变动价位'):u.eastmoney_copper(ITEMS['copper'],NOW)

    def test_tick_unit_cannot_replace_missing_quote_unit(self):
        data=self.copper_responses();data[0].pop('bjdw')
        with patch.object(u,'request_json',side_effect=data):
            with self.assertRaisesRegex(ValueError,'报价单位'):u.eastmoney_copper(ITEMS['copper'],NOW)

    def test_copper_rejects_wrong_quote_or_precision(self):
        for field,value in [('f57','CU0'),('f107',102),('f59',2),('f43',0),('f43',float('inf'))]:
            data=self.copper_responses();data[2]['data'][field]=value
            with self.subTest(field=field,value=value),patch.object(u,'request_json',side_effect=data):
                with self.assertRaises(ValueError):u.eastmoney_copper(ITEMS['copper'],NOW)

    def test_copper_rejects_intraday_future_and_weekend_timestamps(self):
        for stamp in [datetime(2026,11,20,21,tzinfo=timezone.utc),datetime(2026,11,23,22,tzinfo=timezone.utc),datetime(2026,11,21,22,tzinfo=timezone.utc)]:
            data=self.copper_responses();data[2]['data']['f86']=stamp.timestamp()
            with self.subTest(stamp=stamp),patch.object(u,'request_json',side_effect=data):
                with self.assertRaises(ValueError):u.eastmoney_copper(ITEMS['copper'],NOW)

    def test_copper_daily_history_is_not_integer_scaled_or_intraday(self):
        data=self.copper_responses()
        data[1]={'data':{'code':'HG00Y','name':'COMEX铜','market':101,
                          'klines':['2026-11-20,5.59,5.465,5.608,5.439,100','2026-11-23,5.5,5.5,5.6,5.4,100']}}
        with patch.object(u,'request_json',side_effect=data) as req:
            rows,source=u.eastmoney_copper(ITEMS['copper'],NOW)
        self.assertEqual(rows,[{'date':'2026-11-20','value':5.465}]);self.assertEqual(req.call_count,2)
        self.assertIn('日线',source)

    def test_changed_copper_series_drops_old_front_contract_history(self):
        history={'series':{'copper':[{'date':'2026-11-19','value':5.6}]},'sources':{'copper':'old'}}
        old={**ITEMS['copper'],'symbol':'HG_FRONT','provider':'external'}
        u.prepare_history(history,[ITEMS['copper']],{'indicators':[old]})
        self.assertNotIn('copper',history['series'])


class TestCopperHistoryIntegrity(unittest.TestCase):
    def rows(self):
        days=u.session_dates(date(2026,7,6),date(2026,11,20),'cme')
        return [{'date':day.isoformat(),'value':5.465} for day in days]

    def test_100_unique_sorted_cme_dates_preserve_prices(self):
        rows=self.rows();before=json.dumps(rows)
        check=u.validate_copper_history(rows)
        self.assertEqual(check['observations'],100);self.assertEqual(check['unique_dates'],100)
        self.assertTrue(check['ascending']);self.assertEqual(check['expected_cme_sessions'],100)
        self.assertEqual(check['missing_sessions'],[]);self.assertEqual(check['unexpected_dates'],[])
        self.assertFalse(check['rollover_rule_verified']);self.assertEqual(json.dumps(rows),before)

    def test_duplicate_dates_are_not_silently_deduplicated(self):
        rows=self.rows();rows[50]=dict(rows[49])
        with self.assertRaisesRegex(u.CopperHistoryError,'日期重复'):u.validate_copper_history(rows)

    def test_unsorted_dates_are_not_silently_sorted(self):
        rows=self.rows();rows[49],rows[50]=rows[50],rows[49]
        with self.assertRaisesRegex(u.CopperHistoryError,'未升序'):u.validate_copper_history(rows)

    def test_missing_cme_session_is_reported_without_filling(self):
        rows=self.rows();missing=rows.pop(50)['date'];before=json.dumps(rows)
        self.assertEqual(u.copper_history_check(rows)['missing_sessions'],[missing])
        with self.assertRaisesRegex(u.CopperHistoryError,missing):u.validate_copper_history(rows)
        self.assertEqual(json.dumps(rows),before)

    def test_weekends_and_christmas_do_not_create_false_gaps(self):
        rows=[{'date':'2026-12-24','value':5.4},{'date':'2026-12-28','value':5.5}]
        self.assertEqual(u.validate_copper_history(rows)['missing_sessions'],[])

    def test_non_cme_date_is_rejected(self):
        rows=[{'date':'2026-11-20','value':5.4},{'date':'2026-11-21','value':5.5}]
        with self.assertRaisesRegex(u.CopperHistoryError,'非CME交易日'):u.validate_copper_history(rows)

    def test_bad_history_does_not_fall_back_and_hide_the_error(self):
        rows=self.rows();rows[50]=dict(rows[49])
        data=TestPortalSources().copper_responses()
        data[1]={'data':{'code':'HG00Y','name':'COMEX铜','market':101,
            'klines':[p['date']+',5.5,5.465,5.6,5.4,100' for p in rows]}}
        with patch.object(u,'request_json',side_effect=data) as request:
            with self.assertRaisesRegex(u.CopperHistoryError,'日期重复'):u.eastmoney_copper(ITEMS['copper'],NOW)
        self.assertEqual(request.call_count,2)

    def test_merged_history_gap_preserves_old_history_and_surfaces_error(self):
        old=[{'date':'2026-11-19','value':5.592},{'date':'2026-11-20','value':5.465}]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir()
            (root/'data/history.json').write_text(json.dumps({'series':{'copper':old},'sources':{'copper':'prior'},'definitions':{'copper':u.definition_key(ITEMS['copper'])}}))
            (root/'data/snapshot.json').write_text(json.dumps({'indicators':[]}))
            def fetch(item,now):
                return ([{'date':'2026-11-24','value':5.6}] if item['id']=='copper' else [{'date':'2026-11-20','value':4.0}]),'test'
            with patch.object(u,'ROOT',root),patch.object(u,'fetch',side_effect=fetch):
                self.assertTrue(u.run(datetime(2026,11,26,8,tzinfo=timezone.utc)))
            saved=json.loads((root/'data/history.json').read_text())
            self.assertEqual(saved['series']['copper'],old)
            snap=json.loads((root/'data/snapshot.json').read_text())
            copper=next(c for c in snap['indicators'] if c['id']=='copper')
            self.assertIn('2026-11-23',copper['error']);self.assertEqual(copper['value'],5.465)
            self.assertEqual(copper['status'],'stale');self.assertEqual(snap['sources_failed'],1)
            self.assertEqual(snap['history_checks'][0]['status'],'ok')


if __name__=='__main__':unittest.main()
