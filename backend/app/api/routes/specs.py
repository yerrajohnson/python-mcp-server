"""Specification upload and management routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.config import get_settings
from app.core.exceptions import AppError, SpecValidationError
from app.core.logging import get_logger
from app.models.schemas import FileType, Specification, SpecificationSummary
from app.services.mcp_registry import get_registry
from app.services.storage import get_store

router = APIRouter(tags=["specifications"])
logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".yaml", ".yml", ".json"}
EXT_TO_TYPE = {".yaml": FileType.YAML, ".yml": FileType.YML, ".json": FileType.JSON}


@router.post("/upload-spec", response_model=SpecificationSummary)
async def upload_spec(file: UploadFile = File(...)) -> SpecificationSummary:
    if not file.filename:
        raise SpecValidationError("Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise SpecValidationError(
            f"Unsupported file type '{ext}'. Allowed: yaml, yml, json",
            details={"allowed": list(ALLOWED_EXTENSIONS)},
        )

    settings = get_settings()
    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise SpecValidationError(
            f"File exceeds maximum size of {settings.max_upload_size_mb} MB"
        )
    if not content.strip():
        raise SpecValidationError("Uploaded file is empty")

    name = Path(file.filename).stem
    file_type = EXT_TO_TYPE[ext]
    store = get_store()
    spec = await store.create_spec(
        name=name,
        original_filename=file.filename,
        file_type=file_type,
        content=content,
    )
    logger.info("Uploaded spec %s (%s)", spec.id, file.filename)
    return SpecificationSummary(
        id=spec.id,
        name=spec.name,
        version=spec.version,
        file_type=spec.file_type,
        upload_date=spec.upload_date,
        status=spec.status,
        error_message=spec.error_message,
    )


@router.get("/specifications", response_model=list[SpecificationSummary])
async def list_specifications() -> list[SpecificationSummary]:
    return await get_store().list_specs()


@router.get("/spec/{spec_id}", response_model=Specification)
async def get_specification(spec_id: str) -> Specification:
    return await get_store().get_spec(spec_id)


@router.delete("/spec/{spec_id}")
async def delete_specification(spec_id: str) -> dict:
    store = get_store()
    registry = get_registry()
    server_ids = [
        s["id"]
        for s in await store.list_mcp_servers()
        if s.get("spec_id") == spec_id
    ]
    for server_id in server_ids:
        await registry.unregister(server_id)
    deleted_servers = await store.delete_mcp_servers_for_spec(spec_id)
    await store.delete_batches_for_spec(spec_id)
    await store.delete_spec(spec_id)
    logger.info(
        "Deleted spec %s and %d related MCP server(s)",
        spec_id,
        len(deleted_servers),
    )
    return {"ok": True, "id": spec_id, "deleted_servers": deleted_servers}


@router.get("/spec/{spec_id}/raw")
async def get_specification_raw(spec_id: str) -> dict:
    store = get_store()
    spec = await store.get_spec(spec_id)
    content = await store.read_spec_content(spec_id)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError("Unable to decode specification file", status_code=500) from exc
    return {
        "id": spec.id,
        "filename": spec.original_filename,
        "file_type": spec.file_type,
        "content": text,
    }
