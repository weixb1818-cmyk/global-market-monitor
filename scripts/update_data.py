#!/usr/bin/env python3
"""Fetch and validate daily close observations; never invent a quote."""
from __future__ import annotations
import concurrent.futures, csv, io, json, logging, math, os, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import holidays
import exchange_calendars as xcals

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
ET = ZoneInfo('America/New_York')
UTC = timezone.utc
LOG = logging.getLogger('update')


def observations(rows):
    result = {}
    for row in rows:
        d = date.fromisoformat(str(row['date'])[:10]).isoformat()
        raw = row.get('value')
        if raw in (None, '', '.'): continue
        val = float(raw)
        if not math.isfinite(val): raise ValueError('non-finite value')
        result[d] = val
    return [{'date': d, 'value': v} for d, v in sorted(result.items())]


def request_json(url, params=None, headers=None):
    response = requests.get(url, params=params, headers=headers, timeout=18)
    response.raise_for_status()
    return response.json()


def fred(symbol, now):
    key = os.getenv('FRED_API_KEY')
    if key:
        body = request_json('https://api.stlouisfed.org/fred/series/observations', {'series_id':symbol,'api_key':key,'file_type':'json','observation_start':(now.date()-timedelta(days=130)).isoformat()})
        if 'observations' not in body: raise ValueError('FRED response missing observations')
        rows = body['observations']
    else:
        response = requests.get('https://fred.stlouisfed.org/graph/fredgraph.csv', params={'id':symbol,'cosd':(now.date()-timedelta(days=130)).isoformat()}, timeout=18)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        if not reader.fieldnames or symbol not in reader.fieldnames: raise ValueError('invalid FRED CSV')
        rows = [{'date':r[reader.fieldnames[0]],'value':r[symbol]} for r in reader]
    return observations(rows), 'FRED / '+symbol


def coingecko(symbol, now):
    headers = {'x-cg-demo-api-key':os.environ['COINGECKO_API_KEY']} if os.getenv('COINGECKO_API_KEY') else {}
    body = request_json(f'https://api.coingecko.com/api/v3/coins/{symbol}/market_chart', {'vs_currency':'usd','days':90,'interval':'daily'}, headers)
    if not isinstance(body.get('prices'), list): raise ValueError('invalid CoinGecko response')
    rows = []
    for ts, value in body['prices']:
        dt = datetime.fromtimestamp(ts/1000, UTC)
        # Daily sample at 00:00 UTC is the previous UTC day's closing snapshot.
        if dt.hour == dt.minute == dt.second == 0 and dt <= now:
            rows.append({'date':(dt.date()-timedelta(days=1)).isoformat(),'value':value})
    return observations(rows), 'CoinGecko / UTC 00:00'


def twelve(symbol, now):
    key = os.getenv('TWELVE_DATA_API_KEY')
    if not key: raise ValueError('未配置 TWELVE_DATA_API_KEY')
    body = request_json('https://api.twelvedata.com/time_series', {'symbol':symbol,'interval':'1day','outputsize':100,'apikey':key})
    if body.get('status') == 'error' or 'values' not in body: raise ValueError('Twelve Data 不支持该品种或账户无权限')
    meta = body.get('meta', {})
    if meta.get('symbol', '').upper() != symbol.upper(): raise ValueError('Twelve Data 返回品种不符')
    tz_name = meta.get('exchange_timezone') or 'UTC'
    try: local_today = now.astimezone(ZoneInfo(tz_name)).date()
    except Exception as exc: raise ValueError('Twelve Data 时区不可识别') from exc
    rows = observations([{'date':v['datetime'],'value':v['close']} for v in body['values']])
    rows = [p for p in rows if date.fromisoformat(p['date']) < local_today]
    return rows, 'Twelve Data / '+symbol+' / '+tz_name+' 日线'


def external(item, now):
    # An authorized source must explicitly certify exact instrument, units and completed daily closes.
    url = os.getenv('MARKET_DATA_'+item['id'].upper()+'_URL')
    if not url: raise ValueError('未配置已授权且定义一致的行情源')
    body = request_json(url)
    if body.get('symbol') != item['symbol'] or body.get('unit') != item['unit'] or body.get('daily_close') is not True or not body.get('source'):
        raise ValueError('行情源元数据未匹配品种、单位或已收盘口径')
    complete_through = date.fromisoformat(body['complete_through'])
    rows = [p for p in observations(body['observations']) if date.fromisoformat(p['date']) <= complete_through]
    return rows, str(body['source'])[:100]


