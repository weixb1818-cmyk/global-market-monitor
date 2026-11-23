#!/usr/bin/env python3
"""Fixed-rule review. Strict archived availability and exploratory data never mix."""
import argparse
import hashlib
import json
import statistics
import subprocess
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from scripts import update_data as u
except ModuleNotFoundError:
    import update_data as u

ROOT=Path(__file__).resolve().parents[1]
UTC=timezone.utc
RISK_STATES={'金融压力扩散','增长担忧定价','金融条件趋紧'}
# Evaluation labels are fixed here BEFORE examining results, not classifier thresholds.
DRAWDOWN_LABEL={5:-3.0,20:-5.0}


def endpoint(p):
    # Use an asset's first COMPLETE daily close after the signal as the reference.
    # Equity close at 16:00 NY; BTC closes at next 00:00 UTC.
    d=date.fromisoformat(p['date'])
    return (datetime.combine(d+timedelta(days=1),datetime.min.time(),UTC) if p['asset']=='btc'
            else datetime.combine(d,datetime.min.time(),ZoneInfo('America/New_York')).replace(hour=16))


def outcome(series, signal_time, asset, horizon):
    future=[p for p in series if endpoint({**p,'asset':asset})>signal_time]
    if len(future)<horizon+1:return {'status':'pending','available_closes':len(future),'needed_closes':horizon+1}
    window=future[:horizon+1];values=[p['value'] for p in window]
    if any(v<=0 for v in values):return {'status':'invalid'}
    peak=values[0];dd=0
    for v in values:peak=max(peak,v);dd=min(dd,(v/peak-1)*100)
    return {'status':'mature','entry_date':window[0]['date'],'end_date':window[-1]['date'],
            'entry_value':values[0],'end_value':values[-1], 'return_pct':(values[-1]/values[0]-1)*100,
            'max_adverse_from_entry_pct':min(0,(min(values)/values[0]-1)*100),'max_close_drawdown_pct':dd}


def evaluate(cards, histories, available):
    return u.classify(cards,u.CONFIG['thresholds'])


def archived():
    commits=subprocess.check_output(['git','log','--reverse','--format=%H','--','data/snapshot.json'],cwd=ROOT,text=True).splitlines()
    daily={}
    for sha in commits:
        try:
            snap=json.loads(subprocess.check_output(['git','show',sha+':data/snapshot.json'],cwd=ROOT,stderr=subprocess.DEVNULL))
            commit_time=datetime.fromisoformat(subprocess.check_output(['git','show','-s','--format=%cI',sha],cwd=ROOT,text=True).strip())
            available=max(datetime.fromisoformat(snap['generated_at']),commit_time)
            c={x['id']:dict(x) for x in snap['indicators']}
            attempt=json.loads(subprocess.check_output(['git','show',sha+':data/last_attempt.json'],cwd=ROOT,stderr=subprocess.DEVNULL))
            if attempt.get('status')=='failed' and datetime.fromisoformat(attempt['at'])>=datetime.fromisoformat(snap['generated_at']):
                for v in c.values():v.update(status='error',error='archived failed attempt')
            # New boundary applied to data actually archived at that time. We do
            # not claim the historical UI had already implemented this fix.
            for v in c.values():
                if v.get('as_of') and u.is_stale(v['as_of'],v['calendar'],available,u.CONFIG['thresholds']):v['status']='stale'
            m=u.classify(c,u.CONFIG['thresholds']);day=available.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
            if day not in daily:
                daily[day]={'commit':sha,'available_at':available.isoformat(),'macro':m,
                            'input_dates':{k:v.get('as_of') for k,v in c.items() if k in ['dxy','real10y','hy','vix','us2y']},
                            'input_statuses':{k:v.get('status') for k,v in c.items() if k in ['dxy','real10y','hy','vix','us2y']}}
        except (KeyError,ValueError,subprocess.CalledProcessError):continue
    return list(daily.values())


