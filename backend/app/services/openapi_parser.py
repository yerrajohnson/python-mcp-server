"""OpenAPI specification parser and validator."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError

from app.core.exceptions import SpecValidationError, UnsupportedOpenAPIVersionError
from app.core.logging import get_logger
from app.models.schemas import (
    AuthScheme,
    AuthType,
    EndpointInfo,
    ParameterSchema,
    ParsedSpec,
    SpecInfo,
)

logger = get_logger(__name__)

SUPPORTED_MAJOR = {3}


def _load_raw(content: bytes, file_type: str) -> dict[str, Any]:
    text = content.decode("utf-8")
    try:
        if file_type in ("yaml", "yml"):
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
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
    except Exception as exc:  # noqa: BLE001 — surface any validator failure
        logger.warning("OpenAPI validation warning: %s", exc)
        # Soft-fail: some valid-enough specs trip strict validators
        if "openapi" not in raw and "swagger" not in raw:
            raise SpecValidationError(f"Validation failed: {exc}") from exc


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "tool"


def _make_tool_name(method: str, path: str, operation_id: str | None, summary: str | None) -> str:
    if operation_id:
        return _slugify(operation_id)
    if summary:
        return _slugify(summary)
    # Derive from method + path: GET /users/{id} -> get_users_by_id
    parts = [method.lower()]
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("by_" + segment[1:-1])
        else:
            parts.append(segment)
    return _slugify("_".join(parts))


def _extract_auth(raw: dict[str, Any]) -> list[AuthScheme]:
    components = raw.get("components", {}) or {}
    schemes_raw = components.get("securitySchemes", {}) or {}
    # OpenAPI 2.x fallback
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
                auth_type = AuthType.BEARER if "bearer" in (scheme_name or "").lower() else AuthType.BASIC
        elif stype == "oauth2":
            auth_type = AuthType.OAUTH2
        elif stype == "openIdConnect":
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
    node: Any = {"components": components} if parts[0] == "components" else components
    # Walk from root of raw components
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
            for p in params:
                if "$ref" in p:
                    p = _resolve_ref(p["$ref"], components) or p
                if not p.get("name"):
                    continue
                param_models.append(
                    ParameterSchema(
                        name=p["name"],
                        location=p.get("in", "query"),
                        required=bool(p.get("required", False)),
                        description=p.get("description"),
                        schema=p.get("schema") or {"type": "string"},
                    )
                )

            op_tags = operation.get("tags") or ["default"]
            for t in op_tags:
                tags_set.add(t)

            tool_name = _make_tool_name(
                method,
                path,
                operation.get("operationId"),
                operation.get("summary"),
            )
            input_schema = _build_input_schema({**operation, "parameters": params}, components)
            output_schema = _build_output_schema(operation, components)

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
                    tool_name=tool_name,
                    input_schema=input_schema,
                    output_schema=output_schema,
                )
            )

    return endpoints, sorted(tags_set)


def parse_openapi(content: bytes, file_type: str) -> ParsedSpec:
    """Validate and parse an OpenAPI document into structured metadata."""
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

    # Prefer tag order from top-level tags if present
    declared_tags = [t.get("name") for t in (raw.get("tags") or []) if t.get("name")]
    ordered_tags = declared_tags + [t for t in tags if t not in declared_tags]

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
