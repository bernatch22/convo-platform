"""The control plane serves the built UI without ever shadowing an API route."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.webui import mount_ui

pytestmark = pytest.mark.unit


def build(tmp_path: Path) -> Path:
    """A minimal `ui/dist`: an index and one hashed asset, like vite leaves behind."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app-abc123.js").write_text("console.log('convo')")
    return dist


def app_with(dist: Path) -> FastAPI:
    """An app whose API route is declared before the SPA catch-all, as api.py does."""
    app = FastAPI()

    @app.get("/tenants")
    def tenants() -> list[str]:
        return ["clinica-norte"]

    mount_ui(app, dist)
    return app


def test_an_unbuilt_ui_adds_no_route_at_all(tmp_path: Path) -> None:
    app = FastAPI()

    assert mount_ui(app, tmp_path / "never-built") is False

    assert TestClient(app).get("/anything").status_code == 404


def test_a_built_ui_serves_its_assets_verbatim(tmp_path: Path) -> None:
    client = TestClient(app_with(build(tmp_path)))

    assert client.get("/assets/app-abc123.js").text == "console.log('convo')"


def test_an_unknown_path_falls_back_to_the_spa_shell(tmp_path: Path) -> None:
    client = TestClient(app_with(build(tmp_path)))

    assert client.get("/t/clinica-norte/reception").text == "<div id=root></div>"


def test_the_api_keeps_priority_over_the_catch_all(tmp_path: Path) -> None:
    client = TestClient(app_with(build(tmp_path)))

    assert client.get("/tenants").json() == ["clinica-norte"]


def test_a_path_that_escapes_the_folder_gets_the_shell_not_the_file(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours")
    client = TestClient(app_with(build(tmp_path)))

    assert client.get("/../secret.txt").text == "<div id=root></div>"