def descriptive(series):
    """Current-vintage, assumed delay sensitivity study. NOT a PIT backtest.

    Old values were not archived when published. A long lag cannot cure revision
    leakage. Results from this section must never be used as validated forecasts.
    """
    items={x['id']:x for x in u.CONFIG['indicators']}
    sessions=u.session_dates(date.fromisoformat(max(series[k][20]['date'] for k in ['dxy','real10y','hy','vix','us2y'] if len(series.get(k,[]))>20)),
                             date.fromisoformat(min(series[k][-1]['date'] for k in ['dxy','real10y','hy','vix','us2y'])),'nyse')
    results=[]
    for delay in [2,4]:
        rows=[];prior=None
        for d in sessions:
            available=datetime.combine(d,datetime.min.time(),ZoneInfo('Asia/Shanghai')).replace(hour=8,minute=15)
            cards={}
            for key in ['dxy','real10y','hy','vix','us2y','spread10y2y','spread10y3m']:
                pts=[p for p in series.get(key,[]) if date.fromisoformat(p['date'])<=d-timedelta(days=delay)]
                cards[key]=u.calculate(items[key],pts,'current-vintage descriptive sample',None,available,u.CONFIG['thresholds'])
            m=u.classify(cards,u.CONFIG['thresholds']);transition=m['state']!=prior;prior=m['state']
            rows.append({'signal_at':available.isoformat(),'state':m['state'],'mode':m['mode'],'state_transition':transition,
                'signals':m['signals'],'uncertainty':m['uncertainty'],'input_dates':{k:c['as_of'] for k,c in cards.items()},
                'curve_changes_bp':{k:cards[k]['change_20'] for k in ['spread10y2y','spread10y3m']},
                'outcomes':{asset:{str(h):outcome(series.get(asset,[]),available,asset,h) for h in [5,20]} for asset in ['sp500','nasdaq100','btc']}})
        groups=[]
        for asset in ['sp500','nasdaq100','btc']:
            for h in [5,20]:
                for state in sorted({r['state'] for r in rows}):
                    sample=[r['outcomes'][asset][str(h)] for r in rows if r['state']==state and r['outcomes'][asset][str(h)]['status']=='mature']
                    changes=[r['outcomes'][asset][str(h)] for r in rows if r['state']==state and r['state_transition'] and r['outcomes'][asset][str(h)]['status']=='mature']
                    groups.append({'asset':asset,'horizon':h,'state':state,'n_daily_overlapping':len(sample),'n_state_transitions':len(changes),
                                   'mean_max_drawdown_pct':statistics.mean(x['max_close_drawdown_pct'] for x in sample) if sample else None,
                                   'median_max_drawdown_pct':statistics.median(x['max_close_drawdown_pct'] for x in sample) if sample else None,
                                   'label_drawdown_threshold_pct':DRAWDOWN_LABEL[h],
                                   'risk_event_count':sum(x['max_close_drawdown_pct']<=DRAWDOWN_LABEL[h] for x in sample)})
        cases={}
        # Fixed deterministic selection: first qualifying date, never best result.
        for r in rows:
            x=r['outcomes']['sp500']['20']
            if x['status']!='mature' or r['mode']!='full':continue
            warn=r['state'] in RISK_STATES;event=x['max_close_drawdown_pct']<=DRAWDOWN_LABEL[20]
            category='warning_and_drawdown' if warn and event else 'warning_without_drawdown' if warn else 'missed_drawdown' if event else 'no_warning_no_drawdown'
            cases.setdefault(category,r)
        results.append({'assumed_calendar_day_lag':delay,'groups':groups,'first_cases':cases,'daily':rows})
    return {'status':'exploratory_only_not_point_in_time','revision_leakage_unresolved':True,
            'warning':'Only today’s normalized historical values exist for these dates. Assumed lags do not prove historical publication availability. Overlapping windows and small sample invalidate predictive claims.', 'lag_scenarios':results}


def main():
    history=json.loads((ROOT/'data/history.json').read_text());series=history['series'];samples=archived()
    for r in samples:
        stamp=datetime.fromisoformat(r['available_at']);r['outcomes']={a:{str(h):outcome(series.get(a,[]),stamp,a,h) for h in [5,20]} for a in ['sp500','nasdaq100','btc']}
    result={'generated_at':datetime.now(UTC).isoformat(),'thresholds':u.CONFIG['thresholds'],
            'thresholds_sha256':hashlib.sha256(json.dumps(u.CONFIG['thresholds'],sort_keys=True).encode()).hexdigest(),
            'history_sha256':hashlib.sha256((ROOT/'data/history.json').read_bytes()).hexdigest(),
            'strict_archived_availability':{'method':'Earliest archived snapshot each Beijing day; available=max(generated_at, Git commit time). New status boundary applied to then-archived inputs. No backfilled historical series used to create old signals.',
                'signals':samples,'mature_outcomes':sum(x['status']=='mature' for r in samples for a in r['outcomes'].values() for x in a.values()),
                'limitation':'Before snapshot archival there is no publication-vintage evidence for all five inputs. Daily close drawdown is not intraday drawdown; next complete close is a reference, not an executable trade.'},
            'descriptive_current_vintage':descriptive(series),
            'conclusion':'Not enough historically archived, matured observations to demonstrate predictive ability. Fixed-rule classifications organize observed market pressure; exploratory associations are not causal or tradable evidence.'}
    out=ROOT/'verification/macro-analysis.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'archived_days':len(samples),'mature_outcomes':result['strict_archived_availability']['mature_outcomes'],'exploratory_only':True},ensure_ascii=False))


if __name__=='__main__':main()
