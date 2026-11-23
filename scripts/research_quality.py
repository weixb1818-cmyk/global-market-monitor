#!/usr/bin/env python3
"""Read-only free-source commodity research; never replaces production data."""
import hashlib
import json
import statistics
from datetime import datetime,timedelta,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]

def main():
    now=datetime.now(timezone.utc);end=now.date()-timedelta(days=1);start=end-timedelta(days=13)
    evidence=[]
    def get(url,params=None):
        began=datetime.now(timezone.utc).isoformat();r=requests.get(url,params=params,timeout=25)
        evidence.append({'endpoint':url,'params':params,'requested_at':began,'completed_at':datetime.now(timezone.utc).isoformat(),
                         'status':r.status_code,'response_sha256':hashlib.sha256(r.content).hexdigest()})
        r.raise_for_status();return r.json()
    result={'checked_at':now.isoformat(),'scope':'Research only; no production instrument or source replacement','requests':evidence,'failures':{}}
    try:
        meta=get('https://api.frankfurter.dev/v2/currency/xau')
        providers=get('https://api.frankfurter.dev/v2/providers')
        blend=get('https://api.frankfurter.dev/v2/rates',{'base':'XAU','quotes':'USD','from':start.isoformat(),'to':end.isoformat(),'expand':'providers'})
        gold=get(f'https://api.nbp.pl/api/cenyzlota/{start}/{end}/',{'format':'json'})
        fx=get(f'https://api.nbp.pl/api/exchangerates/rates/a/usd/{start}/{end}/',{'format':'json'})
        fxmap={r['effectiveDate']:r['mid'] for r in fx['rates']};goldmap={r['data']:r['cena'] for r in gold}
        rows=[]
        for r in blend:
            d=r['date'];parts=[p for p in r['providers'] if not p.get('excluded')]
            if d not in fxmap or d not in goldmap:continue
            nbp=goldmap[d]*31.1034768/fxmap[d]
            rows.append({'date':d,'blend_usd_per_troy_oz':r['rate'],'nbp_gold_pln_per_gram':goldmap[d],
                         'nbp_usd_pln':fxmap[d],'nbp_cross_usd_per_troy_oz':nbp,'difference_pct':(r['rate']/nbp-1)*100,
                         'component_dates':sorted({p['date'] for p in parts}),'mixed_dates':len({p['date'] for p in parts})>1})
        result['gold']={'metadata':meta,'providers':[{k:p.get(k) for k in ['key','name','data_url','terms_url']} for p in providers if p['key'] in meta['providers']],
                        'comparison':'NBP official PLN/gram gold reference * 31.1034768 / same-date USDPLN table A. It is an official reference cross, not COMEX/LBMA executable close. NBP is also a blend constituent, so not fully independent.',
                        'comparisons':rows,'n':len(rows),'median_abs_difference_pct':statistics.median(abs(r['difference_pct']) for r in rows) if rows else None,
                        'max_abs_difference_pct':max((abs(r['difference_pct']) for r in rows),default=None),
                        'blend_rows_with_mixed_dates':sum(len({p['date'] for p in r['providers'] if not p.get('excluded')})>1 for r in blend),
                        'revision_policy':'Frankfurter says blended historical rates can shift when new data arrives. Per-run normalized revisions are logged by updater.',
                        'documentation':['https://frankfurter.dev/methodology/','https://frankfurter.dev/python/','https://api.nbp.pl/en.html']}
    except (requests.RequestException,ValueError,KeyError) as e:result['failures']['gold']=type(e).__name__
    try:
        metadata=get('https://futsse-static.eastmoney.com/redis',{'msgid':'101_4_info'})
        result['copper']={'unit':metadata.get('bjdw'),'tick':metadata.get('zxbddw'),
                           'published_contract_fields':{k:v for k,v in metadata.items() if k in ['vname','vcode','hyjgyf','jydw','jysj','zhjyr','jgrq']},
                           'rollover_rule_verified':False,'research_result':'Public product page and contract metadata do not establish HG00Y selection, roll date or adjustment formula. Contract delivery months are not a continuous roll algorithm.',
                           'checked_pages':['https://quote.eastmoney.com/globalfuture/HG00Y.html','https://futsse-static.eastmoney.com/redis?msgid=101_4_info']}
    except (requests.RequestException,ValueError) as e:result['failures']['copper']=type(e).__name__
    Path(ROOT/'verification/commodity-research.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'failures':result['failures'],'gold_comparisons':result.get('gold',{}).get('n')}))

if __name__=='__main__':main()
