#!/usr/bin/env python3
"""Check the actual Pages publication from a separate runner after deployment."""
import json
import os
import time
from urllib.request import Request, urlopen

base = os.environ['DASHBOARD_URL'].rstrip('/')+'/'
expected = os.environ.get('EXPECTED_GENERATED_AT')
for attempt in range(8):
    try:
        def get(path):
            req=Request(base+path+('?check='+str(time.time_ns())), headers={'Cache-Control':'no-cache','User-Agent':'MarketDashboard-PublishVerifier/1.0'})
            with urlopen(req,timeout=20) as r:
                if r.status!=200: raise ValueError(f'{path}: HTTP {r.status}')
                return r.read()
        html=get('index.html').decode('utf-8')
        if '全球市场每日观察' not in html: raise ValueError('wrong index document')
        for name in ('app.js','styles.css'):
            if not get(name): raise ValueError('empty asset')
        data=json.loads(get('data/snapshot.json'))
        if len(data['indicators'])!=17: raise ValueError('wrong indicator count')
        if expected and data['generated_at']!=expected: raise ValueError('CDN still serves an earlier snapshot')
        attempt_data=json.loads(get('data/last_attempt.json'))
        ctx=attempt_data.get('update_context',{})
        if os.getenv('EXPECTED_RUN_URL') and ctx.get('run_url')!=os.environ['EXPECTED_RUN_URL']:
            raise ValueError('CDN still serves an earlier update record')
        print(json.dumps({'url':base,'generated_at':data['generated_at'],'cards':17,'macro':data['macro']['state'],'mode':data['macro'].get('mode'),'event':ctx.get('event'),'schedule':ctx.get('schedule'),'run_url':ctx.get('run_url'),'result':'public readback verified'},ensure_ascii=False))
        break
    except Exception as exc:
        if attempt==7: raise
        print(f'Publication propagation check {attempt+1}: {type(exc).__name__}; retrying')
        time.sleep(5)
