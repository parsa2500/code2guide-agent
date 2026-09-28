# Code2Guide Agent

Persian codebase UX assistant: journey/form extraction and a FastAPI + React operator shell.

## Requirements

- Python 3.11+
- Node.js 20+
- Optional: Docker for Qdrant via `docker-compose.yml`

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env   # fill local keys; never commit .env
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Frontend

```powershell
npm ci --prefix frontend
npm run build --prefix frontend
npm run dev --prefix frontend   # http://127.0.0.1:5173
```

## API

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Or from repo root: `npm run up` / `npm run down` (see `frontend/README.md`).

### W1-04 spike: `/api/v1/ask-mykb`

Answers from Code-KB / my-kb Hub only (`CODE_KB_BASE_URL` + `CODE_KB_TOKEN`). Does **not** call local `HybridIndexer` / `index_workspace` on this path.

```powershell
# set CODE_KB_TOKEN to the same value as my-kb DEV_AUTH_TOKEN (never commit)
curl -s -X POST http://127.0.0.1:8000/api/v1/ask-mykb `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"مناقصه دو مرحله‌ای چیست؟\",\"workspace_id\":\"contracts-guides\",\"brain\":\"guide\"}"
```

### W2-02: `/api/v1/ask-process`

Process graph route: matches a versioned subgraph and attaches only related chunks (full corpus omitted from model context).

```powershell
curl -s -X POST http://127.0.0.1:8000/api/v1/ask-process `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"مناقصه دو مرحله‌ای را مرحله‌به‌مرحله بگو\",\"role\":\"کارشناس\"}"
```

## Notes

- Branch used for Dargah planning baseline: `feature/agents-brain-v1`
- Do not commit secrets or customer data.
