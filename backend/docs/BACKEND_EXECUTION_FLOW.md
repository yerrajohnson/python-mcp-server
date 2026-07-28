# Backend Execution Flow — OpenAPI → MCP Generator

> Backend-only guide. Goal: understand every major hop from upload → parse → group → generate → save → start/stop/download → live tool execution.

---

## 0. Mental model (read this first)

This backend is **one FastAPI process** with two jobs:

1. **Control plane (REST API)** — upload specs, parse them, group endpoints, generate MCP server projects, save/list/start/stop/download servers.
2. **Data plane (MCP runtime)** — serve many logical MCP servers under one mount:
   ```
   /mcp/{spec-slug}/{server-slug}
   ```
   Example: `http://127.0.0.1:8002/mcp/jira-oas-4/issues-management`

**Critical distinction:**

| Artifact | Purpose |
|----------|---------|
| Generated folder `data/generated/{uuid}/` (`server.py`, `tools/`, …) | Downloadable standalone MCP project (Jinja-rendered source) |
| In-process `McpRegistry` + FastMCP | What actually serves tools when the UI says “Start” |

When you **Start** a server in the UI, you are **not** launching `python server.py` as a subprocess (wizard path). You **enable** a logical endpoint already registered inside FastAPI. The generated files are still zipped for Download.

There is also a **legacy** path (`POST /generate`, `POST /run`) that *does* spawn subprocesses. The product UI wizard uses `/mcp-servers/*` instead.

---

## 1. Overall architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI app (main.py)                        │
│  create_app()                                                        │
│    ├─ CORS + exception handlers                                      │
│    ├─ api_router  →  REST control plane                              │
│    └─ mount("/mcp", registry.build_dispatcher())  → MCP data plane   │
│                                                                      │
│  lifespan:                                                           │
│    load mcp_servers.json → register FastMCP instances → startup()    │
└───────────────┬──────────────────────────────┬──────────────────────┘
                │                              │
                ▼                              ▼
     ┌──────────────────┐           ┌──────────────────────┐
     │ Route handlers   │           │ McpRegistry          │
     │ specs / parse /  │           │ RegisteredMcpServer  │
     │ mcp_servers /    │──────────▶│ FastMCP tools        │
     │ generate         │           │ _execute_http_tool   │
     └────────┬─────────┘           └──────────┬───────────┘
              │                                │
              ▼                                ▼
     ┌──────────────────┐           ┌──────────────────────┐
     │ SpecStore        │           │ Upstream OpenAPI API │
     │ (JSON files)     │           │ (httpx + auth fwd)   │
     └──────────────────┘           └──────────────────────┘
              ▲
              │
     ┌────────┴─────────┐
     │ MCPGenerationAgent│ ──▶ MCPGenerator (Jinja2)
     │ group_endpoints   │
     │ parse_openapi     │
     └──────────────────┘
