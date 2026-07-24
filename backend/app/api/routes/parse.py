"""OpenAPI parse and metadata generation routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import AppError, SpecValidationError, UnsupportedOpenAPIVersionError
from app.core.logging import get_logger
from app.models.schemas import ParseRequest, ParseResponse, SpecStatus
from app.services.openapi_parser import parse_openapi
from app.services.storage import get_store

router = APIRouter(tags=["parse"])
logger = get_logger(__name__)


@router.post("/parse", response_model=ParseResponse)
async def parse_specification(body: ParseRequest) -> ParseResponse:
    store = get_store()
    spec = await store.get_spec(body.spec_id)
    await store.set_status(body.spec_id, SpecStatus.PARSING)

    try:
        content = await store.read_spec_content(body.spec_id)
        parsed = parse_openapi(content, spec.file_type.value)
        updated = await store.save_parsed(body.spec_id, parsed, parsed.info.version)
        return ParseResponse(
            spec_id=updated.id,
            status=updated.status,
            info=parsed.info,
            auth_schemes=parsed.auth_schemes,
            endpoints=parsed.endpoints,
            tags=parsed.tags,
        )
    except (SpecValidationError, UnsupportedOpenAPIVersionError) as exc:
        await store.set_status(body.spec_id, SpecStatus.PARSE_ERROR, str(exc))
        return ParseResponse(
            spec_id=body.spec_id,
            status=SpecStatus.PARSE_ERROR,
            error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected parse error for %s", body.spec_id)
        await store.set_status(body.spec_id, SpecStatus.PARSE_ERROR, str(exc))
        raise AppError(f"Parse failed: {exc}", status_code=500) from exc


@router.post("/generate-metadata", response_model=ParseResponse)
async def generate_metadata(body: ParseRequest) -> ParseResponse:
    """Alias of /parse — re-extracts tool names, schemas, and auth metadata."""
    return await parse_specification(body)
