"""Slice-1 agent registry / workspace bindings / brain settings tests."""

from __future__ import annotations

from pathlib import Path


def test_seed_ids_exist_after_init(app_client):
    res = app_client.get("/api/v1/agents")
    assert res.status_code == 200, res.text
    ids = {item["id"] for item in res.json()["items"]}
    assert {"jarvis", "bot_user", "bot_tech"} <= ids
    by_id = {item["id"]: item for item in res.json()["items"]}
    assert by_id["jarvis"]["published"] is True
    assert by_id["bot_user"]["kind"] == "end_user"
    assert by_id["bot_tech"]["kind"] == "technical"
    assert by_id["jarvis"]["kind"] == "jarvis"


def test_publish_flag_toggles(app_client):
    created = app_client.post(
        "/api/v1/agents",
        json={
            "id": "custom_demo",
            "name": "Custom Demo",
            "kind": "custom",
            "published": False,
            "settings_schema": {
                "tone": {"default": "neutral", "workspace_overridable": True},
                "secret": {"default": "x", "workspace_overridable": False},
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["published"] is False

    pub = app_client.post("/api/v1/agents/custom_demo/publish", json={"published": True})
    assert pub.status_code == 200
    assert pub.json()["published"] is True

    unpub = app_client.post("/api/v1/agents/custom_demo/publish", json={"published": False})
    assert unpub.status_code == 200
    assert unpub.json()["published"] is False


def test_cannot_bind_unpublished_agent(app_client, tmp_path: Path):
    ws_path = tmp_path / "bind_ws"
    ws_path.mkdir()
    ws_id = app_client.post(
        "/api/v1/workspaces",
        json={"name": "B", "path": str(ws_path), "description": ""},
    ).json()["id"]

    app_client.post(
        "/api/v1/agents",
        json={"id": "draft_agent", "name": "Draft", "kind": "custom", "published": False},
    )
    res = app_client.post(
        f"/api/v1/workspaces/{ws_id}/agents",
        json={"agent_id": "draft_agent"},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "AGENT_NOT_PUBLISHED"


def test_overrides_reject_non_overridable_key(app_client, tmp_path: Path):
    ws_path = tmp_path / "ovr_ws"
    ws_path.mkdir()
    ws_id = app_client.post(
        "/api/v1/workspaces",
        json={"name": "O", "path": str(ws_path), "description": ""},
    ).json()["id"]

    app_client.post(
        "/api/v1/agents",
        json={
            "id": "ovr_agent",
            "name": "Override Agent",
            "kind": "custom",
            "published": True,
            "settings_schema": {
                "tone": {"default": "neutral", "workspace_overridable": True},
                "secret": {"default": "x", "workspace_overridable": False},
            },
        },
    )
    bind = app_client.post(
        f"/api/v1/workspaces/{ws_id}/agents",
        json={"agent_id": "ovr_agent"},
    )
    assert bind.status_code == 201, bind.text

    bad = app_client.patch(
        f"/api/v1/workspaces/{ws_id}/agents/ovr_agent",
        json={"overrides": {"secret": "leak"}},
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "OVERRIDE_NOT_ALLOWED"

    good = app_client.patch(
        f"/api/v1/workspaces/{ws_id}/agents/ovr_agent",
        json={"overrides": {"tone": "friendly"}},
    )
    assert good.status_code == 200, good.text
    assert good.json()["overrides"]["tone"] == "friendly"
    assert good.json()["effective_settings"]["tone"] == "friendly"
    assert good.json()["effective_settings"]["secret"] == "x"


def test_workspace_create_gets_bindings(app_client, tmp_path: Path):
    ws_path = tmp_path / "bound_ws"
    ws_path.mkdir()
    ws_id = app_client.post(
        "/api/v1/workspaces",
        json={"name": "Bound", "path": str(ws_path), "description": ""},
    ).json()["id"]

    agents = app_client.get(f"/api/v1/workspaces/{ws_id}/agents")
    assert agents.status_code == 200, agents.text
    ids = {item["agent_id"] for item in agents.json()["items"]}
    assert {"bot_user", "bot_tech", "jarvis"} <= ids

    # Legacy chatbots still present
    bots = app_client.get(f"/api/v1/workspaces/{ws_id}/chatbots")
    assert bots.status_code == 200
    bot_ids = {b["id"] for b in bots.json()["items"]}
    assert {"bot_user", "bot_tech"} <= bot_ids


def test_brain_settings_get_put(app_client, tmp_path: Path, monkeypatch):
    # Point persistence under tmp via monkeypatch of constant path resolution
    from src.app.services import brain_settings_service as bss

    monkeypatch.setattr(bss, "BRAIN_SETTINGS_PATH", str(tmp_path / "brain_settings.json"))
    # Also patch module-level import used inside _settings_file via rewriting constant
    import src.app.constants as constants

    monkeypatch.setattr(constants, "BRAIN_SETTINGS_PATH", str(tmp_path / "brain_settings.json"))

    # Re-import path helper uses BRAIN_SETTINGS_PATH from constants at call time — patch function
    def _file():
        return tmp_path / "brain_settings.json"

    monkeypatch.setattr(bss, "_settings_file", _file)

    got = app_client.get("/api/v1/brain-settings")
    assert got.status_code == 200
    assert "embedding_model" in got.json()

    put = app_client.put(
        "/api/v1/brain-settings",
        json={"embedding_model": "test-embed-model", "embedding_dim": 32},
    )
    assert put.status_code == 200, put.text
    assert put.json()["embedding_model"] == "test-embed-model"
    assert put.json()["embedding_dim"] == 32
    assert (tmp_path / "brain_settings.json").is_file()
