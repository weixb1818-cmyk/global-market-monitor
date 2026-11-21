import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from scripts import update_data as u

NOW = datetime(2026,11,21,8,tzinfo=timezone.utc)
ITEMS = {i['id']:i for i in u.CONFIG['indicators']}


class TestFreeSources(unittest.TestCase):
    def fixtures(self, key='usdcnh'):
        item = ITEMS[key]
        base,quote = item['symbol'].split('/')
        meta = {'iso_code':'CNH','name':'Chinese Renminbi Yuan Offshore'} if key=='usdcnh' else {'iso_code':'XAU','name':'Gold (Troy Ounce)'}
        rows = [{'date':'2026-11-20','base':base,'quote':quote,'rate':6.67 if key=='usdcnh' else 3500,
                 'providers':[{'key':'ONE','date':'2026-11-19'}, {'key':'TWO','date':'2026-11-20'},
                              {'key':'OUTLIER','date':'2026-11-20','excluded':True}]}]
        return item,meta,rows

    def test_exact_offshore_and_source_dates_preserved(self):
        item,meta,rows = self.fixtures()
        with patch.object(u,'request_json',side_effect=[meta,rows]) as request:
            points,source = u.frankfurter(item,NOW)
        self.assertEqual(points[0]['value'],6.67)
        self.assertEqual(points[0]['components'],[{'provider':'ONE','date':'2026-11-19'},{'provider':'TWO','date':'2026-11-20'}])
        self.assertEqual(request.call_args.args[1]['expand'],'providers')
        self.assertNotIn('providers',request.call_args.args[1])  # the free blended route, not a licensed raw feed
        card = u.calculate(item,points,source,None,NOW,u.CONFIG['thresholds'])
        self.assertEqual(card['source_components'],points[0]['components'])

    def test_reject_onshore_metadata_and_pair(self):
        item,meta,rows = self.fixtures()
        for change in ('metadata','pair'):
            m = dict(meta); data = copy.deepcopy(rows)
            if change=='metadata':m.update(iso_code='CNY',name='Chinese Yuan')
            else:data[0]['quote']='CNY'
            with self.subTest(change=change),patch.object(u,'request_json',side_effect=[m,data]):
                with self.assertRaises(ValueError):u.frankfurter(item,NOW)

    def test_gold_is_usd_per_troy_ounce_without_inversion(self):
        item,meta,rows = self.fixtures('gold')
        with patch.object(u,'request_json',side_effect=[meta,rows]):points,_ = u.frankfurter(item,NOW)
        self.assertEqual(points[0]['value'],3500)
        meta['name']='Gold (Gram)'
        with patch.object(u,'request_json',return_value=meta):
            with self.assertRaises(ValueError):u.frankfurter(item,NOW)

    def test_no_carried_forward_or_incomplete_observation(self):
        item,meta,rows = self.fixtures()
        carried = copy.deepcopy(rows[0]);carried['date']='2026-11-21'
        older = copy.deepcopy(rows[0]);older['date']='2026-11-20';older['providers']=[{'key':'OLD','date':'2026-11-19'}]
        with patch.object(u,'request_json',side_effect=[meta,[older,carried]]):
            points,_ = u.frankfurter(item,NOW)
        self.assertEqual(points,[])

    def test_reject_missing_attribution_future_component_or_bad_price(self):
        for problem in ('missing','future','negative'):
            item,meta,rows = self.fixtures()
            if problem=='missing':rows[0]['providers']=[]
            elif problem=='future':rows[0]['providers']=[{'key':'FUTURE','date':'2026-11-21'}]
            else:rows[0]['rate']=-1
            with self.subTest(problem=problem),patch.object(u,'request_json',side_effect=[meta,rows]):
                with self.assertRaises(ValueError):u.frankfurter(item,NOW)

    def test_ecb_cross_requires_two_legs_on_same_date(self):
        xml = b'<Envelope><Cube><Cube time="2026-11-20"><Cube currency="USD" rate="1.1"/><Cube currency="JPY" rate="176"/></Cube><Cube time="2026-11-19"><Cube currency="USD" rate="1.2"/></Cube></Cube></Envelope>'
        with patch.object(u.requests,'get',return_value=Mock(content=xml)):
            points,source = u.ecb_usdjpy(NOW)
        self.assertEqual(points,[{'date':'2026-11-20','value':160.0}])
        self.assertIn('非收盘',source)

    def test_different_instrument_history_never_spliced(self):
        old = {**ITEMS['wti'],'provider':'external','symbol':'CL_FRONT','series_definition':''}
        history = {'series':{'wti':[{'date':'2026-11-19','value':80}]},'sources':{'wti':'old futures'}}
        u.prepare_history(history,[ITEMS['wti']],{'indicators':[old]})
        self.assertNotIn('wti',history['series'])
        self.assertNotIn('wti',history['sources'])
        self.assertEqual(history['definitions']['wti'],u.definition_key(ITEMS['wti']))

    def test_same_definition_retains_failure_history(self):
        old = {'series':{'wti':[{'date':'2026-11-19','value':80}]},'sources':{'wti':'EIA'},'definitions':{'wti':u.definition_key(ITEMS['wti'])}}
        u.prepare_history(old,[ITEMS['wti']],{})
        self.assertEqual(len(old['series']['wti']),1)


if __name__=='__main__':unittest.main()
