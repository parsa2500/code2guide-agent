"""Real Brain HTTP + actual Code2Guide routes; one optional Gemini call, no gold input."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from src.api.contracts_guide_lab import app_factory

report = {"status": "running", "provider": os.environ.get("GUIDE_LAB_PROVIDER", "none"), "humanReviewed": False}
try:
    with TestClient(app_factory()) as client:
        assert 'dir="rtl"' in client.get("/").text
        status = client.get("/api/status").json()
        report.update(workspace=status["workspace"], revision=status["revision"], model=status["model"])
        q05 = client.post("/api/chat", json={"question": "چطور منابع پیشنهادی را به درخواست اضافه کنم و به فهرست شرکت‌کنندگان انتقال بدهم؟"})
        assert q05.status_code == 200
        answer = q05.json()
        report["q05"] = {"status": answer["status"], "citations": len(answer["citations"]), "codeNotes": len(answer["code_notes"]), "steps": len(answer["steps"]), "modelCalled": answer["model_called"], "traceId": answer["trace_id"]}
        trace = json.loads((Path(os.environ["GUIDE_LAB_TRACE_DIR"]) / f"{answer['trace_id']}.json").read_text(encoding="utf-8"))
        report["providerDiagnostics"] = {k: trace[k] for k in ["error_type", "provider_http_status", "provider_error_code"] if k in trace}
        assert answer["status"] == "partial", answer["status"]
        assert answer["code_notes"], 'Q05 source link did not reach response'
        assert any(c["uri"].endswith('/SuggestedSuppliers.md') for c in answer["citations"])
        for c in answer["citations"]:
            assert client.get(c["url"]).json()["source_hash"] == c["source_hash"]
        if report["provider"] == "gemini":
            assert answer["steps"] and answer["model_called"]
            trace = json.loads((Path(os.environ["GUIDE_LAB_TRACE_DIR"]) / f"{answer['trace_id']}.json").read_text(encoding="utf-8"))
            assert all(c['uri'].endswith('/SuggestedSuppliers.md') for c in trace['prompt_evidence'])
            assert 'q05-code-links.md' not in trace['model_prompt']
            report["usage"] = trace.get("usage")
        refused = client.post("/api/chat", json={"question": "دسترسی کاربران را چگونه تنظیم کنم؟"}).json()
        assert refused["status"] == "refuse" and not refused["model_called"]
        report["adminRefusal"] = True
        assert client.post("/api/chat", json={"question": "هوا چگونه است؟"}).json()["status"] == "clarify"
        report["unknownTopicClarification"] = True
        report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", errorType=type(exc).__name__, error=str(exc)[:200])
    raise
finally:
    target = Path(os.environ["GUIDE_LAB_REPORT"])
    contents = json.dumps(report, ensure_ascii=False, indent=2)
    if report.get("workspace"):
        target.with_name(f"{target.stem}-{report['workspace']}.json").write_text(contents, encoding="utf-8")
    target.write_text(contents, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
