import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from src.api.contracts_guide_lab import create_app
from src.app.services.contracts_guide_lab import ContractsGuideLab
from src.app.services.guide_lab_settings import GuideSettings, GuideSettingsStore, FIXED_GUARD
from src.app.services.guide_lab_console import GuideLabConsole
from src.app.services.guide_lab_sessions import GuideSessionStore


class Brain:
    def _request_json(self, method, path, payload=None):
        if path == '/api/lab/status':
            return {'database':'connected', 'events':[]}
        if path == '/api/lab/knowledge':
            return {'documents':[], 'graph':{'nodes':[], 'edges':[]}}
        return {'evidencePacket':{'meta':{'revision':'rev:one'},'query':{'workspaceId':'lab'},
            'citations':[{'id':'doc','evidenceId':'doc','uri':'guide/SuggestedSuppliers.md','startLine':1,'endLine':2}],
            'data':{'evidence':[{'evidence':{'id':'doc','kind':'document','content':'انتخاب منبع جدید را بزنید.',
                'metadata':{'resource':{'attributes':{'sourceHash':'a'*64}}}}}]}}}


def setup(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    store = GuideSettingsStore(tmp_path / 'state', provider='none')
    service = ContractsGuideLab(Brain(), 'lab', 'rev:one', tmp_path/'traces/contracts-guide-lab-1',
                                settings_store=store, provider_key='fake-private-key',
                                session_store=GuideSessionStore(tmp_path / 'state' / 'sessions'))
    return service, GuideLabConsole(service, project, tmp_path/'state')


def test_settings_persist_history_and_conflicts(tmp_path):
    store = GuideSettingsStore(tmp_path)
    old = store.get()
    updated = GuideSettings(**{**old['settings'], 'system_prompt':'راهنمای مرحله به مرحله با حفظ همه شرط‌ها.', 'max_document_chunks':3})
    new = store.save(old['revision'], updated)
    assert new['revision'] != old['revision']
    assert GuideSettingsStore(tmp_path).get()['settings']['max_document_chunks'] == 3
    assert (tmp_path/'settings-history'/f"{old['revision']}.json").exists()
    with pytest.raises(ValueError):
        store.save(old['revision'], updated)
    with pytest.raises(ValueError):
        GuideSettings(model='../../../private', token='secret')


def test_changed_prompt_is_sent_and_snapshotted_per_turn(tmp_path):
    service, _ = setup(tmp_path)
    old = service.settings_store.get()
    data = GuideSettings(**{**old['settings'], 'provider':'gemini', 'system_prompt':'همه پیش‌نیازها و شرط‌ها را به ترتیب بنویسید.', 'max_document_chunks':1})
    service.settings_store.save(old['revision'], data)
    def generated(writer, prompt):
        assert writer.settings['system_prompt'] == data.system_prompt
        return {'steps':[{'text':'انتخاب منبع جدید را بزنید.','citation_ids':['doc']}], 'clarification':'', 'usage':{'totalTokenCount':10}}
    with patch('src.app.services.contracts_guide_lab.GeminiGuideWriter.generate', generated):
        response = service.answer('چطور منابع پیشنهادی را اضافه کنم؟')
    trace = json.loads((service.trace_dir/f"{response['trace_id']}.json").read_text(encoding='utf-8'))
    assert response['model_called'] and trace['settings_snapshot']['system_prompt'] == data.system_prompt
    assert data.system_prompt in trace['system_prompt'] and FIXED_GUARD in trace['system_prompt']
    assert 'fake-private-key' not in json.dumps(trace)
    assert [e['stage'] for e in trace['events']] == ['policy','topic','retrieval_started','retrieval_finished','evidence_selected','generation_started','generation_finished','citation_validation_started','citation_validation','finished']


def test_console_mutations_require_header_and_revision(tmp_path):
    service, console = setup(tmp_path)
    with TestClient(create_app(service, console)) as client:
        assert 'dir="rtl"' in client.get('/').text
        assert client.get('/api/status').json()['provider'] == 'none'
        saved = client.get('/api/console/settings').json()
        body = {'revision':saved['revision'], 'settings':saved['settings']}
        assert client.put('/api/console/settings',json=body).status_code == 403
        saved['settings']['max_document_chunks'] = 2
        body['settings'] = saved['settings']
        assert client.put('/api/console/settings',json=body,headers={'X-Guide-Console':'1'}).status_code == 200
        assert client.put('/api/console/settings',json=body,headers={'X-Guide-Console':'1'}).status_code == 409
        assert client.get('/api/console/overview').json()['database'] == 'connected'
        assert 'fake-private-key' not in client.get('/api/console/overview').text
        assert client.post('/api/console/jobs',json={'kind':'arbitrary-shell'},headers={'X-Guide-Console':'1'}).status_code == 422
        assert client.put('/api/console/settings',json=body,headers={'X-Guide-Console':'1','Origin':'https://evil.example'}).status_code == 403


def test_chat_keeps_session_and_page_context(tmp_path):
    service, console = setup(tmp_path)
    with TestClient(create_app(service, console)) as client:
        created = client.post('/api/sessions', json={'page_context': {
            'page_route': '/tenders/42', 'entity_type': 'tender',
            'tenant_id': 'must-not-be-stored', 'data': {'step': 'evaluation', 'token': 'secret'},
        }})
        assert created.status_code == 200
        session_id = created.json()['id']
        response = client.post('/api/chat', json={
            'question': 'چطور منابع پیشنهادی را اضافه کنم؟',
            'session_id': session_id,
            'page_context': {'page_route': '/tenders/42', 'data': {'step': 'evaluation'}},
        })
        assert response.status_code == 200
        assert response.json()['session_id'] == session_id
        loaded = client.get('/api/sessions/' + session_id).json()
        assert [message['role'] for message in loaded['messages']] == ['user', 'assistant']
        assert loaded['page_context']['data'] == {'step': 'evaluation'}
        assert 'tenant_id' not in loaded['page_context']
        assert 'token' not in json.dumps(loaded, ensure_ascii=False)


def test_trace_paths_and_local_review_dont_promote_evidence(tmp_path):
    service, console = setup(tmp_path)
    response = service.answer('هوا چطور است؟')
    assert console.traces()['items'][0]['question'] == 'هوا چطور است؟'
    assert console.trace('contracts-guide-lab-1',response['trace_id'])['response']['review_status']=='pending-human'
    with pytest.raises(ValueError):
        console.trace('../../private',response['trace_id'])
    console.save_review('Q05','کارشناس آزمایشی','needs_changes','مرحله حذف نیاز به بررسی دارد.')
    assert console.reviews()['Q05']['decision']=='needs_changes'
    assert service.answer('هوا چطور است؟')['review_status']=='pending-human'
    with pytest.raises(ValueError):
        console.save_review('../../private','بازبین','approved','')


def test_interrupted_jobs_marked_and_one_job_at_a_time(tmp_path):
    service, console = setup(tmp_path)
    console.current='busy'
    with pytest.raises(ValueError,match='job_running'):
        console.start_job('unit-tests')
    console.current=None
    with pytest.raises(ValueError,match='evaluation_requires_gemini'):
        console.start_job('evaluate-all')
    jobdir=console.state_dir/'jobs'
    jobdir.mkdir()
    (jobdir/'old.json').write_text(json.dumps({'id':'old','status':'running'}),encoding='utf-8')
    restored=GuideLabConsole(service,console.project_dir,console.state_dir)
    assert restored.jobs()[0]['status']=='interrupted'


def test_resync_during_retrieval_keeps_answer_revision_pinned(tmp_path):
    service, _ = setup(tmp_path)
    brain = service.client
    def retrieve(method, path, payload=None):
        service.revision = 'rev:two'
        return brain._request_json(method, path, payload)
    service.client = type('ConcurrentBrain', (), {'_request_json': staticmethod(retrieve)})()
    answer = service.answer('چطور منابع پیشنهادی را اضافه کنم؟')
    assert service.revision == 'rev:two'
    assert answer['revision'] == 'rev:one' and answer['status'] == 'partial'
    trace = json.loads((service.trace_dir / (answer['trace_id'] + '.json')).read_text(encoding='utf-8'))
    assert trace['revision'] == 'rev:one'
