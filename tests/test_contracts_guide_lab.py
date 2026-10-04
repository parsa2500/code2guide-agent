import json
import pytest

from fastapi.testclient import TestClient

from src.api.contracts_guide_lab import create_app
from src.app.services.contracts_guide_lab import ContractsGuideLab, restricted_question


def packet():
    items = [
        ("doc", "guide/SuggestedSuppliers.md", "از فرم منابع پیشنهادی، انتخاب منبع جدید را بزنید."),
        ("code", "guide/q05-code-links.md", "شرط نمایش دکمه در کد؛ منبع: View.cshtml:1-3؛ SHA-256: abc"),
        ("admin", "guide/SuggestedSuppliers.md", "برای تنظیم دسترسی وارد مدیریت امنیت شوید."),
        ("other", "guide/Claims.md", "پرونده دعاوی را ثبت کنید."),
    ]
    return {"evidencePacket": {"meta": {"revision": "rev:one"}, "query": {"workspaceId": "lab"},
        "citations": [{"id": id, "evidenceId": id, "uri": uri, "title": id, "startLine": 1, "endLine": 3} for id, uri, _ in items],
        "data": {"evidence": [{"evidence": {"id": id, "kind": "document", "content": content,
            "metadata": {"resource": {"attributes": {"sourceHash": "a" * 64, "reviewStatus": "pending-human"}}}}} for id, _, content in items]}}}


class Brain:
    def __init__(self):
        self.calls = []
        self.response = packet()

    def _request_json(self, method, path, payload):
        self.calls.append((method, path, payload))
        return self.response


class Writer:
    model = "fake-test-model"

    def __init__(self, ids=None):
        self.ids = ["doc"] if ids is None else ids
        self.prompt = None

    def generate(self, prompt):
        self.prompt = prompt
        return {"answer": "unused", "steps": [{"text": "انتخاب منبع جدید را بزنید.", "citation_ids": self.ids}], "clarification": "هیچ ابهامی وجود ندارد."}


def test_pinned_retrieval_uses_documents_and_keeps_code_local(tmp_path):
    brain, writer = Brain(), Writer()
    service = ContractsGuideLab(brain, "lab", "rev:one", tmp_path, writer)
    result = service.answer("چگونه منابع پیشنهادی را اضافه کنم؟")
    assert result["status"] == "partial"  # pending-human never becomes answered
    assert result["role"] is None and result["app_version"] is None
    assert result["code_notes"] and result["steps"]
    assert result["clarification"] == ""
    assert brain.calls[0][2]["revisionId"] == "rev:one"
    selected = json.loads(writer.prompt)["evidence"]
    assert [x["id"] for x in selected] == ["doc"]
    assert "View.cshtml" not in writer.prompt
    saved = json.loads((tmp_path / f"{result['trace_id']}.json").read_text(encoding="utf-8"))
    assert saved["model_prompt"] == writer.prompt
    assert saved["code_evidence_local_only"][0]["id"] == "code"
    assert service.evidence(result["trace_id"], "doc")["source_hash"] == "a" * 64


def test_role_administration_and_unknown_topic_do_not_query_brain(tmp_path):
    brain, writer = Brain(), Writer()
    service = ContractsGuideLab(brain, "lab", "rev:one", tmp_path, writer)
    assert service.answer("دسترسی کاربران را چطور تنظیم کنم؟")["status"] == "refuse"
    assert service.answer("هوا چطور است؟")["status"] == "clarify"
    assert not brain.calls and writer.prompt is None


def test_wrong_workspace_or_revision_fails_closed(tmp_path):
    brain, writer = Brain(), Writer()
    service = ContractsGuideLab(brain, "lab", "rev:one", tmp_path, writer)
    brain.response["evidencePacket"]["meta"]["revision"] = "rev:other"
    assert service.answer("منابع پیشنهادی چیست؟")["status"] == "escalate"
    assert writer.prompt is None
    brain.response = packet()
    brain.response["evidencePacket"]["query"]["workspaceId"] = "another-tenant"
    assert service.answer("منابع پیشنهادی چیست؟")["status"] == "escalate"
    assert writer.prompt is None


def test_fabricated_or_missing_model_citations_are_rejected(tmp_path):
    for ids in [["invented"], [], ["code"]]:
        result = ContractsGuideLab(Brain(), "lab", "rev:one", tmp_path, Writer(ids)).answer("منابع پیشنهادی چیست؟")
        assert result["status"] == "escalate" and result["steps"] == []


def test_provider_exception_does_not_leak_error_or_secret(tmp_path):
    class Broken(Writer):
        def generate(self, prompt):
            raise RuntimeError("sensitive-token-123")
    result = ContractsGuideLab(Brain(), "lab", "rev:one", tmp_path, Broken()).answer("منابع پیشنهادی چیست؟")
    saved = (tmp_path / f"{result['trace_id']}.json").read_text(encoding="utf-8")
    assert result["status"] == "escalate" and "sensitive-token-123" not in saved


def test_ui_evidence_and_origin_boundary(tmp_path):
    service = ContractsGuideLab(Brain(), "lab", "rev:one", tmp_path)
    with TestClient(create_app(service)) as client:
        assert 'dir="rtl"' in client.get("/").text
        response = client.post("/api/chat", json={"question": "منابع پیشنهادی را اضافه کنم؟"})
        assert response.status_code == 200
        data = response.json()
        assert data["model_called"] is False and data["status"] == "partial"
        assert client.get(data["citations"][0]["url"]).json()["excerpt"]
        assert client.get("/api/evidence/invalid/doc").status_code == 404
        assert client.post("/api/chat", headers={"Origin": "https://evil.example"}, json={"question": "منابع پیشنهادی"}).status_code == 403
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 403


def test_empty_retrieval_abstains_without_provider(tmp_path):
    brain, writer = Brain(), Writer()
    brain.response["evidencePacket"]["citations"] = []
    result = ContractsGuideLab(brain, "lab", "rev:one", tmp_path, writer).answer("منابع پیشنهادی چیست؟")
    assert result["status"] == "clarify" and writer.prompt is None


@pytest.mark.parametrize("question", [
    "دسترسی‌های کاربری در سامانه قراردادها کجاست و چگونه تنظیم می‌شوند؟",
    "تنظیم سطح دسترسی کاربران سامانه قراردادها چگونه است؟",
    "دسترسي هاي كاربران در سامانه قراردادها کجاست و چگونه تنظیم می شوند؟",
])
def test_long_administration_question_hands_off_without_model(tmp_path, question):
    brain, writer = Brain(), Writer()
    result = ContractsGuideLab(brain, "lab", "rev:one", tmp_path, writer).answer(question)
    assert result["status"] == "refuse" and "راهبر" in result["answer"]
    assert not result["steps"] and not result["model_called"]
    assert not brain.calls and writer.prompt is None


def test_permission_prerequisite_is_not_administration():
    assert not restricted_question("برای ویرایش قالب مستندات چه دسترسی لازم است؟")
