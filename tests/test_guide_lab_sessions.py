from src.app.services.guide_lab_sessions import (
    GuideSessionStore,
    sanitize_page_context,
)


def test_page_context_is_allowlisted_and_secrets_are_removed(tmp_path):
    context = sanitize_page_context({
        "page_route": "/contracts/42",
        "page_title": "قرارداد",
        "entity_id": "42",
        "tenant_id": "must-not-enter",
        "data": {"status": "draft", "access_token": "secret", "step": "review"},
        "arbitrary": "ignored",
    })
    assert context == {
        "page_route": "/contracts/42",
        "page_title": "قرارداد",
        "entity_id": "42",
        "data": {"status": "draft", "step": "review"},
    }


def test_sessions_group_messages_and_keep_context(tmp_path):
    store = GuideSessionStore(tmp_path / "sessions")
    session = store.create({"page_route": "/tenders", "data": {"step": "evaluation"}})
    store.append_user(session["id"], "مرحله ارزیابی کجاست؟", session["page_context"])
    store.append_assistant(session["id"], {
        "answer": "به صفحه ارزیابی بروید.",
        "status": "partial",
        "trace_id": "trace-1",
        "steps": [{"text": "صفحه ارزیابی را باز کنید.", "citation_ids": ["doc-1"]}],
        "citations": [{"id": "doc-1", "title": "راهنما", "url": "/api/evidence/x/y"}],
    })
    loaded = store.get(session["id"])
    assert loaded["page_context"]["data"] == {"step": "evaluation"}
    assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]
    assert loaded["messages"][1]["steps"][0]["text"].startswith("صفحه")
    assert store.list()[0]["id"] == session["id"]


def test_invalid_session_id_is_rejected(tmp_path):
    store = GuideSessionStore(tmp_path / "sessions")
    assert store.get("../outside") is None