def fetch(item, now):
    if item['provider']=='fred': result = fred(item['symbol'], now)
    elif item['provider']=='coingecko': result = coingecko(item['symbol'], now)
    elif item['provider']=='twelve': result = twelve(item['symbol'], now)
    else: result = external(item, now)
    points, source = result
    # US prices on the current date are usable only after their completed session.
    et = now.astimezone(ET)
    cutoff = 17 if item['provider'] in ('external','twelve') else 18
    max_date = et.date() if et.hour >= cutoff else et.date()-timedelta(days=1)
    if item['calendar']=='crypto': max_date = now.astimezone(UTC).date()-timedelta(days=1)
    if item['provider']=='twelve': max_date = now.astimezone(UTC).date()-timedelta(days=1)
    points = [p for p in points if date.fromisoformat(p['date']) <= max_date]
    if not points: raise ValueError('无已完成交易时段的有效数据')
    return points[-120:], source


def market_sessions(start, end, calendar):
    if end <= start: return 0
    if calendar == 'bond':
        us_holidays = holidays.US(years=range(start.year, end.year+1))
        return sum(1 for i in range(1,(end-start).days+1) if (d:=start+timedelta(days=i)).weekday()<5 and d not in us_holidays)
    cal=xcals.get_calendar('XNYS',start=(start-timedelta(days=8)).isoformat(),end=(end+timedelta(days=8)).isoformat())
    return len(cal.sessions_in_range((start+timedelta(days=1)).isoformat(),end.isoformat()))


