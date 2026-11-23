#!/usr/bin/env python3
"""Fetch and validate daily close observations; never invent a quote."""
from __future__ import annotations
import concurrent.futures, csv, io, json, logging, math, os, re, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from xml.etree import ElementTree
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
        result[d] = {'date':d,'value':val}
        if 'components' in row: result[d]['components'] = row['components']
    return [v for d, v in sorted(result.items())]


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


def ecb_usdjpy(now):
    response = requests.get('https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml', timeout=18)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    rows = []
    for day in root.iter():
        if not day.get('time'): continue
        rates = {c.get('currency'):float(c.get('rate')) for c in day if c.get('currency') in ('USD','JPY')}
        if set(rates) != {'USD','JPY'}: continue
        if any(not math.isfinite(v) or v <= 0 for v in rates.values()):
            raise ValueError('ECB汇率必须为正有限值')
        rows.append({'date':day.get('time'),'value':rates['JPY']/rates['USD']})
    if not rows: raise ValueError('ECB缺少同日USD和JPY参考汇率')
    return observations(rows), 'ECB / 同日EURJPY÷EURUSD / 日参考汇率，非收盘'


def frankfurter(item, now):
    base, quote = item['symbol'].split('/')
    if (base,quote) not in (('XAU','USD'),('USD','CNH')):
        raise ValueError('未核实的参考汇率品种')
    asset = 'CNH' if quote == 'CNH' else 'XAU'
    meta = request_json('https://api.frankfurter.dev/v2/currency/'+asset.lower())
    expected_name = 'offshore' if asset == 'CNH' else 'troy ounce'
    if meta.get('iso_code') != asset or expected_name not in meta.get('name','').lower():
        raise ValueError('参考序列品种不符；CNH必须为离岸人民币，XAU必须为金衡盎司')
    body = request_json('https://api.frankfurter.dev/v2/rates', {
        'base':base,'quotes':quote,'from':(now.date()-timedelta(days=130)).isoformat(),
        'to':(now.date()-timedelta(days=1)).isoformat(),'expand':'providers'})
    if not isinstance(body,list): raise ValueError('参考汇率历史格式无效')
    rows = []
    for row in body:
        if row.get('base') != base or row.get('quote') != quote:
            raise ValueError('拒绝不同货币对；不使用CNY替代CNH')
        d = date.fromisoformat(row['date'])
        if d >= now.date(): continue
        value = float(row['rate'])
        if not math.isfinite(value) or value <= 0: raise ValueError('参考汇率必须为正有限值')
        parts = [{'provider':p['key'],'date':date.fromisoformat(p['date']).isoformat()}
                 for p in row.get('providers',[]) if not p.get('excluded')]
        if not parts: raise ValueError('缺少合成序列的来源日期')
        if any(p['date'] > d.isoformat() for p in parts): raise ValueError('来源日期晚于参考序列日期')
        # Do not manufacture fresh observations by carrying an entirely older blend forward.
        if not any(p['date'] == d.isoformat() for p in parts): continue
        rows.append({'date':d.isoformat(),'value':value,'components':parts})
    return observations(rows), 'Frankfurter / '+item['symbol']+' / 多源合成参考价，非收盘'


def definition_key(item):
    return '|'.join(str(item.get(k,'')) for k in ('provider','symbol','unit','series_definition'))


def prepare_history(history, items, old_snapshot):
    definitions = history.setdefault('definitions',{})
    old = {c['id']:c for c in old_snapshot.get('indicators',[])}
    for item in items:
        key = item['id']; current = definition_key(item)
        prior = definitions.get(key) or (definition_key(old[key]) if key in old else None)
        if prior is not None and prior != current:
            history['series'].pop(key,None)
            history.setdefault('sources',{}).pop(key,None)
            LOG.warning('%s: 指标口径改变，清除旧序列，禁止拼接不同品种或报价口径',key)
        definitions[key] = current


