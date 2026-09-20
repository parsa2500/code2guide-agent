"""Update job and chat API tests with mocked knowledge/agent."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_workspace(client, tmp_path: Path) -> str:
    ws_path = tmp_path / "proj"
    ws_path.mkdir()
    res = client.post(
        "/api/v1/workspaces",
        json={"name": "P", "path": str(ws_path), "description": ""},
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_update_job_background(app_client, tmp_path: Path):
    ws_id = _make_workspace(app_client, tmp_path)

    fake_result = SimpleNamespace(
        routes=3,
        forms=1,
        api_endpoints=2,
        edges=5,
    )

    with patch("src.app.services.update_service.Code2GuideToolbox", create=True), patch(
        "src.agent.tools.Code2GuideToolbox"
    ), patch("src.knowledge.manager.get_index_manager") as get_mgr:
        mgr = MagicMock()
        mgr.index_workspace.return_value = fake_result
        get_mgr.return_value = mgr

        res = app_client.post(
            f"/api/v1/workspaces/{ws_id}/update",
            json={"rebuild": True, "scope": "full"},
        )
        assert res.status_code == 202, res.text
        job_id = res.json()["job_id"]
        assert res.json()["status"] == "running"

        # BackgroundTasks run eagerly inside TestClient
        job = app_client.get(f"/api/v1/workspaces/{ws_id}/updates/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "success"
        assert "Routes" in job.json()["detail"]

        detail = app_client.get(f"/api/v1/workspaces/{ws_id}")
        assert detail.json()["status"] == "ready"


def test_chat_send_message(app_client, tmp_path: Path):
    ws_id = _make_workspace(app_client, tmp_path)

    fake_state = SimpleNamespace(final_persian_guide="## راهنما\nمرحله ۱")

    with patch("src.agent.workflow.Code2GuideAgent") as Agent:
        agent = MagicMock()
        agent.ask.return_value = fake_state
        Agent.return_value = agent

        res = app_client.post(
            f"/api/v1/workspaces/{ws_id}/chatbots/bot_user/messages",
            json={"text": "چطور شروع کنم؟"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["user_message"]["role"] == "user"
        assert data["assistant_message"]["role"] == "assistant"
        assert "راهنما" in data["assistant_message"]["text"]
        agent.ask.assert_called_once()
        kwargs = agent.ask.call_args.kwargs
        assert kwargs.get("audience") == "end_user"

    listed = app_client.get(f"/api/v1/workspaces/{ws_id}/chatbots/bot_user/messages")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