```

### Layer roles

| Layer | Location | Role |
|-------|----------|------|
| Entry | `app/main.py` | App factory, lifespan, `/mcp` mount |
| API | `app/api/routes/*` | HTTP adapters; validate request bodies; call services |
| Orchestration | `app/services/agent/workflow.py` | Multi-step generation pipeline |
| Business logic | `openapi_parser`, `grouping`, `mcp_generator`, `mcp_registry`, `request_auth` | Real work |
| Persistence | `app/services/storage.py` (`SpecStore`) | File/JSON repository |
| Models/DTOs | `app/models/schemas.py` | Pydantic request/response/domain models |
| Templates | `app/templates/*.j2` | Source emitted for downloadable projects |
| Config | `app/config.py` | Paths, CORS, `PUBLIC_BASE_URL` |
| Errors | `app/core/exceptions.py` | Typed HTTP errors |

### Orchestrators vs workers

| Kind | Class / function | Why |
|------|------------------|-----|
| **Orchestrator** | `MCPGenerationAgent` | Orders generation steps; holds `AgentState` |
| **Orchestrator** | Route handlers in `mcp_servers.py` (`wizard_generate`, `wizard_save`) | Coordinates store + agent + registry |
| **Orchestrator** | `lifespan` in `main.py` | Boots registry from disk |
| **Worker** | `parse_openapi` | Validates + extracts auth/endpoints |
| **Worker** | `group_endpoints` | Builds logical groups |
| **Worker** | `MCPGenerator.generate` | Renders Jinja + writes files |
| **Worker** | `SpecStore.*` | Persistence only |
| **Worker** | `McpRegistry._execute_http_tool` | Live upstream HTTP for tool calls |
| **Worker** | `request_auth.*` | Capture/forward client Authorization |

---

## 2. Backend folder structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI create_app + lifespan
│   ├── config.py               # Settings (dirs, public_base_url, cors)
│   ├── api/
│   │   ├── router.py           # Aggregates routers + /health
│   │   └── routes/
│   │       ├── specs.py        # Upload / list / get / delete / raw
│   │       ├── parse.py        # Parse + generate-metadata alias
│   │       ├── generate.py     # Legacy generate/run/download
│   │       └── mcp_servers.py  # Wizard + tree + start/stop/download
│   ├── core/
│   │   ├── exceptions.py       # AppError hierarchy + handlers
│   │   └── logging.py
│   ├── models/
│   │   └── schemas.py          # All Pydantic models
│   ├── services/
│   │   ├── storage.py          # SpecStore repository
│   │   ├── openapi_parser.py   # Parse/validate OpenAPI
│   │   ├── grouping.py         # Logical grouping
│   │   ├── mcp_generator.py    # Jinja code generation
│   │   ├── mcp_registry.py     # In-process MCP runtime
│   │   ├── request_auth.py     # Postman/client auth forwarding
│   │   ├── slugify.py          # URL path slugs
│   │   ├── port_allocator.py   # Legacy ports (unused by wizard)
│   │   └── agent/workflow.py   # MCPGenerationAgent
│   └── templates/              # Jinja2 sources
└── data/
    ├── uploads/                # Raw OpenAPI bytes
    ├── specs/                  # index.json + {id}.json parsed
    └── generated/              # projects + mcp_servers.json + batches.json
```

---

## 3. Boot sequence (before any user request)

**File:** `app/main.py`

1. `create_app()` builds FastAPI with `lifespan`.
2. Registers CORS from `Settings.cors_origin_list`.
3. Registers `AppError` / `HTTPException` handlers.
4. Includes `api_router` (all REST routes).
5. **Mounts** `get_registry().build_dispatcher()` at `/mcp`.

On startup (`lifespan`):

1. `setup_logging()`
2. `get_settings().ensure_dirs()` — creates `data/`, `uploads/`, `specs/`, `generated/`
3. `get_store().list_mcp_servers()` — reads `data/generated/mcp_servers.json`
4. `get_registry().load_from_store(records)` — for each record:
   - `register_record(record)` builds a `FastMCP` instance, registers tools, creates ASGI app
5. Migrates each entry’s `server_url` / slugs / status=`running` back to store
6. `registry.startup()` — starts each Streamable HTTP session manager via `AsyncExitStack`

**Next:** process listens; REST + `/mcp/...` ready.

---

## 4. Chronological lifecycle (wizard product path)

### Step 1 — Upload OpenAPI file

**Endpoint:** `POST /upload-spec`  
**Handler:** `upload_spec` in `app/api/routes/specs.py`  
**Why:** Persist the raw OpenAPI document and create a specification record.

**Input:** multipart form field `file` (`UploadFile`).

**Processing:**
1. Reject missing filename.
2. Check extension ∈ `{.yaml,.yml,.json}` → else `SpecValidationError`.
3. Read bytes; check size ≤ `Settings.max_upload_size_mb`.
4. Reject empty body.
5. Derive `name` from filename stem; map extension → `FileType`.
6. Call `get_store().create_spec(...)`.

**`SpecStore.create_spec`** (`storage.py`):
- Generate `spec_id = uuid4()`.
- Write file to `data/uploads/{spec_id}.{ext}`.
- Build `Specification` with `status=UPLOADED`, `file_path`, timestamps.
- Upsert into `data/specs/index.json`.

**Output:** `SpecificationSummary` (id, name, version, status, …).

**Next:** Client typically calls `POST /parse`.

> Note: URL-based import is **not** implemented as a separate backend endpoint in this repo. Upload is file multipart only. If the UI ever accepts a URL, it would need to fetch then upload bytes (not present in backend today).

---

### Step 2 — Parse / validate / extract

**Endpoint:** `POST /parse` (also `POST /generate-metadata` → same handler)  
**Handler:** `parse_specification` in `app/api/routes/parse.py`  
**DTO in:** `ParseRequest { spec_id }`  
**DTO out:** `ParseResponse`

**Processing:**
1. `store.get_spec(spec_id)` — load metadata.
2. `store.set_status(spec_id, PARSING)`.
3. `content = store.read_spec_content(spec_id)` — bytes from upload path.
4. `parsed = parse_openapi(content, file_type)` — **core parser**.
5. `store.save_parsed(spec_id, parsed, version)` — status `PARSED`, write `data/specs/{spec_id}.json`.
6. Return summary counts.

On failure → `set_status(..., PARSE_ERROR, message)`.

#### Inside `parse_openapi` (`openapi_parser.py`)

Call chain:

```
parse_openapi(content, file_type)
  ├─ _load_raw          # yaml.safe_load or json.loads → dict
  ├─ _check_version     # require openapi 3.x (reject swagger 2)
  ├─ _validate_spec     # openapi_spec_validator.validate (soft-fail some cases)
  ├─ _extract_auth      # components.securitySchemes → AuthScheme[]
  ├─ _extract_endpoints # paths × methods → EndpointInfo[]
  └─ return ParsedSpec(info, endpoints, auth_schemes, servers, raw_version)
```

##### Validation (`_check_version` + `_validate_spec`)
- Requires `openapi` (or `swagger`) field.
- Rejects 2.x via `UnsupportedOpenAPIVersionError`.
- Runs `openapi_spec_validator.validate`; on some failures logs warning and continues if document still looks like OpenAPI.

##### Auth extraction (`_extract_auth`)
- Reads `components.securitySchemes` (or OAS2 `securityDefinitions`).
- Maps types:
  - `apiKey` → `AuthType.API_KEY` (+ name/in)
  - `http` + bearer/basic → `BEARER` / `BASIC`
  - `oauth2` → `OAUTH2`
- Returns `list[AuthScheme]`.

##### Endpoint discovery (`_extract_endpoints`)
- Iterates `paths` → HTTP methods (`get/post/put/patch/delete/...`).
- For each operation builds `EndpointInfo` including:
  - `method`, `path`, `operation_id`, `summary`, `description`, `tags`
  - `parameters` (path/query/header) as `ParameterSchema`
  - `request_body`, `responses`
  - `security` (operation or global)
  - `tool_name` via `_make_tool_name`
  - `input_schema` via `_build_input_schema` (JSON Schema for MCP tool args)
  - `output_schema` via `_build_output_schema` (from success response schema)
  - `base_url` / `url` from `servers`
- Resolves `$ref` via `_resolve_ref` where needed.

**Output of parse:** `ParsedSpec` persisted on the `Specification` and as `{spec_id}.json`.

**Next:** Wizard calls group → generate → save.

---

### Step 3 — Logical groups

**Endpoint:** `POST /mcp-servers/group`  
**Handler:** `generate_logical_groups` in `mcp_servers.py`  
**DTO:** `GroupRequest { spec_id, selected_endpoints: ["METHOD:path", ...] }`

**Processing:**
1. Load spec; if not parsed, auto-run `parse_openapi` + `save_parsed`.
2. Filter `parsed.endpoints` to selected keys (or all if empty — check actual code path).
3. Call `group_endpoints(endpoints)`.

#### `group_endpoints` (`grouping.py`)
- Bucket endpoints by **first tag**, else by first path resource segment.
- Produce `list[LogicalGroup]`:
  - `name`, `description`, `endpoints: LogicalGroupEndpoint[]`
- Why: one OpenAPI file often becomes **multiple** MCP servers (Issues, Users, Projects…).

**Output:** `GroupResponse { spec_id, groups }`.

**Next:** `POST /mcp-servers/wizard/generate`.

---

### Step 4 — Generate MCP servers (wizard generate)

**Endpoint:** `POST /mcp-servers/wizard/generate`  
**Handler:** `wizard_generate` in `mcp_servers.py`  
**DTO in:** `WizardGenerateRequest { spec_id, groups: LogicalGroup[] }`  
**DTO out:** `WizardGenerateResponse { batch_id, servers: GeneratedServerPreview[], logs }`

**Why:** For each logical group, run the generation agent and stage a **batch** of previews (not yet registered as live servers).

**Processing (per group):**
1. Build selected endpoint keys for that group.
2. Instantiate `MCPGenerationAgent(store)`.
3. `await agent.run(specs=[spec], selected_endpoints={spec.id: keys}, server_name=group.name + " Server")`.
4. Convert `AgentState` → `GeneratedServerPreview` (name, tools metadata, output_folder, generation_id, auth, slug fields).
5. After all groups: `store.save_batch(batch_id, payload)` → `data/generated/batches.json`.

**Next:** User confirms → `wizard_save`.

---

### Step 5 — Orchestration workflow (`MCPGenerationAgent`)

**File:** `app/services/agent/workflow.py`  
**Class:** `MCPGenerationAgent`  
**State:** `AgentState` dataclass (specs, selected endpoints, tools, schemas, files, logs, progress, error, output_dir, generation_id).

**Created by:** route handlers (`wizard_generate`, legacy `generate_mcp_server`).  
**Important method:** `run(...)`.

#### Ordered steps inside `run`

| # | Method | Progress | What it does |
|---|--------|----------|--------------|
| 1 | `_validate` | 10% | Ensure specs exist / have content; set `output_dir = store.generation_dir(uuid)` |
| 2 | `_parse` | 20% | If needed, ensure parsed endpoints available from specs |
| 3 | `_extract_auth` | 35% | Collect `AuthScheme`s from parsed specs into `state.auth_schemes` |
| 4 | `_extract_endpoints` | 50% | Filter endpoints by `selected_endpoints` map |
| 5 | `_generate_tools` | 65% | Build tool dicts: name, method, path, schemas, base_url, descriptions (`_intelligent_tool_name`) |
| 6 | `_generate_schemas` | 75% | Map `{tool_name}_input` / `{tool_name}_output` JSON schemas into `state.schemas` |
| 7 | `_generate_server` | 90% | **`MCPGenerator().generate(...)`** writes files under `output_dir` |
| 8 | `_package` | 100% | `store.save_generation(generation_id, metadata)` → `generated/index.json` |

On exception: `state.error` set; logs failure.

**Who does business logic vs orchestration:**
- Agent = sequencer + state holder.
- Parser/grouping already happened earlier for wizard; agent still re-derives tools from selected endpoints.
- `MCPGenerator` = actual file IO / Jinja.

---

### Step 6 — Tools generation (what a “tool” is)

Inside `_generate_tools`:

For each selected `EndpointInfo`:
- Choose unique MCP tool name (`_intelligent_tool_name` prefers summary/operationId).
- Build dict roughly like:
  ```python
  {
    "name": "...",
    "description": ...,
    "method": "GET",
    "path": "/rest/api/3/issue/{id}",
    "base_url": "https://...",
    "input_schema": {...},   # from EndpointInfo
    "output_schema": {...},
    "parameters": [...],
    "tags": [...],
    ...
  }
  ```

These tool dicts are used twice later:
1. Written into generated project via Jinja (`server.py.j2` registers tools).
2. Stored on `McpServerRecord.tools` and used by `McpRegistry` to register **live** FastMCP tools.

---

### Step 7 — Input/output schemas

**At parse time** (`openapi_parser.py`):
- `_build_input_schema` — JSON Schema object: properties for path/query/header params + optional `body`.
- `_build_output_schema` — from 200/201 response content schema when present.

**At agent time** (`_generate_schemas`):
- Copies those into `state.schemas["{name}_input"]` / `"{name}_output"`.

**At generator time** (`MCPGenerator.generate`):
- Writes `schemas/{name}.json` files (raw JSON, not Jinja).

---

### Step 8 — Jinja2 code generation (`MCPGenerator`)

**File:** `app/services/mcp_generator.py`  
**Class:** `MCPGenerator`  
**Created by:** `MCPGenerationAgent.__init__` / `_generate_server`.

**Important method:** `generate(output_dir, server_name, tools, auth_schemes, schemas) -> list[str]`

Uses Jinja `Environment(FileSystemLoader=app/templates)`.

| Template | Output | Role |
|----------|--------|------|
| `server.py.j2` | `server.py` | Standalone FastMCP entry; tools call upstream HTTP |
| `tool.py.j2` | `tools/{name}.py` | Per-tool metadata module |
| `auth.py.j2` | `auth.py` | Env-based auth helper (`AuthConfig`, `apply_auth`) |
| `http_client.py.j2` | `http_client.py` | Shared httpx wrapper |
| `requirements.txt.j2` | `requirements.txt` | `mcp`, `httpx`, `python-dotenv` |
| `README.md.j2` | `README.md` | Human setup docs |

Also writes `tools/__init__.py` and schema JSON files.

**Returns:** list of relative file paths written.

---

### Step 9 — Packaging

**Agent `_package`:**
- Persists generation metadata via `SpecStore.save_generation` into `data/generated/index.json` (generation_id, tool_count, files, status, output_folder, …).

**Wizard `_save_batch`:**
- Stores previews (not yet live) in `batches.json` keyed by `batch_id`.

No ZIP yet — ZIP happens on Download.

---

### Step 10 — Save MCP server (make it live)

**Endpoint:** `POST /mcp-servers/wizard/save`  
**Handler:** `wizard_save`  
**DTO:** `WizardSaveRequest { batch_id, servers: GeneratedServerPreview[] }`

**Processing per preview:**
1. `store.get_batch(batch_id)` — recover `spec_id`, `spec_name`, `spec_slug`.
2. Build `McpServerRecord`:
   - new `id` (uuid)
   - `name`, `description`, `tools`, `authentication`
   - `generation_id`, `output_folder`
   - `server_url = public_mcp_url(spec_slug, server_slug)`
   - `status=RUNNING`, `port=0`, `transport=streamable-http`
3. `store.save_mcp_server(payload)` → `mcp_servers.json`.
4. `registry.register_and_start(payload)`:
   - `register_record` builds FastMCP + tools
   - starts session manager lifecycle if stack exists
5. Append to response list.

**Output:** `list[McpServerRecord]`.

**Storage after save:**
- Record in `mcp_servers.json`
- Code still on disk at `output_folder`
- Live MCP path: `/mcp/{spec_slug}/{server_slug}`

---

### Step 11 — How UI/list/tree see the server (backend side)

**List:** `GET /mcp-servers`  
- Reads store; overlays live `status` / URL from registry (`enabled` → running/stopped).

**Tree:** `GET /mcp-servers/tree`  
- Groups servers by `spec_id`.
- Loads each `Specification` for metadata.
- Builds `TreeSpecNode` → `TreeServerNode` → `TreeToolNode`.
- `_enrich_tool` merges stored tool dicts with original `EndpointInfo` (params, schemas, etc.).

This is the backend “display model” the frontend consumes.

---

### Step 12 — Start

**Endpoint:** `POST /mcp-servers/{server_id}/start`  
**Handler:** `start_mcp_server`

**Processing:**
1. Load meta from store.
2. If not in registry → `registry.register_record(meta)`.
3. `registry.set_enabled(server_id, True)`.
4. Persist `status=RUNNING`.
5. Return updated `McpServerRecord`.

**Effect:** Dispatcher accepts requests for that slug path again (not 503).

---

### Step 13 — Stop

**Endpoint:** `POST /mcp-servers/{server_id}/stop`  
**Handler:** `stop_mcp_server`

**Processing:**
1. `set_enabled(server_id, False)`.
2. Persist `status=STOPPED`.
3. Return record.

**Effect:** Same process; dispatcher returns **503** for that logical server. No subprocess kill.

---

### Step 14 — Download

**Endpoint:** `GET /mcp-servers/{server_id}/download`  
**Handler:** `download_mcp_server`

**Processing:**
1. Load meta; resolve `Path(output_folder)`.
2. Zip all files under that folder into `BytesIO`.
3. Return `StreamingResponse` with `Content-Disposition` filename from server name.

---

### Step 15 — Delete server / delete spec cascade

**Delete server:** `DELETE /mcp-servers/{server_id}`
1. `registry.unregister(server_id)`
2. `store.delete_mcp_server` — remove JSON entry, delete generation dir, scrub batches

**Delete spec:** `DELETE /spec/{spec_id}`
1. Unregister all servers with that `spec_id`
2. `delete_mcp_servers_for_spec`
3. `delete_batches_for_spec`
4. `delete_spec` (upload file + index + parsed json)

---

### Step 16 — Live MCP request (after Start)

When Postman/Cursor hits:

`POST /mcp/jira-oas-4/issues-management` (Streamable HTTP / JSON-RPC)

```
ASGI mount /mcp
  → McpRegistry.build_dispatcher()
      parse path → spec_slug, server_slug
      lookup RegisteredMcpServer
      if not enabled → 503
      entry.handle(scope, receive, send)
        ├─ bind_request_auth(scope)          # capture Authorization
        ├─ last_client_auth = inbound headers
        └─ mcp.session_manager.handle_request(...)
             └─ tools/call → _call_tool
                  └─ _execute_http_tool(tool, args, auth_types, entry)
                       ├─ build URL from base_url + path + params
                       ├─ merge auth: client → cache → tool args → env
                       └─ httpx.AsyncClient.request(...)
```

**Auth priority** (`request_auth` + `_execute_http_tool`):
1. Headers from MCP HTTP request (`Authorization`, `X-API-Key`, …)
2. `entry.last_client_auth` / session cache
3. Tool arguments (`bearer_token`, `api_key`, …)
4. Process env (`API_BEARER_TOKEN`, `API_KEY`, …)

---

## 5. API map (backend)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/upload-spec` | Store OpenAPI file |
| GET | `/specifications` | List specs |
| GET | `/spec/{id}` | Spec detail + parsed |
| DELETE | `/spec/{id}` | Delete spec + cascade servers |
| GET | `/spec/{id}/raw` | Raw file text |
| POST | `/parse` | Validate + parse |
| POST | `/generate-metadata` | Alias of parse |
| POST | `/mcp-servers/group` | Logical groups |
| POST | `/mcp-servers/wizard/generate` | Run agent per group |
| POST | `/mcp-servers/wizard/save` | Persist + register |
| GET | `/mcp-servers` | Flat list |
| GET | `/mcp-servers/tree` | Spec→Server→Tool |
| POST | `/mcp-servers/{id}/start` | Enable |
| POST | `/mcp-servers/{id}/stop` | Disable |
| GET | `/mcp-servers/{id}/download` | ZIP |
| DELETE | `/mcp-servers/{id}` | Remove |
| GET | `/health` | Health |
| * | `/mcp/{spec}/{server}/...` | Live MCP transport |

Legacy (still present): `/generate`, `/generations/*`, `/download/{generation_id}`, `/run`, `/stop/{generation_id}`.

---

## 6. Persistence model

| File | Contents |
|------|----------|
| `data/uploads/{spec_id}.ext` | Raw OpenAPI |
| `data/specs/index.json` | Spec metadata index |
| `data/specs/{spec_id}.json` | Full `ParsedSpec` |
| `data/generated/index.json` | Generation job metadata |
| `data/generated/batches.json` | Wizard previews |
| `data/generated/mcp_servers.json` | Saved MCP servers |
| `data/generated/{generation_id}/` | Generated project tree |

`SpecStore` is the only repository. No SQL DB.

---

## 7. Important classes (one-liners)

| Class / symbol | Responsibility |
|----------------|----------------|
| `Settings` | App config: dirs, CORS, public URL, upload limits |
| `create_app` / `lifespan` | Wire FastAPI, boot/shutdown MCP registry |
| `SpecStore` | JSON/file persistence for specs, gens, MCP servers, batches |
| `parse_openapi` | Load, validate, extract auth + endpoints → `ParsedSpec` |
| `group_endpoints` | Bucket endpoints into `LogicalGroup`s |
| `MCPGenerationAgent` | Orchestrate validate→…→package generation pipeline |
| `AgentState` | Mutable state bag for one generation run |
| `MCPGenerator` | Render Jinja templates + write schemas to disk |
| `McpRegistry` | Hold all logical FastMCP servers; dispatch `/mcp` |
| `RegisteredMcpServer` | One mounted MCP endpoint + handle/auth cache |
| `bind_request_auth` / `get_client_auth_headers` | Capture/forward client auth to upstream |
| `slugify` / `mcp_path` / `public_mcp_url` | Path + public URL helpers |
| `AppError` (+ subclasses) | Domain errors → HTTP JSON |
| Pydantic models in `schemas.py` | Request/response/domain DTOs |

### DTOs by stage
- Upload: `Specification`, `SpecificationSummary`, `FileType`, `SpecStatus`
- Parse: `ParseRequest`, `ParseResponse`, `ParsedSpec`, `EndpointInfo`, `AuthScheme`
- Group: `GroupRequest`, `GroupResponse`, `LogicalGroup`
- Wizard: `WizardGenerateRequest`, `GeneratedServerPreview`, `WizardSaveRequest`, `McpServerRecord`
- Tree: `McpTreeResponse`, `TreeSpecNode`, `TreeServerNode`, `TreeToolNode`

---

## 8. Call hierarchy (happy path)

```
uvicorn → app.main:app
  create_app()
    lifespan.startup
      SpecStore.list_mcp_servers
      McpRegistry.load_from_store → register_record* → startup

POST /upload-spec
  upload_spec
    SpecStore.create_spec

POST /parse
  parse_specification
    SpecStore.set_status(PARSING)
    SpecStore.read_spec_content
    parse_openapi
      _load_raw → _check_version → _validate_spec
      _extract_auth → _extract_endpoints
    SpecStore.save_parsed

POST /mcp-servers/group
  generate_logical_groups
    [optional parse_openapi]
    group_endpoints

POST /mcp-servers/wizard/generate
  wizard_generate
    for group:
      MCPGenerationAgent.run
        _validate → _parse → _extract_auth → _extract_endpoints
        _generate_tools → _generate_schemas
        _generate_server
          MCPGenerator.generate  # Jinja + schemas
        _package
          SpecStore.save_generation
    SpecStore.save_batch

POST /mcp-servers/wizard/save
  wizard_save
    SpecStore.get_batch
    for preview:
      SpecStore.save_mcp_server
      McpRegistry.register_and_start
        register_record
          FastMCP + _register_tools_lowlevel
        _start_entry

POST /mcp-servers/{id}/start|stop
  set_enabled + SpecStore.save_mcp_server

GET /mcp-servers/{id}/download
  zip output_folder

MCP POST /mcp/{spec}/{server}
  build_dispatcher → RegisteredMcpServer.handle
    bind_request_auth
    session_manager.handle_request
      call_tool → _execute_http_tool → httpx
```

---

## 9. Sequence (upload → running)

```
Client                FastAPI                 SpecStore              Parser/Agent           Registry
  |                      |                        |                      |                    |
  |--POST /upload-spec-->|                        |                      |                    |
  |                      |--create_spec---------->|                      |                    |
  |<-SpecificationSummary|                        |                      |                    |
  |                      |                        |                      |                    |
  |--POST /parse-------->|                        |                      |                    |
  |                      |--read + save_parsed--->|                      |                    |
  |                      |------------parse_openapi--------------------->|                    |
  |<-ParseResponse-------|                        |                      |                    |
  |                      |                        |                      |                    |
  |--POST .../group----->|                        |                      |                    |
  |                      |-------------group_endpoints------------------>|                    |
  |<-GroupResponse-------|                        |                      |                    |
  |                      |                        |                      |                    |
  |--POST .../generate-->|                        |                      |                    |
  |                      |---------MCPGenerationAgent.run--------------->|                    |
  |                      |                        |<--save_generation----|                    |
  |                      |--save_batch----------->|                      |                    |
  |<-WizardGenerateResp--|                        |                      |                    |
  |                      |                        |                      |                    |
  |--POST .../save------>|                        |                      |                    |
  |                      |--save_mcp_server------>|                      |                    |
  |                      |--------------------------------register_and_start----------------->|
  |<-McpServerRecord[]---|                        |                      |                    |
  |                      |                        |                      |                    |
  |--POST .../start----->| (idempotent enable)    |                      |--set_enabled------>|
  |                      |                        |                      |                    |
  |--MCP tools/call----->|------------------------------------------------handle------------->|
  |                      |                        |                      |--httpx upstream---> API
```

---

## 10. Module dependency graph

```
main.py
  ├─ config.Settings
  ├─ api.router
  │    ├─ routes.specs      → storage, schemas, exceptions
  │    ├─ routes.parse      → storage, openapi_parser, schemas
  │    ├─ routes.generate   → storage, agent.workflow, schemas
  │    └─ routes.mcp_servers
  │         ├─ storage
  │         ├─ grouping
  │         ├─ openapi_parser (auto-parse)
  │         ├─ agent.workflow → mcp_generator → templates/*.j2
  │         ├─ mcp_registry → request_auth, slugify, httpx, mcp.FastMCP
  │         └─ schemas
  └─ mcp_registry (mounted)

storage ← used by almost all routes + agent + lifespan
openapi_parser ← parse + optional group/wizard
```

---

## 11. Config that matters

From `Settings` / `.env`:

| Key | Meaning |
|-----|---------|
| `PUBLIC_BASE_URL` | Base for `server_url` shown/stored (must match actual host:port) |
| `DATA_DIR` / upload/specs/generated paths | Persistence roots |
| `CORS_ORIGINS` | Allowed frontends |
| `MAX_UPLOAD_SIZE_MB` | Upload limit |
| `HOST` / `PORT` | Uvicorn bind |

Env vars for **upstream** auth fallback at tool runtime: `API_BEARER_TOKEN`, `API_TOKEN`, `API_KEY`, `API_KEY_HEADER`, `API_USERNAME`/`API_PASSWORD`, `OAUTH_ACCESS_TOKEN`, `API_BASE_URL`.

---

## 12. Two generation modes (don’t confuse them)

| | Wizard (`/mcp-servers/wizard/*`) | Legacy (`/generate` + `/run`) |
|--|----------------------------------|-------------------------------|
| Output files | Yes, Jinja project | Yes |
| Serving | In-process `McpRegistry` | Subprocess `python server.py` on allocated port |
| Start/Stop | Enable/disable flag | Spawn/kill process |
| URL | `/mcp/{spec}/{server}` on main port | `http://host:{9101+}/mcp` historically |

Product UI uses the **wizard + registry** path.

---

## 13. How to explain this to another developer (30-second version)

> User uploads an OpenAPI file; we store it and parse it into endpoints + auth schemes. The wizard groups endpoints into logical MCP servers. For each group, `MCPGenerationAgent` builds tool metadata and `MCPGenerator` writes a downloadable Python MCP project via Jinja. Saving registers those tools into an in-process FastMCP registry mounted at `/mcp/{spec}/{server}`. Start/Stop toggles whether that path is enabled. Download zips the generated folder. Tool calls proxy to the real API and can forward Postman Authorization headers.

---

*Generated for repo `python-mcp-server` backend. Frontend intentionally omitted.*
