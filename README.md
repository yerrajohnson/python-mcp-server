# OpenAPI → MCP Generator

Production-ready web app that uploads OpenAPI specs and auto-generates executable MCP servers.

```
project/
  frontend/   # React 19 + Vite + MUI + React Query
  backend/    # FastAPI + OpenAPI parser + Jinja2 MCP generator
```

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — API at http://localhost:8000/docs

## Workflow

1. **Tab 1** — Upload OpenAPI (YAML/JSON) → Parse → Generate Metadata  
2. **Tab 2** — Select specs & endpoints → Generate → Download ZIP or Run  

## Architecture

- **Backend:** FastAPI routers, JSON store, OpenAPI validator/parser, generation agent pipeline, Jinja2 templates  
- **Frontend:** Two-tab UI (Specs + MCP Servers), three-panel generator layout  
- **Generated output:** `server.py`, `tools/`, `schemas/`, `auth.py`, `requirements.txt`, `README.md`
