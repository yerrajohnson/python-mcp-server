"""In-process MCP server registry — one FastAPI, many logical MCP endpoints."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.core.logging import get_logger
from app.services.request_auth import (
    auth_headers_from_tool_args,
    bind_request_auth,
    get_client_auth_headers,
)
from app.services.slugify import mcp_path, slugify

logger = get_logger(__name__)


def public_mcp_url(spec_slug: str, server_slug: str) -> str:
    settings = get_settings()
    base = (settings.public_base_url or f"http://127.0.0.1:{settings.port}").rstrip("/")
    return f"{base}{mcp_path(spec_slug, server_slug)}"


def _safe_fn_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"tool_{cleaned}"
    return cleaned or "tool"


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
    # Last Authorization / API-key headers seen from Postman/MCP client
    last_client_auth: dict[str, str] = field(default_factory=dict)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.mcp or not self.mcp.session_manager:
            await _send_json(send, 500, {"error": "MCP session manager not ready"})
            return
        if not self._started:
            await _send_json(send, 503, {"error": "MCP server lifecycle not started"})
            return
        # Capture Postman/client Authorization (and API-key) headers for tool execution
        reset = bind_request_auth(scope)
        from app.services.request_auth import extract_auth_headers_from_scope

        inbound = extract_auth_headers_from_scope(scope)
        if inbound:
            self.last_client_auth = dict(inbound)
        try:
            await self.mcp.session_manager.handle_request(scope, receive, send)
        finally:
            reset()


class McpRegistry:
    """Holds logical MCP servers and builds a dispatch ASGI app under /mcp."""

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
            except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
            pass

        tools = record.get("tools") or []
        auth_types = record.get("authentication") or []

        mount = mcp_path(spec_slug, server_slug)
        entry = RegisteredMcpServer(
            server_id=record["id"],
            spec_id=record.get("spec_id", ""),
            spec_slug=spec_slug,
            server_slug=server_slug,
            name=server_name,
            description=record.get("description"),
            tools=tools,
            authentication=auth_types,
            enabled=record.get("status", "running") != "stopped",
            mcp=mcp,
            mount_path=mount,
        )
        self._register_tools_lowlevel(mcp, tools, auth_types, entry)

        # Initialize streamable HTTP session manager
        _ = mcp.streamable_http_app()

        # Stop previous entry at same path if present
        if existing:
            existing._started = False

        self._servers[path_key] = entry
        self._by_id[record["id"]] = path_key
        logger.info(
            "Registered MCP endpoint %s (%d tools, enabled=%s)",
            mount,
            len(tools),
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
        """Register tools via low-level handlers to avoid FastMCP signature inspection issues."""
        from mcp.types import TextContent, Tool

        tool_map = {t.get("name") or f"tool_{i}": t for i, t in enumerate(tools)}

        @mcp._mcp_server.list_tools()
        async def _list_tools() -> list[Tool]:
            result: list[Tool] = []
            for name, tool in tool_map.items():
                schema = tool.get("input_schema") or {
                    "type": "object",
                    "properties": {},
                }
                result.append(
                    Tool(
                        name=name,
                        description=tool.get("description")
                        or f"{tool.get('method')} {tool.get('path')}",
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
            loc = prop.get("x-in") or prop.get("in")
            if loc == "path" or ("{" + prop_name + "}") in path:
                path = path.replace("{" + prop_name + "}", str(value))
            elif loc == "header":
                headers[prop_name] = str(value)
            elif prop_name == "body":
                body = value
            else:
                params[prop_name] = value

        # Auth-related tool args / leftover kwargs handling
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

        import os

        # Priority: Postman/MCP request headers → entry cache → tool args → process env
        client_headers = get_client_auth_headers()
        if not client_headers and entry and entry.last_client_auth:
            client_headers = dict(entry.last_client_auth)
        for hk, hv in client_headers.items():
            headers.setdefault(hk, hv)

        for hk, hv in auth_headers_from_tool_args(kwargs).items():
            headers.setdefault(hk, hv)

        if "Authorization" not in headers:
            token = (
                os.getenv("OAUTH_ACCESS_TOKEN")
                or os.getenv("API_BEARER_TOKEN")
                or os.getenv("API_TOKEN")
            )
            if token and any(a in ("bearer", "oauth2", "basic") for a in auth_types):
                if token.lower().startswith(("bearer ", "basic ")):
                    headers["Authorization"] = token
                elif "basic" in auth_types and ":" in token:
                    import base64

                    headers["Authorization"] = (
                        f"Basic {base64.b64encode(token.encode()).decode()}"
                    )
                else:
                    headers["Authorization"] = f"Bearer {token}"

        api_key_header = os.getenv("API_KEY_HEADER", "X-API-Key")
        if api_key_header not in headers and "X-API-Key" not in headers:
            api_key = os.getenv("API_KEY")
            if api_key and "apiKey" in auth_types:
                headers[api_key_header] = api_key

        # Basic auth from env username/password if still missing
        if "Authorization" not in headers and "basic" in auth_types:
            user = os.getenv("API_USERNAME")
            password = os.getenv("API_PASSWORD")
            if user and password:
                import base64

                raw = f"{user}:{password}".encode()
                headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"

        url_base = os.getenv("API_BASE_URL") or base_url
        url = f"{url_base.rstrip('/')}{path}" if url_base else path

        logger.debug(
            "Executing %s %s (auth_headers=%s)",
            method,
            url,
            sorted(headers.keys()),
        )

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
        except Exception:  # noqa: BLE001
            data = {"text": response.text}
        if response.status_code >= 400:
            return json.dumps(
                {"error": True, "status_code": response.status_code, "body": data},
                indent=2,
                default=str,
            )
        return json.dumps(data, indent=2, default=str)

    def _add_http_tool(
        self,
        mcp: FastMCP,
        tool: dict[str, Any],
        auth_types: list[str],
    ) -> None:
        # Kept for compatibility; prefer _register_tools_lowlevel
        return

    def build_dispatcher(self) -> ASGIApp:
        registry = self

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] not in ("http", "websocket"):
                return

            path = scope.get("path") or "/"
            # Handle both Mount-stripped paths (/spec/server) and full paths (/mcp/spec/server)
            if path.startswith("/mcp/"):
                path = path[4:]  # -> /spec/server...
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
                await _send_json(
                    send,
                    404,
                    {"error": f"Unknown MCP server '{spec_slug}/{server_slug}'"},
                )
                return
            if not entry.enabled:
                await _send_json(
                    send,
                    503,
                    {"error": "MCP server is stopped", "status": "stopped"},
                )
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
                record = {
                    **record,
                    "spec_slug": spec_slug,
                    "server_slug": server_slug,
                    "server_url": public_mcp_url(spec_slug, server_slug),
                    "port": 0,
                    "transport": "streamable-http",
                }
                self.register_record(record)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Failed to register MCP server %s: %s",
                    record.get("id"),
                    exc,
                )


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


_registry: McpRegistry | None = None


def get_registry() -> McpRegistry:
    global _registry
    if _registry is None:
        _registry = McpRegistry()
    return _registry
