"""Rule-based logical grouping of OpenAPI endpoints into MCP servers."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from app.models.schemas import EndpointInfo, LogicalGroup, LogicalGroupEndpoint


def _title_case(name: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", name).strip()
    if not cleaned:
        return "General"
    return " ".join(w.capitalize() for w in cleaned.split())


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
    """Group selected endpoints by OpenAPI tag, falling back to resource path."""
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

        desc = f"MCP tools for {name.lower()} operations ({len(eps)} endpoints)."
        groups.append(
            LogicalGroup(
                id=str(uuid.uuid4()),
                name=name,
                description=desc,
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
