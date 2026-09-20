"""Workspace CRUD API tests."""

from __future__ import annotations

from pathlib import Path


def test_health(app_client):
    res = app_client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_create_list_get_workspace(app_client, tmp_path: Path):
    ws_path = tmp_path / "codebase"
    ws_path.mkdir()
    payload = {
        "name": "Demo",
        "path": str(ws_path),
        "description": "desc",
    }
    created = app_client.post("/api/v1/workspaces", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Demo"
    assert body["status"] == "idle"
    assert body["deleted_at"] is None
    ws_id = body["id"]

    listed = app_client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == ws_id

    detail = app_client.get(f"/api/v1/workspaces/{ws_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["settings"]["default_agent"] == "guide-agent"
    assert "bot_user" in data["settings"]["enabled_chatbots"]


def test_path_conflict(app_client, tmp_path: Path):
    ws_path = tmp_path / "shared"
    ws_path.mkdir()
    payload = {"name": "A", "path": str(ws_path), "description": ""}
    assert app_client.post("/api/v1/workspaces", json=payload).status_code == 201
    conflict = app_client.post("/api/v1/workspaces", json={**payload, "name": "B"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "PATH_ALREADY_EXISTS"


def test_soft_delete_and_restore(app_client, tmp_path: Path):
    ws_path = tmp_path / "delme"
    ws_path.mkdir()
    created = app_client.post(
        "/api/v1/workspaces",
        json={"name": "X", "path": str(ws_path), "description": ""},
    )
    ws_id = created.json()["id"]

    deleted = app_client.delete(f"/api/v1/workspaces/{ws_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    active = app_client.get("/api/v1/workspaces")
    assert active.json()["total"] == 0

    trash = app_client.get("/api/v1/workspaces/deleted")
    assert trash.json()["total"] == 1

    restored = app_client.post(f"/api/v1/workspaces/{ws_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert app_client.get("/api/v1/workspaces").json()["total"] == 1


def test_settings_put(app_client, tmp_path: Path):
    ws_path = tmp_path / "settings_ws"
    ws_path.mkdir()
    ws_id = app_client.post(
        "/api/v1/workspaces",
        json={"name": "S", "path": str(ws_path), "description": ""},
    ).json()["id"]

    body = {
        "default_agent": "guide-agent",
        "enabled_chatbots": ["bot_user"],
        "audience_default": "technical",
        "auto_index": False,
        "mcp_enabled": True,
    }
    res = app_client.put(f"/api/v1/workspaces/{ws_id}/settings", json=body)
    assert res.status_code == 200
    assert res.json()["enabled_chatbots"] == ["bot_user"]
    assert res.json()["mcp_enabled"] is True


def test_logs_after_create(app_client, tmp_path: Path):
    ws_path = tmp_path / "logs_ws"
    ws_path.mkdir()
    ws_id = app_client.post(
        "/api/v1/workspaces",
        json={"name": "L", "path": str(ws_path), "description": ""},
    ).json()["id"]
    logs = app_client.get(f"/api/v1/workspaces/{ws_id}/logs")
    assert logs.status_code == 200
    assert logs.json()["total"] >= 1
