"""URL slug helpers for MCP path-based routing."""

from __future__ import annotations

import re


def slugify(value: str) -> str:
    """Convert a human name into a URL-friendly slug."""
    text = value.strip().lower()
    # Drop common suffix for cleaner paths
    text = re.sub(r"\s+server$", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "server"


def mcp_path(spec_slug: str, server_slug: str) -> str:
    return f"/mcp/{spec_slug}/{server_slug}"