def is_stale(as_of, calendar, now, t):
    if not as_of: return True
    d = date.fromisoformat(as_of)
    if calendar == 'crypto':
        close = datetime.combine(d+timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        return (now-close).total_seconds() > t['crypto_stale_hours']*3600
    et = now.astimezone(ET)
    expected = et.date() if et.hour >= 18 else et.date()-timedelta(days=1)
    return market_sessions(d, expected, calendar) > t['max_missing_sessions']


def calculate(item, points, source, error, now, thresholds):
    if not points:
        return {**item,'value':None,'change_1':None,'change_20':None,'as_of':None,'source':source,'status':'missing','error':error,'interpretation':'数据暂不可用，等待有效行情'}
    latest=points[-1]['value']
    def delta(n):
        if len(points)<=n: return None
        prev=points[-1-n]['value']
        if item['kind'] in ('yield','spread'): return (latest-prev)*100
        if item['kind']=='points': return latest-prev
        return (latest/prev-1)*100 if prev else None
    stale=is_stale(points[-1]['date'],item['calendar'],now,thresholds)
    data={**item,'value':latest*100 if item['kind']=='spread' else latest,'change_1':delta(1),'change_20':delta(20),'as_of':points[-1]['date'],'source':source,'status':'stale' if stale else ('error' if error else 'ok'),'error':error}
    data['interpretation']=interpret(data, thresholds)
    return data


def interpret(x,t):
    v=x['value']; c=x['change_20']; k=x['id']
    if x['status'] in ('stale','missing'): return '数据暂未更新，截至'+(x['as_of'] or '未知')
    if c is None: return '近20期数据不足，暂不解读方向'
    if k=='dxy': return '美元走强，关注全球风险资产压力' if c>=t['dxy_pct'] else '美元走弱，外部美元压力可能缓解' if c<=-t['dxy_pct'] else '美元阶段性震荡，方向尚不明显'
    if k=='us2y': return '短端利率下行，市场可能增加降息定价' if c<=t['two_year_down_bp'] else '短端利率上行，政策利率预期偏紧' if c>=t['two_year_up_bp'] else '短端利率变化有限，关注政策预期'
    if k=='us10y': return '长期融资及估值折现压力上升' if c>=t['long_bp'] else '长期收益率回落，需辨别增长与避险驱动' if c<=-t['long_bp'] else '长端利率基本稳定，关注后续变化'
    if k=='real10y': return '实际利率上行，黄金及高估值资产或承压' if c>0 else '实际利率下行，相关估值压力缓解' if c<0 else '实际利率基本稳定，关注后续变化'
    if k in ('spread10y2y','spread10y3m'):
        prefix='仍处倒挂' if v<0 else '当前为正利差'
        suffix='，曲线变陡' if c>=t['curve_bp'] else '，曲线变平' if c<=-t['curve_bp'] else '，曲线变化有限'
        return prefix+suffix+('；正斜率不等于衰退风险消失' if k=='spread10y3m' else '')
    if k=='vix': return '波动率预期上升，风险偏好降温' if c>=t['vix_pt'] else '波动预期回落，关注市场风险变化' if c<=-t['vix_pt'] else '波动预期变化有限，关注市场风险'
    if k=='hy': return '信用风险溢价扩大，关注风险扩散' if c>=t['hy_bp'] else '信用风险溢价回落，关注信用环境' if c<=-t['hy_bp'] else '信用市场相对稳定，关注利差变化'
    if k in ('usdjpy','usdcnh'):
        target='日元' if k=='usdjpy' else '离岸人民币'
        return ('美元相对'+target+'升值，关注汇率波动') if c>0 else ('美元相对'+target+'贬值，关注汇率波动') if c<0 else '汇率近20期基本持平，关注后续变化'
    direction='上涨' if c>=t['asset_pct'] else '下跌' if c<=-t['asset_pct'] else '震荡'
    notes={'sp500':'关注大盘风险偏好','nasdaq100':'成长及科技权重较高','gold':'需结合实际利率与美元判断','wti':'关注能源供需变化','copper':'关注工业需求变化','btc':'关注价格波动','eth':'关注价格波动'}
    return '近20期'+direction+'，'+notes.get(k,'关注后续走势')


def curve_drivers(cards, histories, t):
    # Drivers must use endpoints common to the published curve and both yields.
    for sid, short in [('spread10y2y','us2y'),('spread10y3m','aux3m')]:
        card=cards[sid]
        if card['status'] in ('missing','stale') or card['change_20'] is None or card['change_20']<t['curve_bp']: continue
        curve=histories.get(sid,[])
        if len(curve)<21: continue
        a,b=curve[-21]['date'],curve[-1]['date']
        if card['as_of']!=b: continue
        long={p['date']:p['value'] for p in histories.get('us10y',[])}
        shortmap={p['date']:p['value'] for p in histories.get(short,[])}
        if not all(d in long and d in shortmap for d in (a,b)): continue
        dl=(long[b]-long[a])*100; ds=(shortmap[b]-shortmap[a])*100
        driver='短端下降更快' if ds<0 and dl<=0 and ds<dl else '长端上升更快' if dl>0 and ds>=0 and dl>ds else '长短端混合驱动'
        card['interpretation']+='；'+driver


def classify(cards,t):
    required=['dxy','real10y','us2y','hy','vix']
    missing=[cards[k]['name'] for k in required if cards[k]['change_20'] is None or cards[k]['value'] is None or cards[k]['status'] in ('stale','missing')]
    if missing: return {'state':'数据不足：暂不判断','reason':'关键数据缺失或过期：'+'、'.join(missing),'uncertainty':'无法可靠判断，等待有效数据','signals':[]}
    d=cards['dxy']['change_20']; r=cards['real10y']['change_20']; y=cards['us2y']['change_20']; h=cards['hy']['change_20']; v=cards['vix']['change_20']; hn=cards['hy']['value']; vn=cards['vix']['value']
    credit=h>=t['hy_bp']; vol=v>=t['vix_pt']
    if credit and vol: state='金融压力扩散'; reason='信用利差与波动率共同上升，市场防御需求增强'
    elif y<=t['two_year_down_bp'] and (credit or vol): state='增长担忧定价'; reason='短端利率下行，但信用或波动信号恶化；降息预期未必利好风险资产'
    elif d>=t['dxy_pct'] and r>=t['real_bp']: state='金融条件趋紧'; reason='美元和实际利率同步上行，估值及融资环境压力增加'
    elif d<=-t['dxy_pct'] and r<=-t['real_bp'] and not credit and not vol and hn<t['hy_high_bp'] and vn<t['vix_high']: state='温和宽松'; reason='美元和实际利率下降，信用及波动风险尚未同步恶化'
    else:
        state='中性/信号分歧'
        dollar='走强' if d>=t['dxy_pct'] else '走弱' if d<=-t['dxy_pct'] else '震荡'
        real='上行' if r>=t['real_bp'] else '下行' if r<=-t['real_bp'] else '变化有限'
        risk='信用或波动恶化' if credit or vol else '信用和波动未显著恶化'
        reason=f'美元{dollar}、实际利率{real}；{risk}，信号未形成一致方向'
    uncertainty = '信用或波动风险仍处高位' if hn>=t['hy_high_bp'] or vn>=t['vix_high'] else ('信用利差暂未显著恶化' if not credit else '信用风险溢价仍在扩大')
    signals=[f'美元近20期 {d:+.2f}%',f'实际利率 {r:+.0f}bp',f'信用利差 {h:+.0f}bp / VIX {v:+.1f}点']
    return {'state':state,'reason':reason,'uncertainty':uncertainty,'signals':signals}


def atomic(path, obj):
    text=json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
        f.write(text); f.flush(); os.fsync(f.fileno()); name=f.name
    os.replace(name,path)


def run(now=None):
    now=now or datetime.now(UTC)
    out=ROOT/'data'; out.mkdir(exist_ok=True)
    hp=out/'history.json'; sp=out/'snapshot.json'
    history=json.loads(hp.read_text(encoding='utf-8')) if hp.exists() else {'series':{}}
    if not isinstance(history.get('series'),dict): raise ValueError('existing history invalid; refusing to overwrite')
    if sp.exists():
        old=json.loads(sp.read_text(encoding='utf-8'))
        if not isinstance(old.get('indicators'),list): raise ValueError('existing snapshot invalid; refusing to overwrite')
    series=history['series']; sources=history.get('sources',{}); errors={}; success=0
    items=CONFIG['indicators']+[{'id':'aux3m','provider':'fred','symbol':'DGS3MO','calendar':'bond'}]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch,item,now):item for item in items}
        for future in concurrent.futures.as_completed(futures):
            item=futures[future]; k=item['id']
            try:
                points,source=future.result(); prior=observations(series.get(k,[])); combined=observations(prior+points)
                # A provider may return an older period; merge without erasing valid history.
                series[k]=combined[-120:]; sources[k]=source; success+=1
            except Exception as e:
                errors[k]='数据源网络请求失败' if isinstance(e,requests.RequestException) else str(e)[:160]; LOG.warning('%s: %s',k,errors[k])
    if not success and sp.exists():
        atomic(out/'last_attempt.json',{'at':now.isoformat(),'status':'failed','message':'所有数据源更新失败，保留上次快照'})
        return False
    cards={item['id']:calculate(item,observations(series.get(item['id'],[])),sources.get(item['id']),errors.get(item['id']),now,CONFIG['thresholds']) for item in CONFIG['indicators']}
    curve_drivers(cards,series,CONFIG['thresholds'])
    for sid,short in [('spread10y2y','us2y'),('spread10y3m','aux3m')]:
        a={p['date']:p['value'] for p in series.get('us10y',[])}; b={p['date']:p['value'] for p in series.get(short,[])}
        c=cards[sid]; d=c['as_of']
        if d in a and d in b and abs(c['value']-(a[d]-b[d])*100)>CONFIG['thresholds']['spread_check_bp']:
            LOG.warning('%s official spread differs from same-date yields',sid); c['warning']='官方利差与同日收益率计算值不一致'
    # Prepare a calendar for the client to re-evaluate freshness even when scheduled updates fail.
    year=now.astimezone(ET).year; nyse=xcals.get_calendar('XNYS',start=f'{year-2}-12-01',end=f'{year+2}-01-31')
    days=nyse.sessions_in_range(f'{year-1}-01-01',f'{year+1}-12-31')
    calendar={'nyse':[str(d.date()) for d in days], 'bond_holidays':[d.isoformat() for d in holidays.US(years=[year-1,year,year+1])]}
    snapshot={'generated_at':now.isoformat(),'timezone':'Asia/Tokyo','indicators':list(cards.values()),'macro':classify(cards,CONFIG['thresholds']),'thresholds':CONFIG['thresholds'],'calendar':calendar,'sources_failed':len(errors)}
    atomic(hp,{'series':series,'sources':sources}); atomic(sp,snapshot)
    atomic(out/'last_attempt.json',{'at':now.isoformat(),'status':'partial' if errors else 'ok','message':f'{len(errors)} 项来源未更新' if errors else '更新完成'})
    return True

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try: sys.exit(0 if run() else 1)
    except Exception:
        LOG.exception('更新失败；快照未被新数据替换')
        try: atomic(ROOT/'data'/'last_attempt.json',{'at':datetime.now(UTC).isoformat(),'status':'failed','message':'更新失败，保留上次快照'})
        except Exception: pass
        sys.exit(1)