def sina_dxy(item, now):
    if item['symbol'] != 'DXY' or item.get('vendor_symbol') != 'DINIW':
        raise ValueError('只接受DINIW美元指数，不使用美元期货或其他美元指数')
    headers = {'Referer':'https://finance.sina.com.cn/'}
    quote = requests.get('https://hq.sinajs.cn/list=DINIW', headers=headers, timeout=18)
    quote.raise_for_status(); quote.encoding = 'gb18030'
    if not re.fullmatch(r'\s*var hq_str_DINIW="[^"\r\n]*,美元指数,[^"\r\n]*";\s*',quote.text):
        raise ValueError('新浪DINIW品种元数据不符')
    response = requests.get('https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var%20_DATA=/NewForexService.getDayKLine',
                            params={'symbol':'DINIW'},headers=headers,timeout=18)
    response.raise_for_status()
    # Parse a JSON string inside a fixed JSONP envelope; never execute downloaded JavaScript.
    match = re.fullmatch(r'\s*(?:/\*.*?\*/\s*)?var _DATA=\(("(?:[^"\\]|\\.)*")\);?\s*',response.text,re.S)
    if not match: raise ValueError('新浪DXY历史格式已变化')
    rows = []
    seen = set()
    for record in json.loads(match.group(1)).split('|'):
        fields = record.split(',')
        if len(fields) < 5: raise ValueError('新浪DXY日线字段不足')
        day = date.fromisoformat(fields[0]).isoformat()
        op,low,high,close = map(float,fields[1:5])
        if day in seen or not all(math.isfinite(v) and v > 0 for v in (op,low,high,close)) or not low <= min(op,close) <= max(op,close) <= high:
            raise ValueError('新浪DXY日线重复或价格异常')
        seen.add(day); rows.append({'date':day,'value':close})
    return observations(rows), '新浪财经 / DINIW / 美元指数日线，非DX期货'


class CopperHistoryError(ValueError):
    pass


def copper_history_check(rows):
    dates = [date.fromisoformat(p['date']) for p in rows]
    unique = set(dates)
    expected = set(session_dates(min(dates),max(dates),'cme')) if dates else set()
    missing = sorted(d.isoformat() for d in expected-unique)
    unexpected = sorted(d.isoformat() for d in unique-expected)
    ordered = dates == sorted(dates)
    valid = len(dates) == len(unique) and ordered and not missing and not unexpected
    return {'id':'copper','status':('ok' if valid else 'warning') if dates else 'missing',
            'observations':len(dates),'unique_dates':len(unique),'ascending':ordered,
            'first_date':min(dates).isoformat() if dates else None,
            'last_date':max(dates).isoformat() if dates else None,
            'expected_cme_sessions':len(expected),'missing_sessions':missing,
            'unexpected_dates':unexpected,'rollover_rule_verified':False}


def validate_copper_history(rows):
    check = copper_history_check(rows)
    problems = []
    if check['observations'] != check['unique_dates']: problems.append('日期重复')
    if not check['ascending']: problems.append('日期未升序排列')
    if check['missing_sessions']: problems.append('缺少CME交易日：'+','.join(check['missing_sessions'][:5]))
    if check['unexpected_dates']: problems.append('非CME交易日：'+','.join(check['unexpected_dates'][:5]))
    if problems: raise CopperHistoryError('铜历史完整性异常：'+'；'.join(problems))
    return check


