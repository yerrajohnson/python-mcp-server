# Frontend — OpenAPI → MCP Generator

React 19 + Vite + TypeScript + MUI + React Query + React Router.

## Setup

```bash
npm install
cp .env.example .env   # or use existing .env
npm run dev
```

App: http://localhost:5173  
API: `VITE_API_URL` (default `http://localhost:8000`)

## Pages

| Route | Tab | Purpose |
|-------|-----|---------|
| `/specs` | OpenAPI Specifications | Upload, parse, view, delete |
| `/mcp` | MCP Servers | Select specs/endpoints, generate, download, run |
