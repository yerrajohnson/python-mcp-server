"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.exceptions import AppError, app_error_handler, http_exception_handler
from app.core.logging import get_logger, setup_logging
from app.services.mcp_registry import get_registry
from app.services.storage import get_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.ensure_dirs()
    logger = get_logger(__name__)
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    store = get_store()
    records = await store.list_mcp_servers()
    registry = get_registry()
    await registry.load_from_store(records)
    # Persist migrated URL fields
    for entry in registry.all():
        try:
            raw = await store.get_mcp_server(entry.server_id)
            raw["spec_slug"] = entry.spec_slug
            raw["server_slug"] = entry.server_slug
            raw["server_url"] = f"{settings.public_base_url.rstrip('/')}/mcp/{entry.spec_slug}/{entry.server_slug}"
            raw["port"] = 0
            raw["transport"] = "streamable-http"
            raw["status"] = "running"
            entry.enabled = True
            await store.save_mcp_server(raw)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to migrate MCP server %s", entry.server_id)

    await registry.startup()
    logger.info("Mounted %d logical MCP server(s) under /mcp/{{spec}}/{{server}}", len(registry.all()))
    yield
    await registry.shutdown()
    logger.info("Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(api_router)

    # Single-port MCP runtime: /mcp/{specification}/{server}
    app.mount("/mcp", get_registry().build_dispatcher())
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=s.debug)
