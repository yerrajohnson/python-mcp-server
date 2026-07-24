"""MCP server generation, download, and run routes."""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.exceptions import AppError, SpecNotFoundError
from app.core.logging import get_logger
from app.models.schemas import (
    GenerateRequest,
    GenerateResponse,
    RunRequest,
    RunResponse,
    SpecStatus,
)
from app.services.agent.workflow import MCPGenerationAgent
from app.services.storage import get_store

router = APIRouter(tags=["generate"])
logger = get_logger(__name__)

# Track running MCP server processes
_running: dict[str, asyncio.subprocess.Process] = {}


@router.post("/generate", response_model=GenerateResponse)
async def generate_mcp_server(body: GenerateRequest) -> GenerateResponse:
    store = get_store()
    specs = []
    for spec_id in body.spec_ids:
        spec = await store.get_spec(spec_id)
        if not spec.parsed:
            raise AppError(
                f"Specification '{spec.name}' must be parsed before generation",
                status_code=400,
            )
        await store.set_status(spec_id, SpecStatus.GENERATING)
        specs.append(spec)

    agent = MCPGenerationAgent(store)
    try:
        state = await agent.run(
            specs=specs,
            selected_endpoints=body.selected_endpoints,
            server_name=body.server_name,
        )
    except Exception as exc:  # noqa: BLE001
        for s in specs:
            await store.set_status(s.id, SpecStatus.ERROR, str(exc))
        raise AppError(f"Generation failed: {exc}", status_code=500) from exc

    for s in specs:
        await store.set_status(s.id, SpecStatus.GENERATED)

    return GenerateResponse(
        generation_id=state.generation_id,
        server_name=state.server_name,
        tool_count=len(state.tools),
        authentication=sorted({a.type.value for a in state.auth_schemes}),
        selected_endpoints=[f"{t['method']} {t['path']}" for t in state.tools],
        output_folder=str(state.output_dir),
        status="completed",
        files=state.files,
        logs=state.logs,
    )


@router.get("/generations")
async def list_generations() -> list[dict]:
    return await get_store().list_generations()


@router.get("/generations/{generation_id}")
async def get_generation(generation_id: str) -> dict:
    return await get_store().get_generation(generation_id)


@router.get("/download/{generation_id}")
async def download_generation(generation_id: str) -> StreamingResponse:
    store = get_store()
    try:
        meta = await store.get_generation(generation_id)
    except SpecNotFoundError as exc:
        raise AppError(str(exc), status_code=404) from exc

    output = Path(meta["output_folder"])
    if not output.exists():
        raise AppError("Generated folder not found", status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(output).as_posix())
    buf.seek(0)

    filename = f"{meta.get('server_name', 'mcp-server').replace(' ', '_').lower()}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/run", response_model=RunResponse)
async def run_generation(body: RunRequest) -> RunResponse:
    store = get_store()
    meta = await store.get_generation(body.generation_id)
    output = Path(meta["output_folder"])
    server_py = output / "server.py"
    if not server_py.exists():
        raise AppError("server.py not found in generated project", status_code=404)

    existing = _running.get(body.generation_id)
    if existing and existing.returncode is None:
        return RunResponse(
            generation_id=body.generation_id,
            status="already_running",
            message="MCP server process is already running",
            pid=existing.pid,
        )

    proc = await asyncio.create_subprocess_exec(
        "python",
        str(server_py),
        cwd=str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _running[body.generation_id] = proc
    logger.info("Started MCP server %s (pid=%s)", body.generation_id, proc.pid)

    return RunResponse(
        generation_id=body.generation_id,
        status="running",
        message="MCP server started",
        pid=proc.pid,
    )


@router.post("/stop/{generation_id}", response_model=RunResponse)
async def stop_generation(generation_id: str) -> RunResponse:
    proc = _running.get(generation_id)
    if not proc or proc.returncode is not None:
        return RunResponse(
            generation_id=generation_id,
            status="stopped",
            message="No running process",
            pid=None,
        )
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except TimeoutError:
        proc.kill()
    _running.pop(generation_id, None)
    return RunResponse(
        generation_id=generation_id,
        status="stopped",
        message="MCP server stopped",
        pid=None,
    )