def eastmoney_copper(item, now):
    if item['symbol'] != 'HG00Y' or item['unit'] != 'USD/lb':
        raise ValueError('只接受COMEX铜HG00Y，单位USD/lb')
    info = request_json('https://futsse-static.eastmoney.com/redis',{'msgid':'101_4_info'})
    quote_unit = re.sub(r'\s+','',info.get('bjdw',''))
    if info.get('vcode') != 'HG' or info.get('vname') != 'COMEX铜' or quote_unit not in ('美元/磅','美元和美分/磅'):
        raise ValueError('东方财富铜品种或报价单位不符')
    tick = re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*美元\s*/\s*磅\s*',info.get('zxbddw',''))
    if not tick or float(tick.group(1)) != 0.0005:
        raise ValueError('东方财富铜最小变动价位不符，应为0.0005美元/磅')
    # Historical service may fail independently of the quote service. Never fill
    # history using previous settlement, CFDs, or prices from another contract.
    try:
        body = request_json('https://push2his.eastmoney.com/api/qt/stock/kline/get',{
            'secid':'101.HG00Y','klt':101,'fqt':0,'lmt':100,'end':'20500101',
            'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56'})
        data = body.get('data') or {}
        if data.get('code') != 'HG00Y' or data.get('name') != 'COMEX铜' or data.get('market') != 101:
            raise ValueError('东方财富铜日线品种不符')
        rows = []
        for record in data.get('klines',[]):
            fields = record.split(',')
            day = date.fromisoformat(fields[0])
            op,close,high,low = map(float,fields[1:5])
            if not all(math.isfinite(v) and v>0 for v in (op,close,high,low)) or not low <= min(op,close) <= max(op,close) <= high:
                raise ValueError('东方财富铜日线价格异常')
            # The daily service carries an intraday row too. Use only days before
            # today in New York; today's completed observation comes next run.
            if day < now.astimezone(ET).date(): rows.append({'date':day.isoformat(),'value':close})
        if rows:
            # Check the supplier's ordering and duplicates before observations()
            # could normalize them. A gap is an error, never a synthetic price.
            validate_copper_history(rows)
            return observations(rows), '东方财富 / 101.HG00Y / COMEX铜日线；供数方换月序列'
    except CopperHistoryError:
        raise  # Preserve the previous valid history and expose the source error.
    except (requests.RequestException,ValueError,KeyError,TypeError,IndexError):
        LOG.warning('copper: 历史接口不可用，尝试已收盘末笔快照；不伪造历史')
    body = request_json('https://push2.eastmoney.com/api/qt/stock/get',{
        'secid':'101.HG00Y','fields':'f43,f57,f58,f59,f86,f107'})
    q = body.get('data') or {}
    if q.get('f57') != 'HG00Y' or q.get('f58') != 'COMEX铜' or q.get('f107') != 101 or q.get('f59') != 4:
        raise ValueError('东方财富铜快照品种或精度不符')
    stamp = datetime.fromtimestamp(float(q['f86']),UTC); et = stamp.astimezone(ET)
    # Accept only the supplier's 17:00 New York end-of-session timestamp.
    # This is a closing snapshot, not the exchange's official settlement.
    if stamp > now or (et.hour,et.minute) != (17,0) or not session_dates(et.date(),et.date(),'cme'):
        raise ValueError('铜快照不是已完成交易时段，拒绝把盘中价格当收盘')
    value = float(q['f43'])/10**q['f59']
    if not math.isfinite(value) or value <= 0: raise ValueError('铜快照价格无效')
    return [{'date':et.date().isoformat(),'value':value}], '东方财富 / 101.HG00Y / 纽约17:00收盘末笔快照，非官方结算；逐日积累历史'



