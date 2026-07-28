"""Consolidated backend core for the two-file architecture."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import shutil
import socket
import sys
import uuid
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import aiofiles
import httpx
import yaml
from fastapi import APIRouter, File, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from mcp.server.fastmcp import FastMCP
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.types import ASGIApp, Receive, Scope, Send


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OpenAPI to MCP Generator"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    data_dir: Path = Path("./data")
    upload_dir: Path = Path("./data/uploads")
    specs_dir: Path = Path("./data/specs")
    generated_dir: Path = Path("./data/generated")
    max_upload_size_mb: int = 10
    log_level: str = "INFO"
    public_base_url: str = "http://127.0.0.1:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for directory in (
            self.data_dir,
            self.upload_dir,
            self.specs_dir,
            self.generated_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


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


async def app_error_handler(_request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "details": {}},
    )


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
    location: str | None = None
    param_name: str | None = None
    description: str | None = None
    flows: dict[str, Any] | None = None


class ParameterSchema(BaseModel):
    name: str
    location: str
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


class McpServerStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class LogicalGroupEndpoint(BaseModel):
    key: str
    method: str
    path: str
    summary: str | None = None
    tool_name: str | None = None
    tags: list[str] = Field(default_factory=list)


class LogicalGroup(BaseModel):
    id: str
    name: str
    description: str | None = None
    endpoints: list[LogicalGroupEndpoint] = Field(default_factory=list)


class GroupRequest(BaseModel):
    spec_id: str
    selected_endpoints: list[str] = Field(
        ...,
        description="List of endpoint keys (METHOD:path)",
    )


class GroupResponse(BaseModel):
    spec_id: str
    groups: list[LogicalGroup]


class WizardGenerateRequest(BaseModel):
    spec_id: str
    groups: list[LogicalGroup]


class GeneratedServerPreview(BaseModel):
    temp_id: str
    name: str
    description: str | None = None
    server_url: str
    port: int = 0
    authentication: list[str] = Field(default_factory=list)
    tool_count: int
    tools: list[dict[str, Any]] = Field(default_factory=list)
    output_folder: str
    generation_id: str
    logical_group: str | None = None
    spec_slug: str | None = None
    server_slug: str | None = None


class WizardGenerateResponse(BaseModel):
    batch_id: str
    servers: list[GeneratedServerPreview]
    logs: list[str] = Field(default_factory=list)


class WizardSaveRequest(BaseModel):
    batch_id: str
    servers: list[GeneratedServerPreview]


class McpServerRecord(BaseModel):
    id: str
    name: str
    description: str | None = None
    spec_id: str
    spec_name: str
    tool_count: int
    authentication: list[str] = Field(default_factory=list)
    server_url: str
    port: int = 0
    status: McpServerStatus = McpServerStatus.STOPPED
    created_date: datetime
    generation_id: str
    output_folder: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    pid: int | None = None
    logical_group: str | None = None
    transport: str = "streamable-http"
    version: str = "1.0.0"
    spec_slug: str | None = None
    server_slug: str | None = None


class McpServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class TreeToolNode(BaseModel):
    id: str
    name: str
    description: str | None = None
    method: str | None = None
    path: str | None = None
    operation_id: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    url: str | None = None
    base_url: str | None = None
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    security: list[dict[str, Any]] = Field(default_factory=list)
    auth_schemes: list[dict[str, Any]] = Field(default_factory=list)


class TreeServerNode(BaseModel):
    id: str
    name: str
    description: str | None = None
    endpoint: str
    port: int = 0
    status: McpServerStatus
    authentication: list[str] = Field(default_factory=list)
    tool_count: int
    created_date: datetime
    transport: str = "streamable-http"
    version: str = "1.0.0"
    logical_group: str | None = None
    tools: list[TreeToolNode] = Field(default_factory=list)
    spec_slug: str | None = None
    server_slug: str | None = None


class TreeSpecNode(BaseModel):
    id: str
    name: str
    version: str
    description: str | None = None
    openapi_version: str | None = None
    base_urls: list[str] = Field(default_factory=list)
    auth_types: list[str] = Field(default_factory=list)
    endpoint_count: int = 0
    server_count: int = 0
    tool_count: int = 0
    upload_date: datetime | None = None
    servers: list[TreeServerNode] = Field(default_factory=list)


class McpTreeResponse(BaseModel):
    specifications: list[TreeSpecNode] = Field(default_factory=list)


logger = get_logger(__name__)
SUPPORTED_MAJOR = {3}
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
ALLOWED_EXTENSIONS = {".yaml", ".yml", ".json"}
EXT_TO_TYPE = {".yaml": FileType.YAML, ".yml": FileType.YML, ".json": FileType.JSON}
BASE_PORT = 9101
MAX_PORT = 9199
_running: dict[str, asyncio.subprocess.Process] = {}
_client_auth_headers: ContextVar[dict[str, str]] = ContextVar(
    "mcp_client_auth_headers",
    default={},
)
_session_auth: dict[str, dict[str, str]] = {}
_client_session_id: ContextVar[str | None] = ContextVar("mcp_client_session_id", default=None)
_AUTH_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+server$", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "server"


def mcp_path(spec_slug: str, server_slug: str) -> str:
    return f"/mcp/{spec_slug}/{server_slug}"


def public_mcp_url(spec_slug: str, server_slug: str) -> str:
    settings = get_settings()
    base = (settings.public_base_url or f"http://127.0.0.1:{settings.port}").rstrip("/")
    return f"{base}{mcp_path(spec_slug, server_slug)}"


def extract_auth_headers_from_scope(scope: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers") or []:
        try:
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
        except Exception:
            continue
        if not value:
            continue
        if name in _AUTH_HEADER_NAMES or name.startswith("x-api") or name.startswith("x-auth"):
            if name == "authorization":
                result["Authorization"] = value
            elif name == "x-api-key":
                result["X-API-Key"] = value
            else:
                result["-".join(p.capitalize() for p in name.split("-"))] = value
    return result


def extract_session_id_from_scope(scope: dict[str, Any]) -> str | None:
    for raw_name, raw_value in scope.get("headers") or []:
        try:
            name = raw_name.decode("latin-1").lower()
            if name == "mcp-session-id":
                return raw_value.decode("latin-1").strip() or None
        except Exception:
            continue
    return None


def bind_request_auth(scope: dict[str, Any]):
    headers = extract_auth_headers_from_scope(scope)
    session_id = extract_session_id_from_scope(scope)
    if session_id and headers:
        _session_auth[session_id] = headers
    elif session_id and session_id in _session_auth and not headers:
        headers = dict(_session_auth[session_id])

    h_token = _client_auth_headers.set(dict(headers))
    s_token = _client_session_id.set(session_id)

    def _reset() -> None:
        _client_auth_headers.reset(h_token)
        _client_session_id.reset(s_token)

    return _reset


def get_client_auth_headers() -> dict[str, str]:
    headers = dict(_client_auth_headers.get())
    if headers:
        return headers
    session_id = _client_session_id.get()
    if session_id and session_id in _session_auth:
        return dict(_session_auth[session_id])
    return {}


def auth_headers_from_tool_args(kwargs: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    mapping = {
        "authorization": "Authorization",
        "Authorization": "Authorization",
        "_authorization": "Authorization",
        "bearer_token": "Authorization",
        "access_token": "Authorization",
        "api_key": "X-API-Key",
        "apiKey": "X-API-Key",
        "x_api_key": "X-API-Key",
    }
    for key, header_name in mapping.items():
        value = kwargs.get(key)
        if value is None or value == "":
            continue
        text = str(value)
        if header_name == "Authorization" and not text.lower().startswith(
            ("bearer ", "basic ", "token ")
        ):
            if key in ("bearer_token", "access_token"):
                text = f"Bearer {text}"
        headers[header_name] = text

    extra = kwargs.get("headers") or kwargs.get("_headers")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None and str(v):
                headers[str(k)] = str(v)
    return headers


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def allocate_ports(count: int, used: set[int] | None = None) -> list[int]:
    used = set(used or set())
    settings = get_settings()
    base = getattr(settings, "mcp_base_port", BASE_PORT)
    ports: list[int] = []
    port = base
    while len(ports) < count and port <= MAX_PORT:
        if port not in used and _is_free(port):
            ports.append(port)
            used.add(port)
        port += 1
    if len(ports) < count:
        raise RuntimeError(f"Could not allocate {count} free ports starting at {base}")
    return ports


def _title_case(name: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", name).strip()
    if not cleaned:
        return "General"
    return " ".join(word.capitalize() for word in cleaned.split())


def _resource_from_path(path: str) -> str | None:
    for segment in path.strip("/").split("/"):
        if not segment or (segment.startswith("{") and segment.endswith("}")):
            continue
        return segment
    return None


def _endpoint_key(ep: EndpointInfo) -> str:
    return f"{ep.method}:{ep.path}"


def group_endpoints(
    endpoints: list[EndpointInfo],
    selected_keys: list[str],
) -> list[LogicalGroup]:
    selected = set(selected_keys)
    chosen = [ep for ep in endpoints if _endpoint_key(ep) in selected]
    if not chosen:
        return []

    buckets: dict[str, list[EndpointInfo]] = defaultdict(list)
    for ep in chosen:
        tag = (ep.tags[0] if ep.tags else None) or _resource_from_path(ep.path) or "default"
        buckets[tag].append(ep)

    groups: list[LogicalGroup] = []
    for tag, eps in buckets.items():
        name = _title_case(tag)
        if not name.lower().endswith("management") and tag.lower() not in ("default", "api"):
            name = f"{name} Management"
        elif tag.lower() == "default":
            name = "API Root & Discovery"

        groups.append(
            LogicalGroup(
                id=str(uuid.uuid4()),
                name=name,
                description=f"MCP tools for {name.lower()} operations ({len(eps)} endpoints).",
                endpoints=[
                    LogicalGroupEndpoint(
                        key=_endpoint_key(ep),
                        method=ep.method,
                        path=ep.path,
                        summary=ep.summary,
                        tool_name=ep.tool_name,
                        tags=ep.tags,
                    )
                    for ep in eps
                ],
            )
        )

    groups.sort(key=lambda g: g.name.lower())
    return groups


def _load_raw(content: bytes, file_type: str) -> dict[str, Any]:
    text = content.decode("utf-8")
    try:
        data = yaml.safe_load(text) if file_type in ("yaml", "yml") else json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SpecValidationError(f"Failed to parse file: {exc}") from exc

    if not isinstance(data, dict):
        raise SpecValidationError("OpenAPI document must be an object")
    return data


def _check_version(raw: dict[str, Any]) -> str:
    version = raw.get("openapi") or raw.get("swagger")
    if not version:
        raise SpecValidationError("Missing 'openapi' (or 'swagger') version field")

    version_str = str(version)
    if version_str.startswith("2."):
        raise UnsupportedOpenAPIVersionError(version_str)

    major = int(version_str.split(".")[0])
    if major not in SUPPORTED_MAJOR:
        raise UnsupportedOpenAPIVersionError(version_str)
    return version_str


def _validate_spec(raw: dict[str, Any]) -> None:
    try:
        validate(raw)
    except OpenAPISpecValidatorError as exc:
        raise SpecValidationError(
            "Invalid OpenAPI specification",
            details={"validation_error": str(exc)},
        ) from exc
    except Exception as exc:
        logger.warning("OpenAPI validation warning: %s", exc)
        if "openapi" not in raw and "swagger" not in raw:
            raise SpecValidationError(f"Validation failed: {exc}") from exc


def _tool_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "tool"


def _make_tool_name(method: str, path: str, operation_id: str | None, summary: str | None) -> str:
    if operation_id:
        return _tool_slug(operation_id)
    if summary:
        return _tool_slug(summary)
    parts = [method.lower()]
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("by_" + segment[1:-1])
        else:
            parts.append(segment)
    return _tool_slug("_".join(parts))


def _extract_auth(raw: dict[str, Any]) -> list[AuthScheme]:
    components = raw.get("components", {}) or {}
    schemes_raw = components.get("securitySchemes", {}) or {}
    if not schemes_raw and "securityDefinitions" in raw:
        schemes_raw = raw["securityDefinitions"]

    schemes: list[AuthScheme] = []
    for name, scheme in schemes_raw.items():
        stype = (scheme.get("type") or "").lower()
        auth_type = AuthType.NONE
        scheme_name = scheme.get("scheme")

        if stype == "apikey":
            auth_type = AuthType.API_KEY
        elif stype == "http":
            if (scheme_name or "").lower() == "bearer":
                auth_type = AuthType.BEARER
            elif (scheme_name or "").lower() == "basic":
                auth_type = AuthType.BASIC
            else:
                auth_type = (
                    AuthType.BEARER if "bearer" in (scheme_name or "").lower() else AuthType.BASIC
                )
        elif stype in {"oauth2", "openidconnect"}:
            auth_type = AuthType.OAUTH2
        else:
            continue

        schemes.append(
            AuthScheme(
                name=name,
                type=auth_type,
                scheme=scheme_name,
                location=scheme.get("in"),
                param_name=scheme.get("name"),
                description=scheme.get("description"),
                flows=scheme.get("flows"),
            )
        )

    if not schemes:
        schemes.append(AuthScheme(name="none", type=AuthType.NONE, description="No authentication detected"))
    return schemes


def _resolve_ref(ref: str, components: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {"$ref": ref}
    parts = ref.lstrip("#/").split("/")
    cursor: Any = {"components": components}
    for part in parts:
        if isinstance(cursor, dict):
            cursor = cursor.get(part, {})
        else:
            return {}
    return cursor if isinstance(cursor, dict) else {}


def _build_input_schema(operation: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in operation.get("parameters", []) or []:
        if "$ref" in param:
            param = _resolve_ref(param["$ref"], components) or param
        name = param.get("name")
        if not name:
            continue
        schema = param.get("schema") or {"type": "string"}
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], components) or schema
        prop = {**schema, "description": param.get("description"), "x-in": param.get("in", "query")}
        properties[name] = {k: v for k, v in prop.items() if v is not None}
        if param.get("required"):
            required.append(name)

    body = operation.get("requestBody") or {}
    if "$ref" in body:
        body = _resolve_ref(body["$ref"], components) or body
    content = body.get("content") or {}
    for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        if media_type in content:
            schema = content[media_type].get("schema") or {}
            if "$ref" in schema:
                ref_name = schema["$ref"].split("/")[-1]
                resolved = _resolve_ref(schema["$ref"], components)
                properties["body"] = {
                    "type": "object",
                    "description": f"Request body ({ref_name})",
                    "properties": resolved.get("properties", resolved),
                    "required": resolved.get("required", []),
                }
            else:
                properties["body"] = schema if schema else {"type": "object"}
            if body.get("required", True):
                required.append("body")
            break

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _build_output_schema(operation: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") or {}
    for code in ("200", "201", "202", "204", "default"):
        if code not in responses:
            continue
        resp = responses[code]
        if "$ref" in resp:
            resp = _resolve_ref(resp["$ref"], components) or resp
        content = resp.get("content") or {}
        if "application/json" in content:
            schema = content["application/json"].get("schema") or {"type": "object"}
            if "$ref" in schema:
                return _resolve_ref(schema["$ref"], components) or schema
            return schema
        if code == "204":
            return {"type": "null", "description": "No content"}
    return {"type": "object", "description": "Response payload"}


def _extract_endpoints(raw: dict[str, Any]) -> tuple[list[EndpointInfo], list[str]]:
    paths = raw.get("paths") or {}
    components = raw.get("components") or {}
    endpoints: list[EndpointInfo] = []
    tags_set: set[str] = set()
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters") or []
        for method, operation in path_item.items():
            if method.lower() not in http_methods or not isinstance(operation, dict):
                continue
            params = list(shared_params) + list(operation.get("parameters") or [])
            param_models: list[ParameterSchema] = []
            for param in params:
                if "$ref" in param:
                    param = _resolve_ref(param["$ref"], components) or param
                if not param.get("name"):
                    continue
                param_models.append(
                    ParameterSchema(
                        name=param["name"],
                        location=param.get("in", "query"),
                        required=bool(param.get("required", False)),
                        description=param.get("description"),
                        schema=param.get("schema") or {"type": "string"},
                    )
                )

            op_tags = operation.get("tags") or ["default"]
            for tag in op_tags:
                tags_set.add(tag)

            endpoints.append(
                EndpointInfo(
                    operation_id=operation.get("operationId"),
                    method=method.upper(),
                    path=path,
                    summary=operation.get("summary"),
                    description=operation.get("description"),
                    tags=op_tags,
                    parameters=param_models,
                    request_body=operation.get("requestBody"),
                    responses=operation.get("responses") or {},
                    security=operation.get("security") or raw.get("security") or [],
                    tool_name=_make_tool_name(
                        method,
                        path,
                        operation.get("operationId"),
                        operation.get("summary"),
                    ),
                    input_schema=_build_input_schema({**operation, "parameters": params}, components),
                    output_schema=_build_output_schema(operation, components),
                )
            )

    return endpoints, sorted(tags_set)


def parse_openapi(content: bytes, file_type: str) -> ParsedSpec:
    logger.info("Parsing OpenAPI (%s, %d bytes)", file_type, len(content))
    raw = _load_raw(content, file_type)
    version = _check_version(raw)
    _validate_spec(raw)

    info_raw = raw.get("info") or {}
    info = SpecInfo(
        title=info_raw.get("title") or "Untitled API",
        version=info_raw.get("version") or "0.0.0",
        description=info_raw.get("description"),
        openapi_version=version,
        servers=raw.get("servers") or [],
    )
    auth_schemes = _extract_auth(raw)
    endpoints, tags = _extract_endpoints(raw)
    declared_tags = [tag.get("name") for tag in (raw.get("tags") or []) if tag.get("name")]
    ordered_tags = declared_tags + [tag for tag in tags if tag not in declared_tags]

    parsed = ParsedSpec(
        info=info,
        auth_schemes=auth_schemes,
        endpoints=endpoints,
        tags=ordered_tags,
        components=raw.get("components") or {},
    )
    logger.info(
        "Parsed '%s' v%s — %d endpoints, %d auth schemes",
        info.title,
        info.version,
        len(endpoints),
        len(auth_schemes),
    )
    return parsed


def _generator_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "server"


class MCPGenerator:
    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["tojson"] = lambda value: json.dumps(value, indent=2)

    def generate(
        self,
        output_dir: Path,
        server_name: str,
        tools: list[dict[str, Any]],
        auth_schemes: list[AuthScheme],
        schemas: dict[str, Any],
    ) -> list[str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "tools").mkdir(exist_ok=True)
        (output_dir / "schemas").mkdir(exist_ok=True)

        ctx = {
            "server_name": server_name,
            "server_slug": _generator_slug(server_name),
            "tools": tools,
            "auth_schemes": [scheme.model_dump() for scheme in auth_schemes],
            "auth_types": sorted({scheme.type.value for scheme in auth_schemes}),
            "tool_count": len(tools),
        }
        written: list[str] = []

        server_code = self.env.get_template("server.py.j2").render(**ctx)
        (output_dir / "server.py").write_text(server_code, encoding="utf-8")
        written.append("server.py")

        (output_dir / "tools" / "__init__.py").write_text(
            '"""Auto-generated MCP tools."""\n',
            encoding="utf-8",
        )
        written.append("tools/__init__.py")

        tool_template = self.env.get_template("tool.py.j2")
        for tool in tools:
            filename = f"{tool['name']}.py"
            code = tool_template.render(tool=tool, auth_types=ctx["auth_types"])
            (output_dir / "tools" / filename).write_text(code, encoding="utf-8")
            written.append(f"tools/{filename}")

        for name, schema in schemas.items():
            path = output_dir / "schemas" / f"{name}.json"
            path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            written.append(f"schemas/{name}.json")

        for template_name, output_name in (
            ("requirements.txt.j2", "requirements.txt"),
            ("README.md.j2", "README.md"),
            ("auth.py.j2", "auth.py"),
            ("http_client.py.j2", "http_client.py"),
        ):
            rendered = self.env.get_template(template_name).render(**ctx)
            (output_dir / output_name).write_text(rendered, encoding="utf-8")
            written.append(output_name)

        logger.info("Generated MCP project at %s (%d files)", output_dir, len(written))
        return written


class SpecStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._index_path = self.settings.specs_dir / "index.json"
        self._generations_path = self.settings.generated_dir / "index.json"

    async def _read_index(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {}
        async with aiofiles.open(self._index_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            return json.loads(content) if content.strip() else {}

    async def _write_index(self, data: dict[str, Any]) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._index_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(data, indent=2, default=str))

    async def _read_generations(self) -> dict[str, Any]:
        if not self._generations_path.exists():
            return {}
        async with aiofiles.open(self._generations_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            return json.loads(content) if content.strip() else {}

    async def _write_generations(self, data: dict[str, Any]) -> None:
        self._generations_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._generations_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(data, indent=2, default=str))

    async def create_spec(
        self,
        name: str,
        original_filename: str,
        file_type: FileType,
        content: bytes,
    ) -> Specification:
        spec_id = str(uuid.uuid4())
        dest = self.settings.upload_dir / f"{spec_id}.{file_type.value}"
        async with aiofiles.open(dest, "wb") as handle:
            await handle.write(content)

        spec = Specification(
            id=spec_id,
            name=name,
            file_type=file_type,
            original_filename=original_filename,
            upload_date=_now(),
            status=SpecStatus.UPLOADED,
            file_path=str(dest),
        )
        index = await self._read_index()
        index[spec_id] = spec.model_dump(mode="json")
        await self._write_index(index)
        logger.info("Created spec %s (%s)", spec_id, original_filename)
        return spec

    async def list_specs(self) -> list[SpecificationSummary]:
        index = await self._read_index()
        summaries: list[SpecificationSummary] = []
        for raw in index.values():
            parsed = raw.get("parsed")
            endpoint_count = len(parsed.get("endpoints", [])) if parsed else 0
            auth_types = [a.get("type", "") for a in parsed.get("auth_schemes", [])] if parsed else []
            summaries.append(
                SpecificationSummary(
                    id=raw["id"],
                    name=raw["name"],
                    version=raw.get("version", "unknown"),
                    file_type=raw["file_type"],
                    upload_date=raw["upload_date"],
                    status=raw["status"],
                    error_message=raw.get("error_message"),
                    endpoint_count=endpoint_count,
                    auth_types=auth_types,
                )
            )
        summaries.sort(key=lambda summary: summary.upload_date, reverse=True)
        return summaries

    async def get_spec(self, spec_id: str) -> Specification:
        index = await self._read_index()
        if spec_id not in index:
            raise SpecNotFoundError(spec_id)
        return Specification.model_validate(index[spec_id])

    async def update_spec(self, spec: Specification) -> Specification:
        index = await self._read_index()
        if spec.id not in index:
            raise SpecNotFoundError(spec.id)
        index[spec.id] = spec.model_dump(mode="json")
        await self._write_index(index)
        return spec

    async def delete_spec(self, spec_id: str) -> None:
        index = await self._read_index()
        if spec_id not in index:
            raise SpecNotFoundError(spec_id)
        raw = index.pop(spec_id)
        file_path = Path(raw.get("file_path", ""))
        if file_path.exists():
            file_path.unlink()
        meta_path = self.settings.specs_dir / f"{spec_id}.json"
        if meta_path.exists():
            meta_path.unlink()
        await self._write_index(index)
        logger.info("Deleted spec %s", spec_id)

    async def read_spec_content(self, spec_id: str) -> bytes:
        spec = await self.get_spec(spec_id)
        path = Path(spec.file_path)
        if not path.exists():
            raise SpecNotFoundError(spec_id)
        async with aiofiles.open(path, "rb") as handle:
            return await handle.read()

    async def save_parsed(self, spec_id: str, parsed: ParsedSpec, version: str) -> Specification:
        spec = await self.get_spec(spec_id)
        spec.parsed = parsed
        spec.version = version
        spec.name = parsed.info.title or spec.name
        spec.status = SpecStatus.PARSED
        spec.error_message = None
        meta_path = self.settings.specs_dir / f"{spec_id}.json"
        async with aiofiles.open(meta_path, "w", encoding="utf-8") as handle:
            await handle.write(parsed.model_dump_json(indent=2))
        return await self.update_spec(spec)

    async def set_status(
        self,
        spec_id: str,
        status: SpecStatus,
        error_message: str | None = None,
    ) -> Specification:
        spec = await self.get_spec(spec_id)
        spec.status = status
        spec.error_message = error_message
        return await self.update_spec(spec)

    async def save_generation(self, generation_id: str, data: dict[str, Any]) -> None:
        generations = await self._read_generations()
        generations[generation_id] = data
        await self._write_generations(generations)

    async def get_generation(self, generation_id: str) -> dict[str, Any]:
        generations = await self._read_generations()
        if generation_id not in generations:
            raise SpecNotFoundError(generation_id)
        return generations[generation_id]

    async def list_generations(self) -> list[dict[str, Any]]:
        generations = await self._read_generations()
        return list(generations.values())

    def generation_dir(self, generation_id: str) -> Path:
        path = self.settings.generated_dir / generation_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_generation_dir(self, generation_id: str) -> None:
        path = self.settings.generated_dir / generation_id
        if path.exists():
            shutil.rmtree(path)

    def _remove_output_folder(self, raw: dict[str, Any]) -> None:
        generation_id = raw.get("generation_id")
        if generation_id:
            self.remove_generation_dir(generation_id)
            return
        output = raw.get("output_folder")
        if not output:
            return
        path = Path(output)
        if not path.is_absolute():
            path = (self.settings.data_dir.parent / output).resolve()
        if path.exists() and path.is_dir():
            shutil.rmtree(path)

    @property
    def _mcp_index_path(self) -> Path:
        return self.settings.generated_dir / "mcp_servers.json"

    @property
    def _batches_path(self) -> Path:
        return self.settings.generated_dir / "batches.json"

    async def _read_mcp_servers(self) -> dict[str, Any]:
        if not self._mcp_index_path.exists():
            return {}
        async with aiofiles.open(self._mcp_index_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            return json.loads(content) if content.strip() else {}

    async def _write_mcp_servers(self, data: dict[str, Any]) -> None:
        self._mcp_index_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._mcp_index_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(data, indent=2, default=str))

    async def list_mcp_servers(self) -> list[dict[str, Any]]:
        data = await self._read_mcp_servers()
        servers = list(data.values())
        servers.sort(key=lambda server: server.get("created_date", ""), reverse=True)
        return servers

    async def get_mcp_server(self, server_id: str) -> dict[str, Any]:
        data = await self._read_mcp_servers()
        if server_id not in data:
            raise SpecNotFoundError(server_id)
        return data[server_id]

    async def save_mcp_server(self, server: dict[str, Any]) -> dict[str, Any]:
        data = await self._read_mcp_servers()
        data[server["id"]] = server
        await self._write_mcp_servers(data)
        return server

    async def delete_mcp_server(self, server_id: str) -> dict[str, Any]:
        data = await self._read_mcp_servers()
        if server_id not in data:
            raise SpecNotFoundError(server_id)
        raw = data.pop(server_id)
        await self._write_mcp_servers(data)
        tool_count = len(raw.get("tools") or [])
        self._remove_output_folder(raw)
        await self._remove_server_from_batches(server_id, raw.get("generation_id"))
        logger.info(
            "Deleted MCP server %s (%s) with %d tool(s)",
            server_id,
            raw.get("name"),
            tool_count,
        )
        return {"id": server_id, "name": raw.get("name"), "tool_count": tool_count}

    async def _remove_server_from_batches(
        self,
        server_id: str,
        generation_id: str | None,
    ) -> None:
        if not self._batches_path.exists():
            return
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            batches = json.loads(content) if content.strip() else {}
        changed = False
        for batch in batches.values():
            servers = batch.get("servers") or []
            filtered = [
                server
                for server in servers
                if server.get("id") != server_id
                and server.get("temp_id") != server_id
                and (not generation_id or server.get("generation_id") != generation_id)
            ]
            if len(filtered) != len(servers):
                batch["servers"] = filtered
                changed = True
        if changed:
            async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as handle:
                await handle.write(json.dumps(batches, indent=2, default=str))

    async def delete_mcp_servers_for_spec(self, spec_id: str) -> list[str]:
        data = await self._read_mcp_servers()
        deleted: list[str] = []
        for server_id in list(data.keys()):
            if data[server_id].get("spec_id") != spec_id:
                continue
            raw = data.pop(server_id)
            self._remove_output_folder(raw)
            deleted.append(server_id)
        if deleted:
            await self._write_mcp_servers(data)
            logger.info("Deleted %d MCP server(s) for spec %s", len(deleted), spec_id)
        return deleted

    async def delete_batches_for_spec(self, spec_id: str) -> None:
        if not self._batches_path.exists():
            return
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            batches = json.loads(content) if content.strip() else {}
        removed = [batch_id for batch_id, batch in batches.items() if batch.get("spec_id") == spec_id]
        if not removed:
            return
        for batch_id in removed:
            batches.pop(batch_id)
        async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(batches, indent=2, default=str))
        logger.info("Removed %d wizard batch(es) for spec %s", len(removed), spec_id)

    async def used_mcp_ports(self) -> set[int]:
        data = await self._read_mcp_servers()
        return {int(server["port"]) for server in data.values() if server.get("port")}

    async def save_batch(self, batch_id: str, payload: dict[str, Any]) -> None:
        if not self._batches_path.exists():
            batches: dict[str, Any] = {}
        else:
            async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as handle:
                content = await handle.read()
                batches = json.loads(content) if content.strip() else {}
        batches[batch_id] = payload
        async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(batches, indent=2, default=str))

    async def get_batch(self, batch_id: str) -> dict[str, Any]:
        if not self._batches_path.exists():
            raise SpecNotFoundError(batch_id)
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as handle:
            content = await handle.read()
            batches = json.loads(content) if content.strip() else {}
        if batch_id not in batches:
            raise SpecNotFoundError(batch_id)
        return batches[batch_id]


_store: SpecStore | None = None


def get_store() -> SpecStore:
    global _store
    if _store is None:
        _store = SpecStore()
    return _store


LogCallback = Callable[[str, int], None]


@dataclass
class AgentState:
    specs: list[Specification] = field(default_factory=list)
    selected_endpoints: dict[str, list[str]] = field(default_factory=dict)
    server_name: str = "Generated MCP Server"
    generation_id: str = ""
    output_dir: Path | None = None
    auth_schemes: list[AuthScheme] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    schemas: dict[str, Any] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    progress: int = 0
    error: str | None = None


def _intelligent_tool_name(ep: EndpointInfo, used: set[str]) -> str:
    base = ep.tool_name or "tool"
    if ep.summary:
        candidate = re.sub(r"[^a-z0-9]+", "_", ep.summary.lower()).strip("_")
        if candidate and len(candidate) < 64:
            base = candidate
    if ep.operation_id:
        candidate = re.sub(r"[^a-z0-9]+", "_", ep.operation_id.lower()).strip("_")
        if candidate:
            base = candidate

    name = base
    index = 2
    while name in used:
        name = f"{base}_{index}"
        index += 1
    used.add(name)
    return name


class MCPGenerationAgent:
    STEPS = [
        ("validate", 10),
        ("parse", 20),
        ("extract_auth", 35),
        ("extract_endpoints", 50),
        ("generate_tools", 65),
        ("generate_schemas", 75),
        ("generate_server", 90),
        ("package", 100),
    ]

    def __init__(self, store: SpecStore) -> None:
        self.store = store
        self.generator = MCPGenerator()

    def _log(self, state: AgentState, message: str, progress: int, cb: LogCallback | None) -> None:
        state.logs.append(message)
        state.progress = progress
        logger.info("[%s%%] %s", progress, message)
        if cb:
            cb(message, progress)

    async def run(
        self,
        specs: list[Specification],
        selected_endpoints: dict[str, list[str]],
        server_name: str,
        on_progress: LogCallback | None = None,
    ) -> AgentState:
        state = AgentState(
            specs=specs,
            selected_endpoints=selected_endpoints,
            server_name=server_name,
            generation_id=str(uuid.uuid4()),
        )
        state.output_dir = self.store.generation_dir(state.generation_id)
        try:
            await self._validate(state, on_progress)
            await self._parse(state, on_progress)
            await self._extract_auth(state, on_progress)
            await self._extract_endpoints(state, on_progress)
            await self._generate_tools(state, on_progress)
            await self._generate_schemas(state, on_progress)
            await self._generate_server(state, on_progress)
            await self._package(state, on_progress)
        except Exception as exc:
            state.error = str(exc)
            self._log(state, f"Generation failed: {exc}", state.progress, on_progress)
            raise
        return state

    async def _validate(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Validating selected specifications…", 10, cb)
        if not state.specs:
            raise ValueError("No specifications selected")
        for spec in state.specs:
            if not spec.parsed:
                raise ValueError(f"Specification '{spec.name}' has not been parsed yet")
            keys = state.selected_endpoints.get(spec.id, [])
            if not keys:
                raise ValueError(f"No endpoints selected for '{spec.name}'")

    async def _parse(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Loading parsed OpenAPI metadata…", 20, cb)
        for spec in state.specs:
            assert spec.parsed is not None
            self._log(
                state,
                f"Loaded '{spec.parsed.info.title}' ({len(spec.parsed.endpoints)} endpoints)",
                20,
                cb,
            )

    async def _extract_auth(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Extracting authentication schemes…", 35, cb)
        seen: set[str] = set()
        for spec in state.specs:
            assert spec.parsed is not None
            for scheme in spec.parsed.auth_schemes:
                key = f"{scheme.type}:{scheme.name}"
                if key not in seen:
                    seen.add(key)
                    state.auth_schemes.append(scheme)
        types = ", ".join(sorted({scheme.type.value for scheme in state.auth_schemes}))
        self._log(state, f"Detected auth: {types}", 35, cb)

    async def _extract_endpoints(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Selecting endpoints for MCP tools…", 50, cb)
        count = sum(len(value) for value in state.selected_endpoints.values())
        self._log(state, f"{count} endpoint(s) selected", 50, cb)

    async def _generate_tools(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Generating MCP tool definitions…", 65, cb)
        used_names: set[str] = set()
        for spec in state.specs:
            assert spec.parsed is not None
            selected = set(state.selected_endpoints.get(spec.id, []))
            base_url = spec.parsed.info.servers[0].get("url", "") if spec.parsed.info.servers else ""
            for ep in spec.parsed.endpoints:
                if _endpoint_key(ep) not in selected:
                    continue
                tool_name = _intelligent_tool_name(ep, used_names)
                state.tools.append(
                    {
                        "id": f"{tool_name}-{ep.method}-{ep.path}".replace("/", "_").replace("{", "").replace("}", ""),
                        "name": tool_name,
                        "description": ep.description or ep.summary or f"{ep.method} {ep.path}",
                        "method": ep.method,
                        "path": ep.path,
                        "url": f"{base_url.rstrip('/')}{ep.path}" if base_url else ep.path,
                        "base_url": base_url,
                        "operation_id": ep.operation_id,
                        "summary": ep.summary,
                        "tags": ep.tags,
                        "parameters": [param.model_dump(by_alias=True) for param in ep.parameters],
                        "request_body": ep.request_body,
                        "responses": ep.responses,
                        "input_schema": ep.input_schema or {"type": "object", "properties": {}},
                        "output_schema": ep.output_schema or {"type": "object"},
                        "security": ep.security,
                        "spec_id": spec.id,
                        "spec_name": spec.name,
                        "auth_schemes": [scheme.model_dump(mode="json") for scheme in spec.parsed.auth_schemes],
                    }
                )
        self._log(state, f"Created {len(state.tools)} tool definition(s)", 65, cb)

    async def _generate_schemas(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Generating input/output JSON schemas…", 75, cb)
        for tool in state.tools:
            state.schemas[f"{tool['name']}_input"] = tool["input_schema"]
            state.schemas[f"{tool['name']}_output"] = tool["output_schema"]
        self._log(state, f"Wrote {len(state.schemas)} schema(s)", 75, cb)

    async def _generate_server(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Rendering MCP server project…", 90, cb)
        assert state.output_dir is not None
        state.files = self.generator.generate(
            output_dir=state.output_dir,
            server_name=state.server_name,
            tools=state.tools,
            auth_schemes=state.auth_schemes,
            schemas=state.schemas,
        )
        self._log(state, f"Rendered {len(state.files)} file(s)", 90, cb)

    async def _package(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Packaging generated project…", 100, cb)
        assert state.output_dir is not None
        await self.store.save_generation(
            state.generation_id,
            {
                "generation_id": state.generation_id,
                "server_name": state.server_name,
                "tool_count": len(state.tools),
                "authentication": sorted({scheme.type.value for scheme in state.auth_schemes}),
                "selected_endpoints": [f"{tool['method']} {tool['path']}" for tool in state.tools],
                "output_folder": str(state.output_dir),
                "status": "completed",
                "files": state.files,
                "logs": state.logs,
            },
        )
        self._log(state, "Generation complete", 100, cb)


async def _send_json(send: Send, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


@dataclass
class RegisteredMcpServer:
    server_id: str
    spec_id: str
    spec_slug: str
    server_slug: str
    name: str
    description: str | None
    tools: list[dict[str, Any]]
    authentication: list[str]
    enabled: bool = True
    mcp: FastMCP | None = None
    mount_path: str = ""
    _started: bool = field(default=False, repr=False)
    last_client_auth: dict[str, str] = field(default_factory=dict)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.mcp or not self.mcp.session_manager:
            await _send_json(send, 500, {"error": "MCP session manager not ready"})
            return
        if not self._started:
            await _send_json(send, 503, {"error": "MCP server lifecycle not started"})
            return
        reset = bind_request_auth(scope)
        inbound = extract_auth_headers_from_scope(scope)
        if inbound:
            self.last_client_auth = dict(inbound)
        try:
            await self.mcp.session_manager.handle_request(scope, receive, send)
        finally:
            reset()


class McpRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, RegisteredMcpServer] = {}
        self._by_id: dict[str, str] = {}
        self._stack: Any = None

    async def startup(self) -> None:
        import contextlib

        self._stack = contextlib.AsyncExitStack()
        await self._stack.__aenter__()
        for entry in self.all():
            await self._start_entry(entry)
        logger.info("MCP registry lifecycle started (%d servers)", len(self._servers))

    async def shutdown(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.__aexit__(None, None, None)
            except Exception:
                logger.exception("Error shutting down MCP registry lifecycle")
        self._stack = None
        for entry in self.all():
            entry._started = False

    async def _start_entry(self, entry: RegisteredMcpServer) -> None:
        if entry._started or not entry.mcp or not self._stack:
            return
        manager = entry.mcp.session_manager
        if manager is None:
            _ = entry.mcp.streamable_http_app()
            manager = entry.mcp.session_manager
        if manager is None:
            logger.error("No session manager for %s", entry.mount_path)
            return
        await self._stack.enter_async_context(manager.run())
        entry._started = True
        logger.info("Started Streamable HTTP lifecycle for %s", entry.mount_path)

    def key(self, spec_slug: str, server_slug: str) -> str:
        return f"{spec_slug}/{server_slug}"

    def get(self, spec_slug: str, server_slug: str) -> RegisteredMcpServer | None:
        return self._servers.get(self.key(spec_slug, server_slug))

    def get_by_id(self, server_id: str) -> RegisteredMcpServer | None:
        path_key = self._by_id.get(server_id)
        return self._servers.get(path_key) if path_key else None

    def all(self) -> list[RegisteredMcpServer]:
        return list(self._servers.values())

    async def unregister(self, server_id: str) -> None:
        path_key = self._by_id.pop(server_id, None)
        if path_key and path_key in self._servers:
            entry = self._servers.pop(path_key)
            entry._started = False
            logger.info("Unregistered MCP endpoint %s", path_key)

    def register_record(self, record: dict[str, Any]) -> RegisteredMcpServer:
        spec_name = record.get("spec_name") or "api"
        server_name = record.get("name") or "server"
        spec_slug = record.get("spec_slug") or slugify(spec_name)
        server_slug = record.get("server_slug") or slugify(server_name)
        path_key = self.key(spec_slug, server_slug)

        existing = self._servers.get(path_key)
        if existing:
            self._by_id.pop(existing.server_id, None)

        mcp = FastMCP(
            name=server_name,
            instructions=record.get("description") or f"MCP tools for {server_name}",
        )
        mcp.settings.streamable_http_path = "/"
        mcp.settings.stateless_http = True
        try:
            from mcp.server.transport_security import TransportSecuritySettings

            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            )
        except Exception:
            pass

        mount = mcp_path(spec_slug, server_slug)
        entry = RegisteredMcpServer(
            server_id=record["id"],
            spec_id=record.get("spec_id", ""),
            spec_slug=spec_slug,
            server_slug=server_slug,
            name=server_name,
            description=record.get("description"),
            tools=record.get("tools") or [],
            authentication=record.get("authentication") or [],
            enabled=record.get("status", "running") != "stopped",
            mcp=mcp,
            mount_path=mount,
        )
        self._register_tools_lowlevel(mcp, entry.tools, entry.authentication, entry)
        _ = mcp.streamable_http_app()

        if existing:
            existing._started = False

        self._servers[path_key] = entry
        self._by_id[record["id"]] = path_key
        logger.info(
            "Registered MCP endpoint %s (%d tools, enabled=%s)",
            mount,
            len(entry.tools),
            entry.enabled,
        )
        return entry

    async def register_and_start(self, record: dict[str, Any]) -> RegisteredMcpServer:
        entry = self.register_record(record)
        await self._start_entry(entry)
        return entry

    def set_enabled(self, server_id: str, enabled: bool) -> RegisteredMcpServer | None:
        entry = self.get_by_id(server_id)
        if not entry:
            return None
        entry.enabled = enabled
        return entry

    def _register_tools_lowlevel(
        self,
        mcp: FastMCP,
        tools: list[dict[str, Any]],
        auth_types: list[str],
        entry: RegisteredMcpServer,
    ) -> None:
        from mcp.types import TextContent, Tool

        tool_map = {tool.get("name") or f"tool_{index}": tool for index, tool in enumerate(tools)}

        @mcp._mcp_server.list_tools()
        async def _list_tools() -> list[Tool]:
            result: list[Tool] = []
            for name, tool in tool_map.items():
                schema = tool.get("input_schema") or {"type": "object", "properties": {}}
                result.append(
                    Tool(
                        name=name,
                        description=tool.get("description") or f"{tool.get('method')} {tool.get('path')}",
                        inputSchema=schema,
                    )
                )
            return result

        @mcp._mcp_server.call_tool()
        async def _call_tool(name: str, arguments: dict[str, Any] | None):
            tool = tool_map.get(name)
            if not tool:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
            text = await self._execute_http_tool(
                tool,
                arguments or {},
                auth_types,
                entry,
            )
            return [TextContent(type="text", text=text)]

    async def _execute_http_tool(
        self,
        tool: dict[str, Any],
        kwargs: dict[str, Any],
        auth_types: list[str],
        entry: RegisteredMcpServer | None = None,
    ) -> str:
        import base64
        import os

        method = (tool.get("method") or "GET").upper()
        path_template = tool.get("path") or "/"
        base_url = tool.get("base_url") or ""
        input_schema = tool.get("input_schema") or {"type": "object", "properties": {}}
        properties: dict[str, Any] = input_schema.get("properties") or {}

        path = path_template
        params: dict[str, Any] = {}
        headers: dict[str, str] = {}
        body: Any = None

        for prop_name, prop in properties.items():
            if prop_name not in kwargs or kwargs[prop_name] is None:
                continue
            value = kwargs[prop_name]
            location = prop.get("x-in") or prop.get("in")
            if location == "path" or ("{" + prop_name + "}") in path:
                path = path.replace("{" + prop_name + "}", str(value))
            elif location == "header":
                headers[prop_name] = str(value)
            elif prop_name == "body":
                body = value
            else:
                params[prop_name] = value

        auth_arg_keys = {
            "authorization",
            "Authorization",
            "_authorization",
            "bearer_token",
            "access_token",
            "api_key",
            "apiKey",
            "x_api_key",
            "headers",
            "_headers",
        }
        for key, value in kwargs.items():
            if key in properties or value is None or key in auth_arg_keys:
                continue
            if ("{" + key + "}") in path:
                path = path.replace("{" + key + "}", str(value))
            elif key == "body":
                body = value
            else:
                params[key] = value

        client_headers = get_client_auth_headers()
        if not client_headers and entry and entry.last_client_auth:
            client_headers = dict(entry.last_client_auth)
        for header_key, header_value in client_headers.items():
            headers.setdefault(header_key, header_value)

        for header_key, header_value in auth_headers_from_tool_args(kwargs).items():
            headers.setdefault(header_key, header_value)

        if "Authorization" not in headers:
            token = os.getenv("OAUTH_ACCESS_TOKEN") or os.getenv("API_BEARER_TOKEN") or os.getenv("API_TOKEN")
            if token and any(auth in ("bearer", "oauth2", "basic") for auth in auth_types):
                if token.lower().startswith(("bearer ", "basic ")):
                    headers["Authorization"] = token
                elif "basic" in auth_types and ":" in token:
                    headers["Authorization"] = f"Basic {base64.b64encode(token.encode()).decode()}"
                else:
                    headers["Authorization"] = f"Bearer {token}"

        api_key_header = os.getenv("API_KEY_HEADER", "X-API-Key")
        if api_key_header not in headers and "X-API-Key" not in headers:
            api_key = os.getenv("API_KEY")
            if api_key and "apiKey" in auth_types:
                headers[api_key_header] = api_key

        if "Authorization" not in headers and "basic" in auth_types:
            user = os.getenv("API_USERNAME")
            password = os.getenv("API_PASSWORD")
            if user and password:
                raw = f"{user}:{password}".encode()
                headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"

        url_base = os.getenv("API_BASE_URL") or base_url
        url = f"{url_base.rstrip('/')}{path}" if url_base else path

        logger.debug("Executing %s %s (auth_headers=%s)", method, url, sorted(headers.keys()))
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params or None,
                headers=headers or None,
                json=body,
            )
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text}
        if response.status_code >= 400:
            return json.dumps(
                {"error": True, "status_code": response.status_code, "body": data},
                indent=2,
                default=str,
            )
        return json.dumps(data, indent=2, default=str)

    def build_dispatcher(self) -> ASGIApp:
        registry = self

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] not in ("http", "websocket"):
                return
            path = scope.get("path") or "/"
            if path.startswith("/mcp/"):
                path = path[4:]
            elif path == "/mcp":
                path = "/"

            stripped = path.lstrip("/")
            parts = stripped.split("/") if stripped else []
            if len(parts) < 2:
                await _send_json(
                    send,
                    404,
                    {"error": "MCP endpoint path must be /mcp/{spec}/{server}"},
                )
                return

            spec_slug, server_slug = parts[0], parts[1]
            entry = registry.get(spec_slug, server_slug)
            if not entry:
                await _send_json(send, 404, {"error": f"Unknown MCP server '{spec_slug}/{server_slug}'"})
                return
            if not entry.enabled:
                await _send_json(send, 503, {"error": "MCP server is stopped", "status": "stopped"})
                return

            rest = "/" + "/".join(parts[2:]) if len(parts) > 2 else "/"
            child_scope = dict(scope)
            child_scope["path"] = rest
            root = scope.get("root_path") or ""
            if not root.endswith(f"/mcp/{spec_slug}/{server_slug}"):
                child_scope["root_path"] = root + f"/mcp/{spec_slug}/{server_slug}"
            await entry.handle(child_scope, receive, send)

        return app

    async def load_from_store(self, records: list[dict[str, Any]]) -> None:
        self._servers.clear()
        self._by_id.clear()
        for record in records:
            try:
                spec_slug = record.get("spec_slug") or slugify(record.get("spec_name") or "api")
                server_slug = record.get("server_slug") or slugify(record.get("name") or "server")
                self.register_record(
                    {
                        **record,
                        "spec_slug": spec_slug,
                        "server_slug": server_slug,
                        "server_url": public_mcp_url(spec_slug, server_slug),
                        "port": 0,
                        "transport": "streamable-http",
                    }
                )
            except Exception as exc:
                logger.exception("Failed to register MCP server %s: %s", record.get("id"), exc)


_registry: McpRegistry | None = None


def get_registry() -> McpRegistry:
    global _registry
    if _registry is None:
        _registry = McpRegistry()
    return _registry


specs_router = APIRouter(tags=["specifications"])
parse_router = APIRouter(tags=["parse"])
generate_router = APIRouter(tags=["generate"])
mcp_servers_router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])
api_router = APIRouter()


@specs_router.post("/upload-spec", response_model=SpecificationSummary)
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
        raise SpecValidationError(f"File exceeds maximum size of {settings.max_upload_size_mb} MB")
    if not content.strip():
        raise SpecValidationError("Uploaded file is empty")

    spec = await get_store().create_spec(
        name=Path(file.filename).stem,
        original_filename=file.filename,
        file_type=EXT_TO_TYPE[ext],
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


@specs_router.get("/specifications", response_model=list[SpecificationSummary])
async def list_specifications() -> list[SpecificationSummary]:
    return await get_store().list_specs()


@specs_router.get("/spec/{spec_id}", response_model=Specification)
async def get_specification(spec_id: str) -> Specification:
    return await get_store().get_spec(spec_id)


@specs_router.delete("/spec/{spec_id}")
async def delete_specification(spec_id: str) -> dict:
    store = get_store()
    registry = get_registry()
    server_ids = [server["id"] for server in await store.list_mcp_servers() if server.get("spec_id") == spec_id]
    for server_id in server_ids:
        await registry.unregister(server_id)
    deleted_servers = await store.delete_mcp_servers_for_spec(spec_id)
    await store.delete_batches_for_spec(spec_id)
    await store.delete_spec(spec_id)
    logger.info("Deleted spec %s and %d related MCP server(s)", spec_id, len(deleted_servers))
    return {"ok": True, "id": spec_id, "deleted_servers": deleted_servers}


@specs_router.get("/spec/{spec_id}/raw")
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


@parse_router.post("/parse", response_model=ParseResponse)
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
        return ParseResponse(spec_id=body.spec_id, status=SpecStatus.PARSE_ERROR, error_message=str(exc))
    except Exception as exc:
        logger.exception("Unexpected parse error for %s", body.spec_id)
        await store.set_status(body.spec_id, SpecStatus.PARSE_ERROR, str(exc))
        raise AppError(f"Parse failed: {exc}", status_code=500) from exc


@parse_router.post("/generate-metadata", response_model=ParseResponse)
async def generate_metadata(body: ParseRequest) -> ParseResponse:
    return await parse_specification(body)


@generate_router.post("/generate", response_model=GenerateResponse)
async def generate_mcp_server(body: GenerateRequest) -> GenerateResponse:
    store = get_store()
    specs: list[Specification] = []
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
    except Exception as exc:
        for spec in specs:
            await store.set_status(spec.id, SpecStatus.ERROR, str(exc))
        raise AppError(f"Generation failed: {exc}", status_code=500) from exc

    for spec in specs:
        await store.set_status(spec.id, SpecStatus.GENERATED)

    return GenerateResponse(
        generation_id=state.generation_id,
        server_name=state.server_name,
        tool_count=len(state.tools),
        authentication=sorted({scheme.type.value for scheme in state.auth_schemes}),
        selected_endpoints=[f"{tool['method']} {tool['path']}" for tool in state.tools],
        output_folder=str(state.output_dir),
        status="completed",
        files=state.files,
        logs=state.logs,
    )


@generate_router.get("/generations")
async def list_generations() -> list[dict]:
    return await get_store().list_generations()


@generate_router.get("/generations/{generation_id}")
async def get_generation(generation_id: str) -> dict:
    return await get_store().get_generation(generation_id)


@generate_router.get("/download/{generation_id}")
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


@generate_router.post("/run", response_model=RunResponse)
async def run_generation(body: RunRequest) -> RunResponse:
    meta = await get_store().get_generation(body.generation_id)
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


@generate_router.post("/stop/{generation_id}", response_model=RunResponse)
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
            parameters=[param.model_dump(by_alias=True) for param in ep.parameters],
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


@mcp_servers_router.get("", response_model=list[McpServerRecord])
async def list_mcp_servers() -> list[McpServerRecord]:
    store = get_store()
    registry = get_registry()
    result: list[McpServerRecord] = []
    for item in await store.list_mcp_servers():
        entry = registry.get_by_id(item["id"])
        if entry:
            item["status"] = McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
            item["server_url"] = public_mcp_url(entry.spec_slug, entry.server_slug)
            item["spec_slug"] = entry.spec_slug
            item["server_slug"] = entry.server_slug
            item["transport"] = "streamable-http"
            item["port"] = 0
        result.append(McpServerRecord.model_validate(item))
    return result


@mcp_servers_router.get("/tree", response_model=McpTreeResponse)
async def get_mcp_tree() -> McpTreeResponse:
    store = get_store()
    registry = get_registry()
    servers_raw = await store.list_mcp_servers()
    by_spec: dict[str, list[dict]] = {}
    for item in servers_raw:
        entry = registry.get_by_id(item["id"])
        if entry:
            item["status"] = McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
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
        except Exception:
            spec = None

        ep_lookup: dict[str, Any] = {}
        if spec and spec.parsed:
            for ep in spec.parsed.endpoints:
                ep_lookup[f"{ep.method}:{ep.path}"] = ep

        tree_servers: list[TreeServerNode] = []
        total_tools = 0
        for server in server_list:
            tools = [_enrich_tool(tool if isinstance(tool, dict) else {}, ep_lookup) for tool in (server.get("tools") or [])]
            total_tools += len(tools)
            spec_slug = server.get("spec_slug") or slugify(server.get("spec_name") or "api")
            server_slug = server.get("server_slug") or slugify(server.get("name") or "server")
            tree_servers.append(
                TreeServerNode(
                    id=server["id"],
                    name=server["name"],
                    description=server.get("description"),
                    endpoint=server.get("server_url") or public_mcp_url(spec_slug, server_slug),
                    port=0,
                    status=McpServerStatus(server.get("status", "stopped")),
                    authentication=server.get("authentication") or [],
                    tool_count=len(tools),
                    created_date=server["created_date"],
                    transport=server.get("transport") or "streamable-http",
                    version=server.get("version") or "1.0.0",
                    logical_group=server.get("logical_group"),
                    tools=tools,
                    spec_slug=spec_slug,
                    server_slug=server_slug,
                )
            )

        tree_servers.sort(key=lambda item: item.name.lower())
        info = spec.parsed.info if spec and spec.parsed else None
        auth_types = (
            sorted({scheme.type.value for scheme in spec.parsed.auth_schemes})
            if spec and spec.parsed
            else sorted({auth for server in server_list for auth in (server.get("authentication") or [])})
        )
        nodes.append(
            TreeSpecNode(
                id=spec_id,
                name=(info.title if info else None) or (spec.name if spec else server_list[0].get("spec_name", "Spec")),
                version=(info.version if info else None) or (spec.version if spec else "unknown"),
                description=info.description if info else None,
                openapi_version=info.openapi_version if info else None,
                base_urls=[url.get("url", "") for url in (info.servers if info else []) if url.get("url")],
                auth_types=auth_types,
                endpoint_count=len(spec.parsed.endpoints) if spec and spec.parsed else 0,
                server_count=len(tree_servers),
                tool_count=total_tools,
                upload_date=spec.upload_date if spec else None,
                servers=tree_servers,
            )
        )

    nodes.sort(key=lambda node: node.name.lower())
    return McpTreeResponse(specifications=nodes)


@mcp_servers_router.post("/group", response_model=GroupResponse)
async def generate_logical_groups(body: GroupRequest) -> GroupResponse:
    store = get_store()
    spec = await store.get_spec(body.spec_id)
    if not spec.parsed:
        content = await store.read_spec_content(body.spec_id)
        parsed = parse_openapi(content, spec.file_type.value)
        await store.save_parsed(body.spec_id, parsed, parsed.info.version)
        spec = await store.get_spec(body.spec_id)
    assert spec.parsed is not None
    if not body.selected_endpoints:
        raise AppError("Select at least one endpoint", status_code=400)

    groups = group_endpoints(spec.parsed.endpoints, body.selected_endpoints)
    return GroupResponse(spec_id=body.spec_id, groups=groups)


@mcp_servers_router.post("/wizard/generate", response_model=WizardGenerateResponse)
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
    auth = sorted({scheme.type.value for scheme in spec.parsed.auth_schemes})
    spec_name = spec.parsed.info.title if spec.parsed else spec.name
    spec_slug = slugify(spec_name)

    for group in body.groups:
        keys = [endpoint.key for endpoint in group.endpoints]
        if not keys:
            continue
        server_name = group.name if group.name.lower().endswith("server") else f"{group.name} Server"
        server_slug = slugify(server_name)
        state = await agent.run(
            specs=[spec],
            selected_endpoints={spec.id: keys},
            server_name=server_name,
        )
        logs.extend(state.logs)
        previews.append(
            GeneratedServerPreview(
                temp_id=str(uuid.uuid4()),
                name=server_name,
                description=group.description,
                server_url=public_mcp_url(spec_slug, server_slug),
                port=0,
                authentication=auth,
                tool_count=len(state.tools),
                tools=[
                    {
                        "id": tool.get("id") or tool["name"],
                        "name": tool["name"],
                        "description": tool["description"],
                        "method": tool["method"],
                        "path": tool["path"],
                        "url": tool.get("url"),
                        "base_url": tool.get("base_url"),
                        "operation_id": tool.get("operation_id"),
                        "summary": tool.get("summary"),
                        "tags": tool.get("tags") or [],
                        "parameters": tool.get("parameters") or [],
                        "request_body": tool.get("request_body"),
                        "responses": tool.get("responses") or {},
                        "input_schema": tool.get("input_schema") or {},
                        "output_schema": tool.get("output_schema") or {},
                        "security": tool.get("security") or [],
                        "auth_schemes": tool.get("auth_schemes") or [],
                    }
                    for tool in state.tools
                ],
                logical_group=group.name,
                output_folder=str(state.output_dir),
                generation_id=state.generation_id,
                spec_slug=spec_slug,
                server_slug=server_slug,
            )
        )

    await store.save_batch(
        batch_id,
        {
            "batch_id": batch_id,
            "spec_id": body.spec_id,
            "spec_name": spec_name,
            "spec_slug": spec_slug,
            "servers": [preview.model_dump(mode="json") for preview in previews],
            "created_date": _now().isoformat(),
        },
    )
    return WizardGenerateResponse(batch_id=batch_id, servers=previews, logs=logs)


@mcp_servers_router.post("/wizard/save", response_model=list[McpServerRecord])
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


@mcp_servers_router.get("/{server_id}", response_model=McpServerRecord)
async def get_mcp_server(server_id: str) -> McpServerRecord:
    raw = await get_store().get_mcp_server(server_id)
    entry = get_registry().get_by_id(server_id)
    if entry:
        raw["server_url"] = public_mcp_url(entry.spec_slug, entry.server_slug)
        raw["status"] = McpServerStatus.RUNNING.value if entry.enabled else McpServerStatus.STOPPED.value
    return McpServerRecord.model_validate(raw)


@mcp_servers_router.patch("/{server_id}", response_model=McpServerRecord)
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


@mcp_servers_router.delete("/{server_id}")
async def delete_mcp_server(server_id: str) -> dict:
    await get_registry().unregister(server_id)
    deleted = await get_store().delete_mcp_server(server_id)
    return {"ok": True, **deleted}


@mcp_servers_router.get("/{server_id}/download")
async def download_mcp_server(server_id: str) -> StreamingResponse:
    meta = await get_store().get_mcp_server(server_id)
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


@mcp_servers_router.post("/{server_id}/start", response_model=McpServerRecord)
async def start_mcp_server(server_id: str) -> McpServerRecord:
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


@mcp_servers_router.post("/{server_id}/stop", response_model=McpServerRecord)
async def stop_mcp_server(server_id: str) -> McpServerRecord:
    store = get_store()
    meta = await store.get_mcp_server(server_id)
    get_registry().set_enabled(server_id, False)
    meta["status"] = McpServerStatus.STOPPED.value
    meta["pid"] = None
    await store.save_mcp_server(meta)
    logger.info("Disabled MCP endpoint %s", meta.get("server_url"))
    return McpServerRecord.model_validate(meta)


api_router.include_router(specs_router)
api_router.include_router(parse_router)
api_router.include_router(generate_router)
api_router.include_router(mcp_servers_router)


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        app_name=settings.app_name,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.ensure_dirs()
    startup_logger = get_logger(__name__)
    startup_logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    store = get_store()
    records = await store.list_mcp_servers()
    registry = get_registry()
    await registry.load_from_store(records)
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
        except Exception:
            startup_logger.exception("Failed to migrate MCP server %s", entry.server_id)

    await registry.startup()
    startup_logger.info("Mounted %d logical MCP server(s) under /mcp/{spec}/{server}", len(registry.all()))
    yield
    await registry.shutdown()
    startup_logger.info("Shutting down")


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
    app.mount("/mcp", get_registry().build_dispatcher())
    return app
    
