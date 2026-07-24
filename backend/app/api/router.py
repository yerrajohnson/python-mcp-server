from fastapi import APIRouter

from app.api.routes import generate, parse, specs
from app.config import get_settings
from app.models.schemas import HealthResponse

api_router = APIRouter()
api_router.include_router(specs.router)
api_router.include_router(parse.router)
api_router.include_router(generate.router)


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        app_name=settings.app_name,
    )
