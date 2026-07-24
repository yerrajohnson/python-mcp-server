# Backend — OpenAPI → MCP Generator

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload-spec` | Upload OpenAPI YAML/JSON |
| GET | `/specifications` | List uploaded specs |
| GET | `/spec/{id}` | Get spec + parsed metadata |
| DELETE | `/spec/{id}` | Delete spec |
| POST | `/parse` | Parse & validate OpenAPI |
| POST | `/generate-metadata` | Re-extract tool metadata |
| POST | `/generate` | Generate MCP server |
| GET | `/download/{id}` | Download ZIP |
| POST | `/run` | Run generated server |
| POST | `/stop/{id}` | Stop running server |
| GET | `/health` | Health check |