def barchart_dxy(item, now):
    # Official paid API only; never scrape a website or substitute DXY futures.
    if os.getenv('MARKET_DATA_DXY_URL'):
        return external(item, now)
    key = os.getenv('BARCHART_API_KEY')
    if not key:
        raise ValueError('DXY需ICE或Barchart现货指数授权；未配置BARCHART_API_KEY或DXY授权源')
    symbol = item['vendor_symbol']
    quote = request_json('https://ondemand.websol.barchart.com/getQuote.json', {'apikey':key,'symbols':symbol})
    results = quote.get('results') or []
    if quote.get('status',{}).get('code') != 200 or len(results) != 1:
        raise ValueError('Barchart DXY授权或品种元数据不可用')
    q = results[0]
    if q.get('symbol') != symbol or 'dollar index cash' not in q.get('name','').lower():
        raise ValueError('拒绝非DXY现货指数品种；不能使用期货或其他美元指数')
    body = request_json('https://ondemand.websol.barchart.com/getHistory.json', {'apikey':key,'symbol':symbol,'type':'daily','startDate':(now.date()-timedelta(days=130)).strftime('%Y%m%d'),'maxRecords':100,'order':'asc'})
    if body.get('status',{}).get('code') != 200 or not body.get('results'):
        raise ValueError('Barchart DXY日线权限不足或无有效历史')
    if any(row.get('symbol') != symbol for row in body['results']):
        raise ValueError('Barchart历史返回了不同品种')
    return observations([{'date':r['tradingDay'],'value':r['close']} for r in body['results']]), 'Barchart / DXY00 / ICE美元现货指数日线'


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
    elif item['provider']=='barchart': result = barchart_dxy(item, now)
    elif item['provider']=='ecb': result = ecb_usdjpy(now)
    elif item['provider']=='frankfurter': result = frankfurter(item, now)
    elif item['provider']=='sina': result = sina_dxy(item, now)
    elif item['provider']=='eastmoney': result = eastmoney_copper(item, now)
    else: result = external(item, now)
    points, source = result
    # US prices on the current date are usable only after their completed session.
    et = now.astimezone(ET)
    cutoff = 17 if item['provider'] in ('external','twelve') else 18
    max_date = et.date() if et.hour >= cutoff else et.date()-timedelta(days=1)
    if item['calendar']=='crypto': max_date = now.astimezone(UTC).date()-timedelta(days=1)
    if item['provider']=='twelve': max_date = now.astimezone(UTC).date()-timedelta(days=1)
    if item['provider'] in ('ecb','frankfurter'): max_date = now.astimezone(UTC).date()-timedelta(days=1)
    if item['provider']=='sina':
        # Conservative one-day lag avoids accepting a still-forming DXY daily bar.
        # Friday's ICE session ends at 17:00 ET, Mon-Thu at 19:15 ET.
        max_date = et.date()-timedelta(days=1)
    points = [p for p in points if date.fromisoformat(p['date']) <= max_date]
    if not points: raise ValueError('无已完成交易时段的有效数据')
    return points[-120:], (item.get('source_label')+' / '+item['symbol']) if item.get('source_label') else source


def session_dates(start, end, calendar):
    if end < start: return []
    if calendar == 'forex':
        return [start+timedelta(days=i) for i in range((end-start).days+1)
                if (start+timedelta(days=i)).weekday()<5 and (start+timedelta(days=i)).strftime('%m-%d') not in ('01-01','12-25')]
    name = 'CMES' if calendar == 'cme' else 'XNYS'
    cal = xcals.get_calendar(name,start=(start-timedelta(days=8)).isoformat(),end=(end+timedelta(days=8)).isoformat())
    dates = [d.date() for d in cal.sessions_in_range(start.isoformat(),end.isoformat())]
    if calendar == 'bond':
        federal = holidays.US(years=range(start.year,end.year+1))
        dates = [d for d in dates if d not in federal]
    return dates


def market_sessions(start, end, calendar):
    return len(session_dates(start+timedelta(days=1),end,calendar)) if end>start else 0


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
    data={**item,'value':latest*100 if item['kind']=='spread' else latest,'change_1':delta(1),'change_20':delta(20),'as_of':points[-1]['date'],'observation_count':len(points),'source':source,'status':'stale' if stale else ('error' if error else 'ok'),'error':error}
    if points[-1].get('components'):
        data['source_components'] = points[-1]['components']
    data['interpretation']=interpret(data, thresholds)
    if not stale and item['id']=='vix' and data['value']>=thresholds['vix_high']:
        data['interpretation']+='；波动率仍处高位'
    if not stale and item['id']=='hy' and data['value']>=thresholds['hy_high_bp']:
        data['interpretation']+='；信用利差仍处高位'
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
    if k=='gold' and x.get('series_definition')=='gold-blended-reference-v1':
        return '合成参考近20期'+direction+'，不等同现货收盘'
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


def risk_levels(cards, t):
    alerts=[]
    for key, threshold, unit, label in [('vix',t['vix_high'],'点','波动率处于较高水平'),('hy',t['hy_high_bp'],'bp','信用利差处于较高水平')]:
        c=cards.get(key,{})
        if c.get('value') is not None and c.get('status') not in ('stale','missing') and c['value']>=threshold:
            alerts.append({'id':key,'as_of':c.get('as_of'),'value':c['value'],'unit':unit,'message':label})
    return alerts


