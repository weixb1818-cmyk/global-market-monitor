#!/usr/bin/env python3
"""Host cron dispatches the existing GitHub workflow; no local market fetching."""
import argparse
import fcntl
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

try:
    from .schedule_audit import gate
except ImportError:
    from schedule_audit import gate

REPO = 'weixb1818-cmyk/global-market-monitor'
SITE = 'https://weixb1818-cmyk.github.io/global-market-monitor'
SLOTS = ('08:15', '08:45', '10:15')
BJT = ZoneInfo('Asia/Shanghai')
ACTIVE = {'queued', 'in_progress', 'waiting', 'pending', 'requested'}


def gh_api(endpoint, payload=None):
    cmd = ['/usr/bin/gh', 'api', endpoint]
    if payload is not None:
        cmd += ['--method', 'POST', '--input', '-']
    result = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        # Keep credential-bearing subprocess environment and response text private.
        raise RuntimeError(f'GitHub API command failed (exit {result.returncode})')
    return json.loads(result.stdout) if result.stdout.strip() else None


def planned(now, slot):
    h, m = map(int, slot.split(':'))
    return now.astimezone(BJT).replace(hour=h, minute=m, second=0, microsecond=0)


def decision(now, slot, attempt, runs, state, verify=False):
    target = planned(now, slot)
    if not verify and not target <= now <= target + timedelta(minutes=10):
        return 'skip_outside_slot_window'
    if any(r.get('status') in ACTIVE for r in runs):
        return 'skip_workflow_active'
    if not verify and state:
        return 'skip_slot_already_attempted'
    # Only a published, healthy update whose entire workflow succeeded suppresses
    # another automatic update. A partial source failure remains retryable.
    if not verify and not gate('workflow_dispatch', None, attempt, now, origin='host_cron'):
        url = attempt.get('update_context', {}).get('run_url')
        if any(r.get('html_url') == url and r.get('conclusion') == 'success' for r in runs):
            return 'skip_healthy_published_day'
    return 'dispatch'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--slot', required=True, choices=SLOTS)
    p.add_argument('--verify', action='store_true', help='explicit diagnostic; bypass slot and daily health guards')
    p.add_argument('--runtime-dir', type=Path, default=Path(__file__).resolve().parents[1] / '.runtime' / 'market-timer')
    args = p.parse_args()
    os.umask(0o077)
    args.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.runtime_dir / 'trigger.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'result': 'skip_local_trigger_active'})); return
        now = datetime.now(timezone.utc)
        key = planned(now, args.slot).strftime('%Y-%m-%d_%H%M')
        state_path = args.runtime_dir / f'{key}.json'
        log_path = args.runtime_dir / 'events.jsonl'
        record = {'requested_at': now.isoformat(), 'planned_at': planned(now, args.slot).isoformat(),
                  'origin': 'host_timer_test' if args.verify else 'host_cron',
                  'dispatch_id': key + '-' + uuid.uuid4().hex[:12]}
        def emit():
            line = json.dumps(record, ensure_ascii=False)
            with log_path.open('a') as f:
                f.write(line + '\n'); f.flush(); os.fsync(f.fileno())
            print(line, flush=True)
        try:
            runs = gh_api(f'repos/{REPO}/actions/workflows/update.yml/runs?per_page=100')['workflow_runs']
            try:
                with urlopen(Request(SITE + '/data/last_attempt.json?timer=' + uuid.uuid4().hex,
                                     headers={'Cache-Control': 'no-cache'}), timeout=20) as r:
                    attempt = json.load(r)
            except Exception:
                attempt = {}  # unknown public state is not evidence of success
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            action = decision(now, args.slot, attempt, runs, state, args.verify)
            record['result'] = action
            if action != 'dispatch':
                emit(); return
            # Persist intent BEFORE a possibly ambiguous network response. Never
            # blindly repeat this slot; next compensation checks cloud state again.
            if not args.verify:
                state_path.write_text(json.dumps(record) + '\n')
            emit()
            inputs = {k: record[k] for k in ('origin', 'dispatch_id', 'planned_at', 'requested_at')}
            inputs['force'] = args.verify
            gh_api(f'repos/{REPO}/actions/workflows/update.yml/dispatches', {'ref': 'main', 'inputs': inputs})
            record.update(result='dispatch_accepted', accepted_at=datetime.now(timezone.utc).isoformat())
            if not args.verify:
                state_path.write_text(json.dumps(record) + '\n')
            emit()
        except Exception as exc:
            record.update(result='trigger_error_or_ambiguous', error_type=type(exc).__name__,
                          finished_at=datetime.now(timezone.utc).isoformat())
            emit()
            raise SystemExit(1)


if __name__ == '__main__':
    main()
