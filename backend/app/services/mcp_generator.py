"""Jinja2-based MCP server code generator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.logging import get_logger
from app.models.schemas import AuthScheme

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "server"


class MCPGenerator:
    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["tojson"] = lambda v: json.dumps(v, indent=2)

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

        slug = _slug(server_name)
        auth_types = sorted({a.type.value for a in auth_schemes})
        ctx = {
            "server_name": server_name,
            "server_slug": slug,
            "tools": tools,
            "auth_schemes": [a.model_dump() for a in auth_schemes],
            "auth_types": auth_types,
            "tool_count": len(tools),
        }

        written: list[str] = []

        # server.py
        server_code = self.env.get_template("server.py.j2").render(**ctx)
        (output_dir / "server.py").write_text(server_code, encoding="utf-8")
        written.append("server.py")

        # tools/__init__.py + per-tool modules
        (output_dir / "tools" / "__init__.py").write_text(
            '"""Auto-generated MCP tools."""\n',
            encoding="utf-8",
        )
        written.append("tools/__init__.py")

        tool_tpl = self.env.get_template("tool.py.j2")
        for tool in tools:
            fname = f"{tool['name']}.py"
            code = tool_tpl.render(tool=tool, auth_types=auth_types)
            (output_dir / "tools" / fname).write_text(code, encoding="utf-8")
            written.append(f"tools/{fname}")

        # schemas
        for name, schema in schemas.items():
            path = output_dir / "schemas" / f"{name}.json"
            path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            written.append(f"schemas/{name}.json")

        # requirements.txt
        reqs = self.env.get_template("requirements.txt.j2").render(**ctx)
        (output_dir / "requirements.txt").write_text(reqs, encoding="utf-8")
        written.append("requirements.txt")

        # README.md
        readme = self.env.get_template("README.md.j2").render(**ctx)
        (output_dir / "README.md").write_text(readme, encoding="utf-8")
        written.append("README.md")

        # auth helper
        auth_code = self.env.get_template("auth.py.j2").render(**ctx)
        (output_dir / "auth.py").write_text(auth_code, encoding="utf-8")
        written.append("auth.py")

        # http client helper
        http_code = self.env.get_template("http_client.py.j2").render(**ctx)
        (output_dir / "http_client.py").write_text(http_code, encoding="utf-8")
        written.append("http_client.py")

        logger.info("Generated MCP project at %s (%d files)", output_dir, len(written))
        return written
