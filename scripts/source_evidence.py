"""Small per-run evidence ledger. No credentials or restricted quote bodies."""
import hashlib
import json
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

KNOWN_HOSTS = {'api.frankfurter.dev','www.ecb.europa.eu','fred.stlouisfed.org','api.stlouisfed.org',
               'api.coingecko.com','hq.sinajs.cn','vip.stock.finance.sina.com.cn',
               'futsse-static.eastmoney.com','push2his.eastmoney.com','push2.eastmoney.com'}
SAFE_PARAMS = {'id','series_id','symbol','symbols','base','quotes','from','to','expand','secid','klt','fqt','lmt','end','msgid','cosd','observation_start','days','interval','vs_currency','file_type','fields','fields1','fields2','outputsize','startDate','maxRecords','order','type'}


class Evidence:
    def __init__(self, root, context):
        self.root=Path(root); self.started_at=datetime.now(timezone.utc).isoformat()
        try:self.code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root,text=True,stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:self.code_commit=None
        try:self.working_tree_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=self.root,text=True,stderr=subprocess.DEVNULL).strip())
        except subprocess.CalledProcessError:self.working_tree_dirty=None
        self.context=context; self.requests=[]; self.outcomes=[]; self.lock=threading.Lock(); self.local=threading.local()

    def set_item(self, item): self.local.item=item['id']

    def record(self, url, params, response, started, error=None):
        parts=urlsplit(url)
        entry={'indicator':getattr(self.local,'item',None),'requested_at':started,
               'completed_at':datetime.now(timezone.utc).isoformat(),
               'endpoint':parts.scheme+'://'+(parts.hostname or '[invalid-host]')+(parts.path if parts.hostname in KNOWN_HOSTS else '/[redacted]'),
               'params':{k:v for k,v in (params or {}).items() if k in SAFE_PARAMS},
               'status':None,'response_sha256':None,'error_type':type(error).__name__ if error else None}
        if response is not None:
            body=response.content
            if isinstance(body,bytes):
                entry.update(status=response.status_code,response_sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
                entry['server_date']=response.headers.get('Date'); entry['content_type']=response.headers.get('Content-Type')
                # ECB permits reuse of statistical information with attribution.
                # Only bounded XML from this public endpoint is archived by default.
                if parts.hostname=='www.ecb.europa.eu' and parts.path.startswith('/stats/eurofxref/') and response.status_code==200 and len(body)<=131072:
                    name='ecb-'+entry['response_sha256']+'.xml'; path=self.root/'data'/'raw'/name
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
                    entry['raw_path']='data/raw/'+name
                    entry['raw_reuse_basis']='https://www.ecb.europa.eu/services/disclaimer/html/index.en.html'
        with self.lock: self.requests.append(entry)

    def outcome(self, key, points=None, error=None):
        with self.lock:
            self.outcomes.append({'id':key,'status':'error' if error else 'ok','error':error,
                'source_first_date':points[0]['date'] if points else None,
                'source_last_date':points[-1]['date'] if points else None,'observations':len(points or [])})

    def finish(self, snapshot_path, history_path, revisions):
        result={'started_at':self.started_at,'completed_at':datetime.now(timezone.utc).isoformat(),
                'code_commit':self.code_commit,'working_tree_dirty_at_start':self.working_tree_dirty,'update_context':self.context,'requests':self.requests,'outcomes':self.outcomes,'revisions':revisions,
                'generated_files':{str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [snapshot_path,history_path] if p.exists()},
                'raw_policy':'Only bounded public ECB statistical XML retained; other responses have metadata/hash only, not an implied redistribution permission.'}
        return result


def revisions(prior, current):
    old={p['date']:p for p in prior}; result=[]
    for p in current:
        if p['date'] in old and p['value']!=old[p['date']]['value']:
            result.append({'date':p['date'],'old_value':old[p['date']]['value'],'new_value':p['value'],
                           'old_components':old[p['date']].get('components'), 'new_components':p.get('components')})
    return result
