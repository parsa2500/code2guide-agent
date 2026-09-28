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

## Notes

- Branch used for Dargah planning baseline: `feature/agents-brain-v1`
- Do not commit secrets or customer data.
