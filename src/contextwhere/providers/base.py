from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contextwhere.schemas import EvidenceRecord, UnavailableProvider, evidence_from_item


@dataclass
class ProviderResult:
    provider: str
    ok: bool
    status: str
    items: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    unavailable: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "status": self.status,
            "items": self.items,
            "manifest": self.manifest,
            "unavailable": self.unavailable,
            "details": self.details,
        }


def result_unavailable(provider: str, reason: str, **details: Any) -> ProviderResult:
    unavailable = UnavailableProvider(provider=provider, reason=reason, details=details).to_dict()
    return ProviderResult(provider=provider, ok=False, status="unavailable", unavailable=unavailable, details=details)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "tasks", "results", "files", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def load_fixture_records(provider: str, fixture: Path, default_kind: str = "item") -> list[EvidenceRecord]:
    payload = load_json(fixture)
    return [evidence_from_item(provider, item, default_kind=default_kind) for item in extract_items(payload)]
