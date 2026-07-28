"""LangGraph-style agent workflow for MCP server generation.

Nodes:
  validate → parse → extract_auth → extract_endpoints →
  generate_tools → generate_schemas → generate_server → package
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.logging import get_logger
from app.models.schemas import AuthScheme, EndpointInfo, ParsedSpec, Specification
from app.services.mcp_generator import MCPGenerator
from app.services.storage import SpecStore

logger = get_logger(__name__)

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


def _endpoint_key(ep: EndpointInfo) -> str:
    return f"{ep.method}:{ep.path}"


def _intelligent_tool_name(ep: EndpointInfo, used: set[str]) -> str:
    """Choose a clear, unique MCP tool name."""
    base = ep.tool_name or "tool"
    # Prefer verb_noun style
    if ep.summary:
        candidate = re.sub(r"[^a-z0-9]+", "_", ep.summary.lower()).strip("_")
        if candidate and len(candidate) < 64:
            base = candidate
    if ep.operation_id:
        candidate = re.sub(r"[^a-z0-9]+", "_", ep.operation_id.lower()).strip("_")
        if candidate:
            base = candidate

    name = base
    i = 2
    while name in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name)
    return name


class MCPGenerationAgent:
    """Orchestrates the OpenAPI → MCP generation pipeline."""

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
        except Exception as exc:  # noqa: BLE001
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
        types = ", ".join(sorted({s.type.value for s in state.auth_schemes}))
        self._log(state, f"Detected auth: {types}", 35, cb)

    async def _extract_endpoints(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Selecting endpoints for MCP tools…", 50, cb)
        count = sum(len(v) for v in state.selected_endpoints.values())
        self._log(state, f"{count} endpoint(s) selected", 50, cb)

    async def _generate_tools(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Generating MCP tool definitions…", 65, cb)
        used_names: set[str] = set()
        for spec in state.specs:
            assert spec.parsed is not None
            selected = set(state.selected_endpoints.get(spec.id, []))
            base_url = ""
            if spec.parsed.info.servers:
                base_url = spec.parsed.info.servers[0].get("url", "")

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
                        "parameters": [p.model_dump(by_alias=True) for p in ep.parameters],
                        "request_body": ep.request_body,
                        "responses": ep.responses,
                        "input_schema": ep.input_schema or {"type": "object", "properties": {}},
                        "output_schema": ep.output_schema or {"type": "object"},
                        "security": ep.security,
                        "spec_id": spec.id,
                        "spec_name": spec.name,
                        "auth_schemes": [a.model_dump(mode="json") for a in spec.parsed.auth_schemes],
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
        files = self.generator.generate(
            output_dir=state.output_dir,
            server_name=state.server_name,
            tools=state.tools,
            auth_schemes=state.auth_schemes,
            schemas=state.schemas,
        )
        state.files = files
        self._log(state, f"Rendered {len(files)} file(s)", 90, cb)

    async def _package(self, state: AgentState, cb: LogCallback | None) -> None:
        self._log(state, "Packaging generated project…", 100, cb)
        assert state.output_dir is not None
        await self.store.save_generation(
            state.generation_id,
            {
                "generation_id": state.generation_id,
                "server_name": state.server_name,
                "tool_count": len(state.tools),
                "authentication": sorted({a.type.value for a in state.auth_schemes}),
                "selected_endpoints": [
                    f"{t['method']} {t['path']}" for t in state.tools
                ],
                "output_folder": str(state.output_dir),
                "status": "completed",
                "files": state.files,
                "logs": state.logs,
            },
        )
        self._log(state, "Generation complete", 100, cb)
