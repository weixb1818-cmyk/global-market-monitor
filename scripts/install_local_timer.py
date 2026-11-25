#!/usr/bin/env python3
"""Install/remove only this project's cron block; retain unrelated jobs and backup."""
import argparse
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

BEGIN = '# BEGIN global-market-monitor host timer'
END = '# END global-market-monitor host timer'


def without_block(text):
    if BEGIN not in text and END not in text:
        return text
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('ambiguous managed cron markers')
    start = text.index(BEGIN); end = text.index(END) + len(END)
    if end < start: raise ValueError('invalid managed cron markers')
    if end < len(text) and text[end] == '\n': end += 1
    return text[:start] + text[end:]


def render(text, root, remove=False):
    kept = without_block(text)
    if remove: return kept
    runtime = root / '.runtime' / 'market-timer'
    lines = [BEGIN, '# Host timezone must be Asia/Shanghai (checked by installer).']
    for hour, minute in ((8,15),(8,45),(10,15)):
        cmd = ['/usr/bin/python3', str(root/'scripts/local_trigger.py'), '--slot', f'{hour:02d}:{minute:02d}']
        lines.append(f'{minute} {hour} * * * ' + shlex.join(cmd) + ' >> ' + shlex.quote(str(runtime/'cron.log')) + ' 2>&1')
    lines.append(END)
    return kept + ('' if not kept or kept.endswith('\n') else '\n') + '\n'.join(lines) + '\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--remove', action='store_true')
    args=p.parse_args();root=args.root.resolve();os.umask(0o077)
    # Debian/Ubuntu cron uses the host zone; do not assume it implements CRON_TZ.
    zone=subprocess.check_output(['/usr/bin/timedatectl','show','-p','Timezone','--value'],text=True).strip()
    if not args.remove and zone!='Asia/Shanghai':raise SystemExit('Host timezone must be Asia/Shanghai; no changes made')
    if not args.remove:
        if not (root/'scripts/local_trigger.py').is_file():raise SystemExit('Trigger script missing')
        subprocess.run(['/usr/bin/gh','api','repos/weixb1818-cmyk/global-market-monitor','--silent'],check=True)
        subprocess.run(['/usr/bin/systemctl','is-active','--quiet','cron'],check=True)
    current=subprocess.run(['/usr/bin/crontab','-l'],capture_output=True,text=True)
    if current.returncode not in (0,1):raise SystemExit('Cannot read crontab')
    old=current.stdout
    new=render(old,root,args.remove)
    runtime=root/'.runtime'/'market-timer';runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=runtime/('crontab-before-'+datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.txt')
    backup.write_text(old)
    subprocess.run(['/usr/bin/crontab','-'],input=new,text=True,check=True)
    installed=subprocess.check_output(['/usr/bin/crontab','-l'],text=True)
    if installed!=new:raise SystemExit('Crontab readback differs; inspect private backup')
    print('Removed' if args.remove else 'Installed', 'managed timer block; unrelated jobs retained; private backup:',backup)


if __name__=='__main__':main()
