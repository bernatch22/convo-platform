# `convo.api.webui`

The reasoning that used to live in the docstrings of `convo/api/webui.py`; the code keeps one line per symbol.

## module

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
