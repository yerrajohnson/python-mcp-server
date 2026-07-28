"""Persistent JSON-backed storage for specifications and generations."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles

from app.config import get_settings
from app.core.exceptions import SpecNotFoundError
from app.core.logging import get_logger
from app.models.schemas import (
    FileType,
    ParsedSpec,
    SpecStatus,
    Specification,
    SpecificationSummary,
)

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SpecStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._index_path = self.settings.specs_dir / "index.json"
        self._generations_path = self.settings.generated_dir / "index.json"

    # --- Index helpers ---

    async def _read_index(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {}
        async with aiofiles.open(self._index_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content) if content.strip() else {}

    async def _write_index(self, data: dict[str, Any]) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._index_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def _read_generations(self) -> dict[str, Any]:
        if not self._generations_path.exists():
            return {}
        async with aiofiles.open(self._generations_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content) if content.strip() else {}

    async def _write_generations(self, data: dict[str, Any]) -> None:
        self._generations_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._generations_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str))

    # --- Spec CRUD ---

    async def create_spec(
        self,
        name: str,
        original_filename: str,
        file_type: FileType,
        content: bytes,
    ) -> Specification:
        spec_id = str(uuid.uuid4())
        dest = self.settings.upload_dir / f"{spec_id}.{file_type.value}"
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

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
            auth_types = []
            if parsed:
                auth_types = [a.get("type", "") for a in parsed.get("auth_schemes", [])]
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
        summaries.sort(key=lambda s: s.upload_date, reverse=True)
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
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def save_parsed(self, spec_id: str, parsed: ParsedSpec, version: str) -> Specification:
        spec = await self.get_spec(spec_id)
        spec.parsed = parsed
        spec.version = version
        spec.name = parsed.info.title or spec.name
        spec.status = SpecStatus.PARSED
        spec.error_message = None
        meta_path = self.settings.specs_dir / f"{spec_id}.json"
        async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
            await f.write(parsed.model_dump_json(indent=2))
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

    # --- Generations ---

    async def save_generation(self, generation_id: str, data: dict[str, Any]) -> None:
        gens = await self._read_generations()
        gens[generation_id] = data
        await self._write_generations(gens)

    async def get_generation(self, generation_id: str) -> dict[str, Any]:
        gens = await self._read_generations()
        if generation_id not in gens:
            raise SpecNotFoundError(generation_id)
        return gens[generation_id]

    async def list_generations(self) -> list[dict[str, Any]]:
        gens = await self._read_generations()
        return list(gens.values())

    def generation_dir(self, generation_id: str) -> Path:
        path = self.settings.generated_dir / generation_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_generation_dir(self, generation_id: str) -> None:
        path = self.settings.generated_dir / generation_id
        if path.exists():
            shutil.rmtree(path)

    def _remove_output_folder(self, raw: dict[str, Any]) -> None:
        gen_id = raw.get("generation_id")
        if gen_id:
            self.remove_generation_dir(gen_id)
            return
        output = raw.get("output_folder")
        if not output:
            return
        path = Path(output)
        if not path.is_absolute():
            path = (self.settings.data_dir.parent / output).resolve()
        if path.exists() and path.is_dir():
            shutil.rmtree(path)

    # --- MCP Server registry ---

    @property
    def _mcp_index_path(self) -> Path:
        return self.settings.generated_dir / "mcp_servers.json"

    @property
    def _batches_path(self) -> Path:
        return self.settings.generated_dir / "batches.json"

    async def _read_mcp_servers(self) -> dict[str, Any]:
        if not self._mcp_index_path.exists():
            return {}
        async with aiofiles.open(self._mcp_index_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content) if content.strip() else {}

    async def _write_mcp_servers(self, data: dict[str, Any]) -> None:
        self._mcp_index_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._mcp_index_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def list_mcp_servers(self) -> list[dict[str, Any]]:
        data = await self._read_mcp_servers()
        servers = list(data.values())
        servers.sort(key=lambda s: s.get("created_date", ""), reverse=True)
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
        return {
            "id": server_id,
            "name": raw.get("name"),
            "tool_count": tool_count,
        }

    async def _remove_server_from_batches(
        self,
        server_id: str,
        generation_id: str | None,
    ) -> None:
        if not self._batches_path.exists():
            return
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as f:
            content = await f.read()
            batches = json.loads(content) if content.strip() else {}
        changed = False
        for batch in batches.values():
            servers = batch.get("servers") or []
            filtered = [
                s
                for s in servers
                if s.get("id") != server_id
                and s.get("temp_id") != server_id
                and (not generation_id or s.get("generation_id") != generation_id)
            ]
            if len(filtered) != len(servers):
                batch["servers"] = filtered
                changed = True
        if changed:
            async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(batches, indent=2, default=str))

    async def delete_mcp_servers_for_spec(self, spec_id: str) -> list[str]:
        """Delete all MCP servers generated from a specification."""
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
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as f:
            content = await f.read()
            batches = json.loads(content) if content.strip() else {}
        removed = [batch_id for batch_id, batch in batches.items() if batch.get("spec_id") == spec_id]
        if not removed:
            return
        for batch_id in removed:
            batches.pop(batch_id)
        async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(batches, indent=2, default=str))
        logger.info("Removed %d wizard batch(es) for spec %s", len(removed), spec_id)

    async def used_mcp_ports(self) -> set[int]:
        data = await self._read_mcp_servers()
        return {int(s["port"]) for s in data.values() if s.get("port")}

    async def save_batch(self, batch_id: str, payload: dict[str, Any]) -> None:
        if not self._batches_path.exists():
            batches: dict[str, Any] = {}
        else:
            async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as f:
                content = await f.read()
                batches = json.loads(content) if content.strip() else {}
        batches[batch_id] = payload
        async with aiofiles.open(self._batches_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(batches, indent=2, default=str))

    async def get_batch(self, batch_id: str) -> dict[str, Any]:
        if not self._batches_path.exists():
            raise SpecNotFoundError(batch_id)
        async with aiofiles.open(self._batches_path, "r", encoding="utf-8") as f:
            content = await f.read()
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
