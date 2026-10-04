import json
from threading import Event, Thread
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.api.contracts_guide_lab import create_app
from src.integrations.code_kb_client import CodeKbError
from src.app.services.guide_lab_settings import GuideSettings
from src.app.services.guide_lab_pipeline import GuidePipeline
from tests.test_guide_lab_console import setup, Brain


def test_crud_bridge_validates_ids_and_preserves_owner_conflicts(tmp_path):
    service,console=setup(tmp_path)
    calls=[]
    def request(method,path,payload=None):
        calls.append((method,path,payload))
        if payload.get('version')=='b'*64:raise CodeKbError('private server details',status=409,body={'error':'knowledge_conflict'})
        return {'dirty':True,'draftVersion':'c'*64}
    service.client=type('Owner',(),{'_request_json':staticmethod(request)})()
    with TestClient(create_app(service,console)) as client:
        body={'version':'a'*64,'value':{'content':'guide'}}
        assert client.post('/api/console/knowledge/documents/New.md',json=body).status_code==403
        headers={'X-Guide-Console':'1'}
        assert client.post('/api/console/knowledge/documents/New.md',json=body,headers=headers).status_code==200
        assert calls[-1][1]=='/api/lab/knowledge/documents/New.md'
        assert client.request('DELETE','/api/console/knowledge/documents/New.md',json={'version':'a'*64},headers=headers).status_code==200
        assert calls[-1][0]=='DELETE'
        assert client.put('/api/console/knowledge/graph/wrong/id',json=body,headers=headers).status_code==422
        body['version']='b'*64
        result=client.put('/api/console/knowledge/documents/New.md',json=body,headers=headers)
        assert result.status_code==409 and result.json()['detail']=='knowledge_conflict'
        assert 'private server details' not in result.text
        console.current='publication'
        assert client.post('/api/console/knowledge/documents/New.md',json=body,headers=headers).status_code==409


def test_pipeline_is_observable_while_generation_waits(tmp_path):
    service,console=setup(tmp_path)
    old=service.settings_store.get()
    service.settings_store.save(old['revision'],GuideSettings(**{**old['settings'],'provider':'gemini'}))
    entered,release=Event(),Event()
    def generate(writer,prompt):
        entered.set();assert release.wait(5)
        return {'steps':[{'text':'انتخاب منبع جدید را بزنید.','citation_ids':['doc']}],'clarification':''}
    with patch('src.app.services.contracts_guide_lab.GeminiGuideWriter.generate',generate):
        with TestClient(create_app(service,console)) as client:
            response=client.post('/api/console/pipeline/start',json={'question':'چطور منابع پیشنهادی را اضافه کنم؟'},headers={'X-Guide-Console':'1'})
            assert response.status_code==202
            run_id=response.json()['id']
            try:
                assert entered.wait(5)
                live=client.get('/api/console/pipeline/runs/'+run_id).json()
                nodes={n['id']:n for n in live['nodes']}
                assert live['status']=='running' and nodes['generation']['status']=='running'
                assert nodes['retrieval']['status']=='passed'
                assert json.loads(nodes['generation']['details']['prompt'])['question']=='چطور منابع پیشنهادی را اضافه کنم؟'
                duplicate=client.post('/api/console/pipeline/start',json={'question':'چطور منابع پیشنهادی را اضافه کنم؟'},headers={'X-Guide-Console':'1'})
                assert duplicate.status_code==409
            finally:release.set()
            # Wait for the bounded local worker, without calling a provider.
            finished=Event()
            def wait():
                import time
                for _ in range(100):
                    if console.pipeline.get(run_id)['status']!='running':finished.set();return
                    time.sleep(.01)
            thread=Thread(target=wait);thread.start();assert finished.wait(3);thread.join()
            run=client.get('/api/console/pipeline/runs/'+run_id).json()
            assert run['status']=='passed' and run['response']['model_called']
            generation=next(n for n in run['nodes'] if n['id']=='generation')
            assert generation['details']['prompt'] and generation['details']['output']['steps']


def test_skipped_stages_and_interrupted_runs_are_honest(tmp_path):
    service,console=setup(tmp_path)
    response=service.answer('مدیریت امنیت و انتقال پست را بگو')
    run=console.pipeline.get(response['trace_id'])
    assert run['response']['status']=='refuse'
    assert next(n for n in run['nodes'] if n['id']=='generation')['status']=='skipped'
    console.pipeline.begin('f'*32,'unfinished')
    console.pipeline.event('f'*32,'retrieval_started',12)
    restarted=GuidePipeline(console.pipeline.directory)
    assert restarted.get('f'*32)['status']=='interrupted'


def test_managed_document_changes_reach_retrieval_but_permission_blocks_export(tmp_path):
    service,console=setup(tmp_path)
    service.managed_knowledge=True
    old=service.settings_store.get()
    service.settings_store.save(old['revision'],GuideSettings(**{**old['settings'],'provider':'gemini'}))
    class ManagedBrain(Brain):
        allow=False
        def _request_json(self,method,path,payload=None):
            if 'catalog?' in path:
                return {'documents':[{'name':'Custom.md','keywords':['راهنمای جدید'],'externalEligible':self.allow,'sourceHash':'a'*64}]}
            result=super()._request_json(method,path,payload)
            result['evidencePacket']['citations'][0]['uri']='guide/Custom.md'
            return result
    brain=ManagedBrain();service.client=brain
    with patch('src.app.services.contracts_guide_lab.GeminiGuideWriter.generate') as model:
        response=service.answer('راهنمای جدید را بگو')
        assert not response['model_called'] and response['local_document_notes']
        model.assert_not_called()
    brain.allow=True
    with patch('src.app.services.contracts_guide_lab.GeminiGuideWriter.generate',return_value={'steps':[{'text':'انتخاب منبع جدید را بزنید.','citation_ids':['doc']}],'clarification':''}):
        response=service.answer('راهنمای جدید را بگو')
    assert response['model_called'] and response['steps']
    trace=json.loads((service.trace_dir/(response['trace_id']+'.json')).read_text(encoding='utf-8'))
    assert trace['prompt_evidence'][0]['uri']=='guide/Custom.md'


def test_managed_catalog_hash_mismatch_fails_closed(tmp_path):
    service,_=setup(tmp_path);service.managed_knowledge=True
    class ChangedBrain(Brain):
        def _request_json(self,method,path,payload=None):
            if 'catalog?' in path:return {'documents':[{'name':'SuggestedSuppliers.md','keywords':[],'externalEligible':True,'sourceHash':'wrong'}]}
            return super()._request_json(method,path,payload)
    service.client=ChangedBrain()
    response=service.answer('چطور منابع پیشنهادی را اضافه کنم؟')
    assert response['status']=='escalate' and not response['model_called']
