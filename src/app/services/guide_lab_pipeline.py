"""Observable execution state, updated by real service events while work runs."""
import json
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone
import re

NODES = [('policy','کنترل دامنه'),('topic','انتخاب منابع'),('retrieval','بازیابی Brain'),
         ('selection','شواهد مجاز'),('generation','Gemini'),('validation','کنترل استناد'),('answer','پاسخ')]


class GuidePipeline:
    def __init__(self, directory: Path):
        self.directory, self.lock = directory, RLock()
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob('*.json'):
            run=json.loads(path.read_text(encoding='utf-8'))
            if run['status']=='running':
                run['status']='interrupted'
                for node in run['nodes']:
                    if node['status']=='running':node['status']='failed'
                self._save(run)

    def _save(self, run):
        path=self.directory / (run['id']+'.tmp')
        path.write_text(json.dumps(run,ensure_ascii=False,indent=2),encoding='utf-8')
        path.replace(self.directory / (run['id']+'.json'))

    def begin(self, trace_id, question, revision=None, settings_revision=None):
        with self.lock:
            run={'id':trace_id,'question':question,'revision':revision,'settings_revision':settings_revision,
                 'started_at':datetime.now(timezone.utc).isoformat(),'status':'running','events':[],
                 'nodes':[{'id':id,'label':label,'status':'pending'} for id,label in NODES]}
            self._save(run)
            return run

    def get(self, trace_id):
        if not re.fullmatch(r'[a-f0-9]{32}',trace_id):raise ValueError('invalid_run_id')
        return json.loads((self.directory/(trace_id+'.json')).read_text(encoding='utf-8'))

    def list(self):
        files=sorted(self.directory.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        return [{key:run.get(key) for key in ['id','question','started_at','status','revision','settings_revision']}
                for run in (json.loads(p.read_text(encoding='utf-8')) for p in files)]

    def active(self):
        return any(run['status']=='running' for run in self.list())

    def event(self, trace_id, stage, elapsed_ms, **details):
        with self.lock:
            run=self.get(trace_id)
            nodes={node['id']:node for node in run['nodes']}
            mapping={'policy':('policy','running'),'topic':('topic','passed'),
                     'retrieval_started':('retrieval','running'),'retrieval_finished':('retrieval','passed'),
                     'evidence_selected':('selection','passed'),'generation_started':('generation','running'),
                     'generation_finished':('generation','passed'),'citation_validation_started':('validation','running'),'citation_validation':('validation','passed'),
                     'finished':('answer','passed')}
            if stage in mapping:
                target,status=mapping[stage]
                for node in nodes.values():
                    if node['status']=='running' and node['id']!=target:
                        node.update(status='passed',ended_ms=elapsed_ms)
                node=nodes[target]
                node.setdefault('started_ms',elapsed_ms)
                node.update(status=status,details={**node.get('details',{}),**details})
                if status=='passed':node['ended_ms']=elapsed_ms
            if stage=='error':
                for node in nodes.values():
                    if node['status']=='running':node.update(status='failed',ended_ms=elapsed_ms,details=details)
                run['status']='failed'
            if stage=='finished':
                response=details.pop('response',None)
                if response is not None:run['response']=response
                run['status']='failed' if details.get('status')=='escalate' else 'passed'
                if run['status']=='failed':nodes['answer']['status']='failed'
                for node in nodes.values():
                    if node['status']=='pending':node['status']='skipped'
                run['duration_ms']=elapsed_ms
            run['events'].append({'stage':stage,'elapsed_ms':elapsed_ms,**details})
            self._save(run)

    def complete(self, trace_id, response, elapsed_ms):
        self.event(trace_id,'finished',elapsed_ms,status=response['status'],response=response)
