#!/usr/bin/env python3
"""Read the actual Pages deployment and retain evidence of its real trigger."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def validate_publication(data, attempt, *, expected_at=None, run_url=None,
                         event=None, schedule=None, data_outcome='success', origin=None, dispatch_id=None, planned_at=None):
    if len(data['indicators']) != 17:
        raise ValueError('wrong indicator count')
    if expected_at and data['generated_at'] != expected_at:
        raise ValueError('CDN still serves an earlier snapshot')
    ctx = attempt.get('update_context', {})
    if run_url and ctx.get('run_url') != run_url:
        raise ValueError('CDN still serves an earlier update record')
    if event and ctx.get('event') != event:
        raise ValueError('published trigger differs from the actual GitHub event')
    if ctx.get('event') == 'schedule' and ctx.get('schedule') != schedule:
        raise ValueError('published cron differs from the actual GitHub schedule')
    for key, expected in [('origin', origin), ('dispatch_id', dispatch_id), ('planned_at', planned_at)]:
        if expected and ctx.get(key) != expected:
            raise ValueError('published trigger metadata mismatch: ' + key)
    if data_outcome == 'success':
        if data.get('update_context') != ctx:
            raise ValueError('snapshot and update record belong to different runs')
        if attempt.get('status') not in ('ok', 'partial'):
            raise ValueError('successful update has no successful data record')
    elif attempt.get('status') != 'failed':
        raise ValueError('failed update must be explicitly marked as failed')
    native = ctx.get('event') == 'schedule' and ctx.get('schedule') == '15 0 * * *'
    return {
        'generated_at': data['generated_at'], 'cards': 17,
        'macro': data['macro']['state'], 'mode': data['macro'].get('mode'),
        'update_context': ctx, 'attempt_status': attempt.get('status'),
        'data_updated': data_outcome == 'success',
        'native_daily_schedule_verified': native and data_outcome == 'success',
        'result': 'public readback verified',
    }


def main():
    base = os.environ['DASHBOARD_URL'].rstrip('/') + '/'
    for attempt in range(8):
        try:
            def get(path):
                req = Request(base + path + '?check=' + str(time.time_ns()), headers={
                    'Cache-Control': 'no-cache', 'User-Agent': 'MarketDashboard-PublishVerifier/1.1'})
                with urlopen(req, timeout=20) as response:
                    if response.status != 200:
                        raise ValueError(f'{path}: HTTP {response.status}')
                    return response.read()
            if '全球市场每日观察' not in get('index.html').decode('utf-8'):
                raise ValueError('wrong index document')
            for name in ('app.js', 'styles.css'):
                if not get(name):
                    raise ValueError('empty asset')
            result = validate_publication(
                json.loads(get('data/snapshot.json')), json.loads(get('data/last_attempt.json')),
                expected_at=os.getenv('EXPECTED_GENERATED_AT'), run_url=os.getenv('EXPECTED_RUN_URL'),
                event=os.getenv('EXPECTED_EVENT'), schedule=os.getenv('EXPECTED_SCHEDULE') or None,
                data_outcome=os.getenv('EXPECTED_DATA_OUTCOME', 'success'),
                origin=os.getenv('EXPECTED_ORIGIN'), dispatch_id=os.getenv('EXPECTED_DISPATCH_ID'),
                planned_at=os.getenv('EXPECTED_PLANNED_AT'))
            result.update(url=base, checked_at=datetime.now(timezone.utc).isoformat())
            output = Path('verification/publication.json')
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
            if os.getenv('GITHUB_STEP_SUMMARY'):
                label = '已验证原生每日定时取数及公网发布' if result['native_daily_schedule_verified'] else '本次不构成原生每日定时更新成功的证据'
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
                    summary.write(f"{label}。\n\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n")
            return
        except Exception as exc:
            if attempt == 7:
                raise
            print(f'Publication propagation check {attempt + 1}: {type(exc).__name__}; retrying')
            time.sleep(5)


if __name__ == '__main__':
    main()
