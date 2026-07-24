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


_store: SpecStore | None = None


def get_store() -> SpecStore:
    global _store
    if _store is None:
        _store = SpecStore()
    return _store