def classify(cards,t):
    required=['dxy','real10y','us2y','hy','vix']
    def invalid(k):
        c=cards.get(k,{})
        return c.get('change_20') is None or c.get('value') is None or c.get('status') in ('stale','missing')
    missing=[k for k in required if invalid(k)]
    dates={k:cards[k].get('as_of') for k in required if k in cards and not invalid(k)}
    alerts=risk_levels(cards,t)
    base={'complete':not missing,'mode':'full' if not missing else 'insufficient','missing':[cards.get(k,{}).get('name',k) for k in missing],'signal_dates':dates,'risk_alerts':alerts}
    non_dxy=[k for k in missing if k!='dxy']
    if non_dxy:
        return {**base,'state':'数据不足：暂不判断','reason':'关键数据缺失或过期：'+'、'.join(base['missing']),'uncertainty':'无法可靠判断；仅展示仍有效的绝对风险水平','signals':[]}
    r=cards['real10y']['change_20']; y=cards['us2y']['change_20']; h=cards['hy']['change_20']; v=cards['vix']['change_20']; hn=cards['hy']['value']; vn=cards['vix']['value']
    credit=h>=t['hy_bp']; vol=v>=t['vix_pt']
    def signal(k,text):
        return text+(' · '+dates[k] if dates.get(k) else '')
    signals=[signal('real10y',f'实际利率 {r:+.0f}bp'),signal('hy',f'HY {h:+.0f}bp'),signal('vix',f'VIX {v:+.1f}点')]
    if missing:  # Only DXY unavailable: four remaining inputs are individually valid.
        if credit and vol: reason='信用利差与波动率共同上升，关注金融压力信号'
        elif y<=t['two_year_down_bp'] and (credit or vol): reason='短端利率下降且信用或波动恶化，关注增长担忧信号'
        elif vol: reason='波动率上升，风险偏好降温；信用尚未共同恶化'
        elif credit: reason='信用利差扩大，关注信用风险变化'
        elif r>=t['real_bp']: reason='实际利率上行，估值与融资成本压力增加'
        else: reason='信用与波动未共同恶化；不能据此确认整体宽松'
        return {**base,'mode':'limited','state':'有限风险提示','reason':reason,'uncertainty':'DXY缺失或过期，结论不完整；不判断美元相关整体金融条件','signals':signals}
    d=cards['dxy']['change_20']
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
    uncertainty='信用或波动风险仍处高位' if alerts else ('信用利差暂未显著恶化' if not credit else '信用风险溢价仍在扩大')
    ds=[date.fromisoformat(x) for x in dates.values() if x]
    if ds and (max(ds)-min(ds)).days>t.get('macro_date_gap_days',3): uncertainty+='；信号日期跨度较大，请逐项核对'
    return {**base,'state':state,'reason':reason,'uncertainty':uncertainty,'signals':[signal('dxy',f'美元 {d:+.2f}%'),signals[0],signal('hy',f'HY {h:+.0f}bp')+' / '+signal('vix',f'VIX {v:+.1f}点')], 'signal_dates':dates}


def compare_spreads(cards, series, t):
    checks=[]
    for sid,short in [('spread10y2y','us2y'),('spread10y3m','aux3m')]:
        a={p['date']:p['value'] for p in series.get('us10y',[])}; b={p['date']:p['value'] for p in series.get(short,[])}
        c=cards[sid]; d=c['as_of']
        if c['value'] is None or d not in a or d not in b:
            checks.append({'id':sid,'as_of':d,'status':'not_comparable','reason':'尚未完成同日底层交叉核验：缺少同一日期的长短端收益率，未跨日期相减'})
            continue
        computed=(a[d]-b[d])*100; difference=abs(c['value']-computed)
        status='warning' if difference>t['spread_check_bp'] else 'ok'
        checks.append({'id':sid,'as_of':d,'status':status,'official_bp':c['value'],'same_date_bp':computed,'difference_bp':difference})
        if status=='warning':
            LOG.warning('%s official spread differs from same-date yields',sid)
            c['warning']='官方利差与同日收益率计算值不一致'
    return checks


