"""Capture auth headers from MCP client requests (e.g. Postman) for upstream API calls."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# Headers forwarded from the inbound MCP HTTP request to outbound OpenAPI calls.
_client_auth_headers: ContextVar[dict[str, str]] = ContextVar(
    "mcp_client_auth_headers",
    default={},
)

# Persist last-seen auth headers per MCP session id (Streamable HTTP).
_session_auth: dict[str, dict[str, str]] = {}
_client_session_id: ContextVar[str | None] = ContextVar("mcp_client_session_id", default=None)

# Common auth-related header names (lowercase) to forward.
_AUTH_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
}


def extract_auth_headers_from_scope(scope: dict[str, Any]) -> dict[str, str]:
    """Pull Authorization / API-key style headers from an ASGI scope."""
    result: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers") or []:
        try:
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
            continue
    return None


def bind_request_auth(scope: dict[str, Any]):
    """
    Bind auth headers for this request.

    Returns a callable to reset contextvars (also updates session cache).
    """
    headers = extract_auth_headers_from_scope(scope)
    session_id = extract_session_id_from_scope(scope)
    if session_id and headers:
        _session_auth[session_id] = headers
    elif session_id and session_id in _session_auth and not headers:
        # Reuse auth from earlier request in the same MCP session
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
    """Optional auth passed as tool arguments (useful if client cannot set HTTP headers)."""
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
