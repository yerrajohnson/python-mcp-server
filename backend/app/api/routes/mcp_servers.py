"""MCP Servers registry + wizard pipeline routes."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.models.schemas import (
    GeneratedServerPreview,
    GroupRequest,
    GroupResponse,
    McpServerRecord,
    McpServerStatus,
    McpServerUpdate,
    McpTreeResponse,
    TreeServerNode,
    TreeSpecNode,
    TreeToolNode,
    WizardGenerateRequest,
    WizardGenerateResponse,
    WizardSaveRequest,
)
from app.services.agent.workflow import MCPGenerationAgent
from app.services.grouping import group_endpoints
from app.services.mcp_registry import get_registry, public_mcp_url
from app.services.slugify import slugify
from app.services.storage import get_store

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])
logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=list[McpServerRecord])
async def list_mcp_servers() -> list[McpServerRecord]:
    store = get_store()
    registry = get_registry()
    result: list[McpServerRecord] = []
    for item in await store.list_mcp_servers():
        entry = registry.get_by_id(item["id"])
        if entry:
            item["status"] = (
                McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
            )
            item["server_url"] = public_mcp_url(entry.spec_slug, entry.server_slug)
            item["spec_slug"] = entry.spec_slug
            item["server_slug"] = entry.server_slug
            item["transport"] = "streamable-http"
            item["port"] = 0
        result.append(McpServerRecord.model_validate(item))
    return result


def _enrich_tool(tool: dict, ep_lookup: dict[str, Any]) -> TreeToolNode:
    key = f"{tool.get('method', '')}:{tool.get('path', '')}"
    ep = ep_lookup.get(key)
    name = tool.get("name") or (ep.tool_name if ep else "tool")
    tool_id = str(tool.get("id") or name)

    if ep:
        return TreeToolNode(
            id=tool_id,
            name=name,
            description=tool.get("description") or ep.description or ep.summary,
            method=ep.method,
            path=ep.path,
            operation_id=ep.operation_id,
            summary=ep.summary,
            tags=ep.tags,
            url=tool.get("url"),
            base_url=tool.get("base_url"),
            parameters=[p.model_dump(by_alias=True) for p in ep.parameters],
            request_body=ep.request_body,
            responses=ep.responses or {},
            input_schema=tool.get("input_schema") or ep.input_schema or {},
            output_schema=tool.get("output_schema") or ep.output_schema or {},
            security=ep.security or [],
            auth_schemes=tool.get("auth_schemes") or [],
        )

    return TreeToolNode(
        id=tool_id,
        name=name,
        description=tool.get("description"),
        method=tool.get("method"),
        path=tool.get("path"),
        operation_id=tool.get("operation_id"),
        summary=tool.get("summary"),
        tags=tool.get("tags") or [],
        url=tool.get("url"),
        base_url=tool.get("base_url"),
        parameters=tool.get("parameters") or [],
        request_body=tool.get("request_body"),
        responses=tool.get("responses") or {},
        input_schema=tool.get("input_schema") or {},
        output_schema=tool.get("output_schema") or {},
        security=tool.get("security") or [],
        auth_schemes=tool.get("auth_schemes") or [],
    )


@router.get("/tree", response_model=McpTreeResponse)
async def get_mcp_tree() -> McpTreeResponse:
    """Hierarchical Spec → MCP Server → Tool tree for the explorer UI."""
    store = get_store()
    registry = get_registry()
    servers_raw = await store.list_mcp_servers()
    by_spec: dict[str, list[dict]] = {}
    for item in servers_raw:
        entry = registry.get_by_id(item["id"])
        if entry:
            item["status"] = (
                McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
            )
            item["server_url"] = public_mcp_url(entry.spec_slug, entry.server_slug)
            item["spec_slug"] = entry.spec_slug
            item["server_slug"] = entry.server_slug
            item["transport"] = "streamable-http"
            item["port"] = 0
        by_spec.setdefault(item["spec_id"], []).append(item)

    nodes: list[TreeSpecNode] = []
    for spec_id, server_list in by_spec.items():
        try:
            spec = await store.get_spec(spec_id)
        except Exception:  # noqa: BLE001
            spec = None

        ep_lookup: dict[str, Any] = {}
        if spec and spec.parsed:
            for ep in spec.parsed.endpoints:
                ep_lookup[f"{ep.method}:{ep.path}"] = ep

        tree_servers: list[TreeServerNode] = []
        total_tools = 0
        for s in server_list:
            tools = [
                _enrich_tool(t if isinstance(t, dict) else {}, ep_lookup)
                for t in (s.get("tools") or [])
            ]
            total_tools += len(tools)
            spec_slug = s.get("spec_slug") or slugify(s.get("spec_name") or "api")
            server_slug = s.get("server_slug") or slugify(s.get("name") or "server")
            tree_servers.append(
                TreeServerNode(
                    id=s["id"],
                    name=s["name"],
                    description=s.get("description"),
                    endpoint=s.get("server_url") or public_mcp_url(spec_slug, server_slug),
                    port=0,
                    status=McpServerStatus(s.get("status", "stopped")),
                    authentication=s.get("authentication") or [],
                    tool_count=len(tools),
                    created_date=s["created_date"],
                    transport=s.get("transport") or "streamable-http",
                    version=s.get("version") or "1.0.0",
                    logical_group=s.get("logical_group"),
                    tools=tools,
                    spec_slug=spec_slug,
                    server_slug=server_slug,
                )
            )

        tree_servers.sort(key=lambda x: x.name.lower())
        info = spec.parsed.info if spec and spec.parsed else None
        auth_types = (
            sorted({a.type.value for a in spec.parsed.auth_schemes})
            if spec and spec.parsed
            else sorted({a for s in server_list for a in (s.get("authentication") or [])})
        )
        nodes.append(
            TreeSpecNode(
                id=spec_id,
                name=(info.title if info else None)
                or (spec.name if spec else server_list[0].get("spec_name", "Spec")),
                version=(info.version if info else None) or (spec.version if spec else "unknown"),
                description=info.description if info else None,
                openapi_version=info.openapi_version if info else None,
                base_urls=[u.get("url", "") for u in (info.servers if info else []) if u.get("url")],
                auth_types=auth_types,
                endpoint_count=len(spec.parsed.endpoints) if spec and spec.parsed else 0,
                server_count=len(tree_servers),
                tool_count=total_tools,
                upload_date=spec.upload_date if spec else None,
                servers=tree_servers,
            )
        )

    nodes.sort(key=lambda n: n.name.lower())
    return McpTreeResponse(specifications=nodes)


@router.post("/group", response_model=GroupResponse)
async def generate_logical_groups(body: GroupRequest) -> GroupResponse:
    store = get_store()
    spec = await store.get_spec(body.spec_id)
    if not spec.parsed:
        from app.services.openapi_parser import parse_openapi

        content = await store.read_spec_content(body.spec_id)
        parsed = parse_openapi(content, spec.file_type.value)
        await store.save_parsed(body.spec_id, parsed, parsed.info.version)
        spec = await store.get_spec(body.spec_id)

    assert spec.parsed is not None
    if not body.selected_endpoints:
        raise AppError("Select at least one endpoint", status_code=400)

    groups = group_endpoints(spec.parsed.endpoints, body.selected_endpoints)
    return GroupResponse(spec_id=body.spec_id, groups=groups)


@router.post("/wizard/generate", response_model=WizardGenerateResponse)
async def wizard_generate(body: WizardGenerateRequest) -> WizardGenerateResponse:
    store = get_store()
    spec = await store.get_spec(body.spec_id)
    if not spec.parsed:
        raise AppError("Specification must be parsed first", status_code=400)
    if not body.groups:
        raise AppError("At least one logical group is required", status_code=400)

    agent = MCPGenerationAgent(store)
    batch_id = str(uuid.uuid4())
    previews: list[GeneratedServerPreview] = []
    logs: list[str] = []
    auth = sorted({a.type.value for a in spec.parsed.auth_schemes})
    spec_name = spec.parsed.info.title if spec.parsed else spec.name
    spec_slug = slugify(spec_name)

    for group in body.groups:
        keys = [ep.key for ep in group.endpoints]
        if not keys:
            continue
        server_name = (
            group.name if group.name.lower().endswith("server") else f"{group.name} Server"
        )
        server_slug = slugify(server_name)
        state = await agent.run(
            specs=[spec],
            selected_endpoints={spec.id: keys},
            server_name=server_name,
        )
        logs.extend(state.logs)
        preview = GeneratedServerPreview(
            temp_id=str(uuid.uuid4()),
            name=server_name,
            description=group.description,
            server_url=public_mcp_url(spec_slug, server_slug),
            port=0,
            authentication=auth,
            tool_count=len(state.tools),
            tools=[
                {
                    "id": t.get("id") or t["name"],
                    "name": t["name"],
                    "description": t["description"],
                    "method": t["method"],
                    "path": t["path"],
                    "url": t.get("url"),
                    "base_url": t.get("base_url"),
                    "operation_id": t.get("operation_id"),
                    "summary": t.get("summary"),
                    "tags": t.get("tags") or [],
                    "parameters": t.get("parameters") or [],
                    "request_body": t.get("request_body"),
                    "responses": t.get("responses") or {},
                    "input_schema": t.get("input_schema") or {},
                    "output_schema": t.get("output_schema") or {},
                    "security": t.get("security") or [],
                    "auth_schemes": t.get("auth_schemes") or [],
                }
                for t in state.tools
            ],
            logical_group=group.name,
            output_folder=str(state.output_dir),
            generation_id=state.generation_id,
            spec_slug=spec_slug,
            server_slug=server_slug,
        )
        previews.append(preview)

    await store.save_batch(
        batch_id,
        {
            "batch_id": batch_id,
            "spec_id": body.spec_id,
            "spec_name": spec_name,
            "spec_slug": spec_slug,
            "servers": [p.model_dump(mode="json") for p in previews],
            "created_date": _now().isoformat(),
        },
    )
    return WizardGenerateResponse(batch_id=batch_id, servers=previews, logs=logs)


@router.post("/wizard/save", response_model=list[McpServerRecord])
async def wizard_save(body: WizardSaveRequest) -> list[McpServerRecord]:
    store = get_store()
    registry = get_registry()
    batch = await store.get_batch(body.batch_id)
    spec_id = batch["spec_id"]
    spec_name = batch["spec_name"]
    spec_slug = batch.get("spec_slug") or slugify(spec_name)
    saved: list[McpServerRecord] = []

    for preview in body.servers:
        server_slug = preview.server_slug or slugify(preview.name)
        record = McpServerRecord(
            id=str(uuid.uuid4()),
            name=preview.name,
            description=preview.description,
            spec_id=spec_id,
            spec_name=spec_name,
            tool_count=preview.tool_count,
            authentication=preview.authentication,
            server_url=public_mcp_url(spec_slug, server_slug),
            port=0,
            status=McpServerStatus.RUNNING,
            created_date=_now(),
            generation_id=preview.generation_id,
            output_folder=preview.output_folder,
            tools=preview.tools,
            logical_group=preview.logical_group,
            transport="streamable-http",
            version="1.0.0",
            spec_slug=spec_slug,
            server_slug=server_slug,
        )
        payload = record.model_dump(mode="json")
        await store.save_mcp_server(payload)
        await registry.register_and_start(payload)
        saved.append(record)
    return saved


@router.get("/{server_id}", response_model=McpServerRecord)
async def get_mcp_server(server_id: str) -> McpServerRecord:
    raw = await get_store().get_mcp_server(server_id)
    entry = get_registry().get_by_id(server_id)
    if entry:
        raw["server_url"] = public_mcp_url(entry.spec_slug, entry.server_slug)
        raw["status"] = (
            McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
        )
    return McpServerRecord.model_validate(raw)


@router.patch("/{server_id}", response_model=McpServerRecord)
async def update_mcp_server(server_id: str, body: McpServerUpdate) -> McpServerRecord:
    store = get_store()
    raw = await store.get_mcp_server(server_id)
    if body.name is not None:
        raw["name"] = body.name
        raw["server_slug"] = slugify(body.name)
    if body.description is not None:
        raw["description"] = body.description
    if raw.get("spec_slug") and raw.get("server_slug"):
        raw["server_url"] = public_mcp_url(raw["spec_slug"], raw["server_slug"])
    await store.save_mcp_server(raw)
    await get_registry().register_and_start(raw)
    return McpServerRecord.model_validate(raw)


@router.delete("/{server_id}")
async def delete_mcp_server(server_id: str) -> dict:
    await get_registry().unregister(server_id)
    deleted = await get_store().delete_mcp_server(server_id)
    return {"ok": True, **deleted}


@router.get("/{server_id}/download")
async def download_mcp_server(server_id: str) -> StreamingResponse:
    store = get_store()
    meta = await store.get_mcp_server(server_id)
    output = Path(meta["output_folder"])
    if not output.exists():
        raise AppError("Generated folder not found", status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(output).as_posix())
    buf.seek(0)
    filename = f"{meta.get('name', 'mcp-server').replace(' ', '_').lower()}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{server_id}/start", response_model=McpServerRecord)
async def start_mcp_server(server_id: str) -> McpServerRecord:
    """Enable the logical MCP endpoint inside the single FastAPI app."""
    store = get_store()
    meta = await store.get_mcp_server(server_id)
    registry = get_registry()
    if not registry.get_by_id(server_id):
        registry.register_record(meta)
    registry.set_enabled(server_id, True)
    meta["status"] = McpServerStatus.RUNNING.value
    meta["pid"] = None
    await store.save_mcp_server(meta)
    logger.info("Enabled MCP endpoint %s", meta.get("server_url"))
    return McpServerRecord.model_validate(meta)


@router.post("/{server_id}/stop", response_model=McpServerRecord)
async def stop_mcp_server(server_id: str) -> McpServerRecord:
    """Disable the logical MCP endpoint (still one FastAPI process)."""
    store = get_store()
    meta = await store.get_mcp_server(server_id)
    get_registry().set_enabled(server_id, False)
    meta["status"] = McpServerStatus.STOPPED.value
    meta["pid"] = None
    await store.save_mcp_server(meta)
    logger.info("Disabled MCP endpoint %s", meta.get("server_url"))
    return McpServerRecord.model_validate(meta)
