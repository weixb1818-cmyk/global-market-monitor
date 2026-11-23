#!/usr/bin/env python3
"""Free GitHub schedule gate and honest rolling calendar-day audit."""
import argparse
import json
import os
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo

BJT=ZoneInfo('Asia/Shanghai')
REPO='weixb1818-cmyk/global-market-monitor'


def target_for(now):
    return datetime.combine(now.astimezone(BJT).date(),datetime.min.time(),BJT).replace(hour=8,minute=15)


def report(runs, now, days=10):
    first=date(2026,11,22);end=now.astimezone(BJT).date();rows=[]
    for i in range(days-1,-1,-1):
        d=end-timedelta(days=i);target=datetime.combine(d,datetime.min.time(),BJT).replace(hour=8,minute=15)
        matches=[r for r in runs if r['event']=='schedule' and datetime.fromisoformat(r['created_at'].replace('Z','+00:00')).astimezone(BJT).date()==d]
        state='not_in_operation' if d<first else 'pending' if now<target else 'no_observed_run' if not matches else 'observed'
        rows.append({'date':d.isoformat(),'planned_at':target.isoformat(),'status':state,'runs':[{
          'run_id':r['id'],'url':r['html_url'],'event':r['event'],'head_sha':r['head_sha'],
          'created_at':r['created_at'],'started_at':r.get('run_started_at'),'completed_at':r.get('completed_at'),
          'conclusion':r['conclusion'],'job_conclusions':r.get('job_conclusions',{}),'source_all_success':None,'matched_cron':None,'delay_seconds':(datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))-target).total_seconds(),
          'timing_note':'Arrival grouped by actual Beijing date; delay relative to that date primary 08:15 target, not proof of nominal schedule date or backup cron. Completed time from last job, not updated_at. Source success unknown unless read against per-run evidence.'} for r in matches]})
    observed=sum(r['status']=='observed' for r in rows)
    return {'checked_at':now.isoformat(),'planned_beijing':'08:15','window_days':days,'observed_days':observed,
            'ten_days_observed':observed==days,'ten_days_update_deploy_success':all(any(x['job_conclusions'].get('update')=='success' and x['job_conclusions'].get('deploy')=='success' for x in r['runs']) for r in rows),'records':rows,'limitation':'GitHub schedule has no punctuality SLA; pre-operation/missing/pending days are not successful runs.'}


def get_json(url):
    headers={'Accept':'application/vnd.github+json','User-Agent':'MarketMonitor-Audit'}
    if os.getenv('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    with urlopen(Request(url,headers=headers),timeout=20) as r:return json.load(r)


def gate(event, cron, attempt, now):
    if event!='schedule' or cron=='15 0 * * *':return True
    # Backup is allowed after total OR partial failure; healthy current snapshots
    # are skipped. Current missing/stale values alone are not a fetch failure.
    try:return not(attempt.get('status')=='ok' and datetime.fromisoformat(attempt['at'])>=target_for(now))
    except (KeyError,ValueError,TypeError):return True


def main():
    p=argparse.ArgumentParser();p.add_argument('--gate',action='store_true');args=p.parse_args();now=datetime.now(timezone.utc)
    if args.gate:
        try:attempt=get_json('https://weixb1818-cmyk.github.io/global-market-monitor/data/last_attempt.json')
        except Exception:attempt={}
        run=gate(os.getenv('TRIGGER_EVENT'),os.getenv('TRIGGER_SCHEDULE'),attempt,now)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('run='+str(run).lower()+'\n')
        print(json.dumps({'run':run,'reason':'primary/manual or no healthy current-day update' if run else 'healthy current-day update; skip backup'}));return
    runs=get_json(f'https://api.github.com/repos/{REPO}/actions/workflows/update.yml/runs?event=schedule&per_page=100')['workflow_runs']
    runs=[r for r in runs if datetime.fromisoformat(r['created_at'].replace('Z','+00:00')).astimezone(BJT).date() >= now.astimezone(BJT).date()-timedelta(days=9)]
    for r in runs:
        jobs=get_json(r['jobs_url'])['jobs'];ends=[j['completed_at'] for j in jobs if j.get('completed_at')]
        r['completed_at']=max(ends) if ends else None
        r['job_conclusions']={j['name']:j['conclusion'] for j in jobs}
    result=report(runs,now);out=Path('verification/schedule-10-days.json');out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'}))


if __name__=='__main__':main()
