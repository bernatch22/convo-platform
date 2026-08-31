"""Serve the built React app (`ui/dist`) from the control plane, when it has been built.

One deploy, one port: in production `api.py` is both the API and the web
server, so a browser hitting `/t/clinica-norte/reception` gets `index.html`
and the router takes it from there. In development nothing is built and this
does nothing at all — `npm run dev` serves the app and proxies the API here.

The catch-all is registered LAST on purpose. Starlette matches routes in the
order they were added, so every API path declared above it keeps priority and
only what no endpoint claims falls through to the SPA.

Open source note: `mount_ui` is a generic recipe — a FastAPI app plus a Vite
`dist/` folder, with the two traps handled (route order, and a path that
escapes the folder).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIST = REPO_ROOT / "ui" / "dist"


def mount_ui(app: FastAPI, dist: Path = UI_DIST) -> bool:
    """Serve `dist` at / with SPA fallback; False (and no route added) when it is not built."""
    index = dist / "index.html"
    if not index.is_file():
        return False

    root = dist.resolve()

    @app.get("/{asset_path:path}", include_in_schema=False)
    def ui(asset_path: str) -> FileResponse:
        """Any path the API did not claim: the real file if there is one, else the SPA shell."""
        return FileResponse(_resolve(root, asset_path) or index)

    return True


def _resolve(root: Path, asset_path: str) -> Path | None:
    """The real file this path names inside `root`, or None (missing, or an escape attempt)."""
    if not asset_path:
        return None
    candidate = (root / asset_path).resolve()
    if root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None
