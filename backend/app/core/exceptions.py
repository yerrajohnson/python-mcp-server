from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class SpecNotFoundError(AppError):
    def __init__(self, spec_id: str):
        super().__init__(f"Specification '{spec_id}' not found", status_code=404)


class SpecValidationError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=422, details=details)


class UnsupportedOpenAPIVersionError(AppError):
    def __init__(self, version: str):
        super().__init__(
            f"Unsupported OpenAPI version: {version}. Supported: 3.0.x, 3.1.x",
            status_code=422,
            details={"version": version},
        )


class GenerationError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=500, details=details)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "details": {}},
    )
    
