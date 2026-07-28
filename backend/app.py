"""Backend application bootstrap for the two-file architecture."""

from backend_core import AppError, app_error_handler, create_app, get_settings, http_exception_handler

app = create_app()

__all__ = [
    "AppError",
    "app",
    "app_error_handler",
    "create_app",
    "get_settings",
    "http_exception_handler",
]


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app:app", host=settings.host, port=settings.port, reload=settings.debug)
