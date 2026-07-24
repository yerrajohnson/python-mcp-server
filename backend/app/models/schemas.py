from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SpecStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    PARSE_ERROR = "parse_error"
    GENERATING = "generating"
    GENERATED = "generated"
    ERROR = "error"


class FileType(str, Enum):
    YAML = "yaml"
    YML = "yml"
    JSON = "json"


class AuthType(str, Enum):
    API_KEY = "apiKey"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    NONE = "none"


class AuthScheme(BaseModel):
    name: str
    type: AuthType
    scheme: str | None = None
    location: str | None = None  # header, query, cookie
    param_name: str | None = None
    description: str | None = None
    flows: dict[str, Any] | None = None


class ParameterSchema(BaseModel):
    name: str
    location: str  # path, query, header, cookie
    required: bool = False
    description: str | None = None
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")

    model_config = {"populate_by_name": True}


class EndpointInfo(BaseModel):
    operation_id: str | None = None
    method: str
    path: str
    summary: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    parameters: list[ParameterSchema] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)
    security: list[dict[str, list[str]]] = Field(default_factory=list)
    tool_name: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class SpecInfo(BaseModel):
    title: str = "Untitled API"
    version: str = "0.0.0"
    description: str | None = None
    openapi_version: str | None = None
    servers: list[dict[str, Any]] = Field(default_factory=list)


class ParsedSpec(BaseModel):
    info: SpecInfo
    auth_schemes: list[AuthScheme] = Field(default_factory=list)
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    components: dict[str, Any] = Field(default_factory=dict)


class Specification(BaseModel):
    id: str
    name: str
    version: str = "unknown"
    file_type: FileType
    original_filename: str
    upload_date: datetime
    status: SpecStatus = SpecStatus.UPLOADED
    error_message: str | None = None
    file_path: str
    parsed: ParsedSpec | None = None


# --- API Request / Response models ---


class SpecificationSummary(BaseModel):
    id: str
    name: str
    version: str
    file_type: FileType
    upload_date: datetime
    status: SpecStatus
    error_message: str | None = None
    endpoint_count: int = 0
    auth_types: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    spec_id: str


class ParseResponse(BaseModel):
    spec_id: str
    status: SpecStatus
    info: SpecInfo | None = None
    auth_schemes: list[AuthScheme] = Field(default_factory=list)
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    error_message: str | None = None


class GenerateRequest(BaseModel):
    spec_ids: list[str]
    selected_endpoints: dict[str, list[str]] = Field(
        ...,
        description="Map of spec_id -> list of endpoint keys (METHOD:path)",
    )
    server_name: str = "Generated MCP Server"
    output_folder: str | None = None


class GenerationProgress(BaseModel):
    step: str
    message: str
    progress: int  # 0-100


class GenerateResponse(BaseModel):
    generation_id: str
    server_name: str
    tool_count: int
    authentication: list[str]
    selected_endpoints: list[str]
    output_folder: str
    status: str
    files: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    generation_id: str


class RunResponse(BaseModel):
    generation_id: str
    status: str
    message: str
    pid: int | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    app_name: str