def update_context():
    return {'event':os.getenv('TRIGGER_EVENT','local'),'schedule':os.getenv('TRIGGER_SCHEDULE') or None,'run_url':os.getenv('WORKFLOW_RUN_URL') or None}


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
    old = {}
    if sp.exists():
        old=json.loads(sp.read_text(encoding='utf-8'))
        if not isinstance(old.get('indicators'),list): raise ValueError('existing snapshot invalid; refusing to overwrite')
    items=CONFIG['indicators']+[{'id':'aux3m','provider':'fred','symbol':'DGS3MO','calendar':'bond'}]
    prepare_history(history,items,old)
    series=history['series']; sources=history.setdefault('sources',{}); errors={}; success=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch,item,now):item for item in items}
        for future in concurrent.futures.as_completed(futures):
            item=futures[future]; k=item['id']
            try:
                points,source=future.result(); prior=observations(series.get(k,[])); combined=observations(prior+points)
                if k=='copper': validate_copper_history(combined[-120:])
                # A provider may return an older period; merge without erasing valid history.
                series[k]=combined[-120:]; sources[k]=source; success+=int(k!='aux3m')
            except Exception as e:
                errors[k]='数据源网络请求失败' if isinstance(e,requests.RequestException) else str(e)[:160]; LOG.warning('%s: %s',k,errors[k])
    if not success and sp.exists():
        atomic(out/'last_attempt.json',{'at':now.isoformat(),'status':'failed','message':'所有数据源更新失败，保留上次快照','update_context':update_context()})
        return False
    cards={item['id']:calculate(item,observations(series.get(item['id'],[])),sources.get(item['id']),errors.get(item['id']),now,CONFIG['thresholds']) for item in CONFIG['indicators']}
    curve_drivers(cards,series,CONFIG['thresholds'])
    spread_checks=compare_spreads(cards,series,CONFIG['thresholds'])
    # Prepare a calendar for the client to re-evaluate freshness even when scheduled updates fail.
    year=now.astimezone(ET).year
    first=date(year-1,1,1);last=date(year+1,12,31)
    calendar={k:[d.isoformat() for d in session_dates(first,last,k)] for k in ('nyse','bond','forex','cme')}
    # Retain this field for older clients during CDN propagation.
    calendar['bond_holidays']=[d.isoformat() for d in holidays.US(years=[year-1,year,year+1])]
    limited_cards={**cards,'dxy':{**cards['dxy'],'value':None,'change_20':None,'status':'missing'}}
    snapshot={'generated_at':now.isoformat(),'timezone':'Asia/Tokyo','indicators':list(cards.values()),'macro':classify(cards,CONFIG['thresholds']),'limited_macro':classify(limited_cards,CONFIG['thresholds']),'risk_alerts':risk_levels(cards,CONFIG['thresholds']),'spread_checks':spread_checks,'history_checks':[copper_history_check(series.get('copper',[]))],'thresholds':CONFIG['thresholds'],'calendar':calendar,'sources_failed':sum(k in errors for k in cards),'update_context':update_context()}
    atomic(hp,{'series':series,'sources':sources,'definitions':history['definitions']}); atomic(sp,snapshot)
    atomic(out/'last_attempt.json',{'at':now.isoformat(),'status':'partial' if errors else 'ok','message':f'{sum(k in errors for k in cards)} 项来源未更新' if errors else '更新完成','update_context':update_context()})
    return True

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try: sys.exit(0 if run() else 1)
    except Exception:
        LOG.exception('更新失败；快照未被新数据替换')
        try: atomic(ROOT/'data'/'last_attempt.json',{'at':datetime.now(UTC).isoformat(),'status':'failed','message':'更新失败，保留上次快照','update_context':update_context()})
        except Exception: pass
        sys.exit(1)
