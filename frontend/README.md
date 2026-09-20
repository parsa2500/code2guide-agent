# Code2Guide Frontend

React + Vite operator shell (FIDS visual world). Proxies `/api` to FastAPI on port 8000.

## Develop

```bash
# terminal 1 — API
uvicorn src.api.main:app --reload --port 8000

# terminal 2 — UI
cd frontend
npm install
npm run dev
```

Or from repo root (Qdrant + API + UI together):

```bash
npm run up      # or: .\scripts\dev-up.ps1
npm run down    # or: .\scripts\dev-down.ps1
```

In Cursor/VS Code: **Terminal → Run Task… → `Code2Guide: Up` / `Code2Guide: Down`**.

Open http://127.0.0.1:5173

## Production UI via FastAPI

```bash
cd frontend && npm run build
uvicorn src.api.main:app --port 8000
```

`src/api/main.py` serves `frontend/dist` at `/` when present; otherwise falls back to `src/api/static/index.html`.
