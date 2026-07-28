"""Allocate unique local ports for generated MCP servers."""

from __future__ import annotations

import socket

from app.config import get_settings

BASE_PORT = 9101
MAX_PORT = 9199


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
