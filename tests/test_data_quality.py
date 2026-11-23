import copy
import json
import math
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, Mock
from scripts import update_data as u
from scripts.source_evidence import Evidence, revisions
from test_dashboard import cards, ITEMS, T, NOW


class StatusBoundary(unittest.TestCase):
    def test_every_non_ok_key_blocks_full_classification(self):
        for key in ['dxy','real10y','us2y','hy','vix']:
            for status in ['error','stale','missing','new_unknown',None]:
                c=cards(dxy=2,real=30,hy=30,vix=4,vixnow=30,hynow=500)
                c[key]['status']=status
                with self.subTest(key=key,status=status):
                    result=u.classify(c,T)
                    self.assertFalse(result['complete'])
                    self.assertEqual(result['mode'],'limited' if key=='dxy' else 'insufficient')
                    self.assertNotIn(key,[a['id'] for a in result['risk_alerts']])

    def test_error_field_even_with_ok_status_and_nonfinite_values(self):
        for change in [{'error':'timeout'},{'value':float('nan')},{'change_20':float('inf')},{'status':None}]:
            c=cards(dxy=2,real=30);c['hy'].update(change)
            self.assertEqual(u.classify(c,T)['mode'],'insufficient')

    def test_failed_high_values_have_no_directional_or_level_claim(self):
        for key in ['vix','hy','dxy','copper']:
            points=[{'date':'2026-11-19','value':20+i} for i in range(21)]
            c=u.calculate(ITEMS[key],points,'fixture','timeout',NOW,T)
            self.assertEqual(c['status'],'error')
            self.assertIn('仅保留历史',c['interpretation'])
            self.assertNotIn('高位',c['interpretation'])
            self.assertEqual(u.risk_levels({key:c},T),[])

    def test_fetch_failure_with_fresh_history_through_json_and_ui(self):
        realroot=Path(u.__file__).resolve().parents[1]
        # Real stored observations exercise the whole updater, with no fixture
        # quotes written into production. A frozen clock keeps them fresh.
        history=json.loads((realroot/'data/history.json').read_text())
        old=json.loads((realroot/'data/snapshot.json').read_text())
        clock=datetime(2026,11,23,10,tzinfo=timezone.utc)
        for failed in ['dxy','hy','vix','real10y','us2y']:
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'data').mkdir()
                (root/'data/history.json').write_text(json.dumps(history));(root/'data/snapshot.json').write_text(json.dumps(old))
                def fetch(item,now):
                    if item['id']==failed:raise ValueError('fixture source failure')
                    return history['series'][item['id']], 'test retained observations'
                with patch.object(u,'ROOT',root),patch.object(u,'fetch',side_effect=fetch):self.assertTrue(u.run(clock))
                snapshot=json.loads((root/'data/snapshot.json').read_text())
                card=next(c for c in snapshot['indicators'] if c['id']==failed)
                self.assertEqual(card['status'],'error');self.assertIsNotNone(card['value'])
                self.assertEqual(card['as_of'],history['series'][failed][-1]['date'])
                self.assertEqual(snapshot['macro']['mode'],'limited' if failed=='dxy' else 'insufficient')
                self.assertNotIn(failed,[a['id'] for a in snapshot['risk_alerts']])
                script="""
const fs=require('fs'),vm=require('vm');let snap=JSON.parse(fs.readFileSync(process.argv[1]));
const doc={getElementById(){return {parentElement:{classList:{add(){}}}}}};
const ctx={console,document:doc,fetch:async()=>({ok:true,json:async()=>snap}),snap};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('app.js','utf8').replace(/load\(\);\s*$/,''),ctx);
const result=vm.runInContext("({macro:currentMacro(snap,new Date('2026-11-23T10:00:00Z')),alerts:currentAlerts(snap,new Date('2026-11-23T10:00:00Z'))})",ctx);
console.log(JSON.stringify(result));
"""
                result=json.loads(subprocess.check_output(['node','-e',script,str(root/'data/snapshot.json')],cwd=realroot,text=True))
                self.assertEqual(result['macro']['mode'],snapshot['macro']['mode'])
                self.assertNotIn(failed,[a['id'] for a in result['alerts']])


class EvidenceTests(unittest.TestCase):
    def test_secrets_are_not_in_evidence_and_raw_is_restricted(self):
        with tempfile.TemporaryDirectory() as d:
            e=Evidence(d,{});e.set_item({'id':'hy'})
            response=Mock(content=b'copyrighted quotes',status_code=200,headers={})
            e.record('https://api.stlouisfed.org/fred/series/observations?api_key=secret',{'api_key':'secret','series_id':'HY'},response,'now')
            self.assertNotIn('secret',json.dumps(e.requests));self.assertNotIn('raw_path',e.requests[0])
            self.assertEqual(len(e.requests[0]['response_sha256']),64)
            e.record('https://private.example/secret/token',{},None,'now',ValueError('secret'))
            self.assertNotIn('token',json.dumps(e.requests));self.assertEqual(e.requests[-1]['error_type'],'ValueError')

    def test_revisions_keep_old_and_new_values(self):
        old=[{'date':'2026-11-19','value':100}];new=[{'date':'2026-11-19','value':101}]
        r=revisions(old,new);self.assertEqual(r[0]['old_value'],100);self.assertEqual(r[0]['new_value'],101)
        self.assertEqual(old[0]['value'],100)

    def test_common_date_spreads_keep_real_legs_and_strict_tolerance(self):
        series={'us10y':[{'date':'2026-11-19','value':5.04}],'us2y':[{'date':'2026-11-19','value':4.76}],
                'spread10y2y':[{'date':'2026-11-19','value':.30}],'spread10y3m':[]}
        r=u.spread_history_checks(series,T)[0];self.assertEqual(r['warnings'],0)
        series['spread10y2y'][0]['value']=.31
        r=u.spread_history_checks(series,T)[0];self.assertEqual(r['warnings'],1)
        self.assertAlmostEqual(r['latest_common']['signed_difference_bp'],3)
        series['us2y'][0]['date']='2026-11-18'
        self.assertEqual(u.spread_history_checks(series,T)[0]['observations'],0)

class CurveFailureSafety(unittest.TestCase):
    def test_failed_bottom_leg_does_not_pass_latest_check(self):
        c={'spread10y2y':{'as_of':'2026-11-19','value':28,'status':'ok'},'spread10y3m':{'as_of':None,'value':None,'status':'missing'}}
        series={'us10y':[{'date':'2026-11-19','value':5.04}],'us2y':[{'date':'2026-11-19','value':4.76}]}
        self.assertEqual(u.compare_spreads(c,series,T,invalid_ids=['us2y'])[0]['status'],'not_comparable')
