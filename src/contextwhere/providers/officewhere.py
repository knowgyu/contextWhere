from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .base import ProviderResult, result_unavailable

DEFAULT_BASE_URL = "http://127.0.0.1:18765"
DISCOVERY_FILE = "provider-discovery.json"


def is_loopback(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def discovery_file_candidates(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> list[Path]:
    values = os.environ if env is None else env
    user_home = Path.home() if home is None else home
    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value.startswith("win"):
        roots = [values.get("LOCALAPPDATA"), values.get("APPDATA")]
        return [Path(root) / "OfficeWhere" / DISCOVERY_FILE for root in roots if root]
    if platform_value == "darwin":
        return [user_home / "Library" / "Application Support" / "OfficeWhere" / DISCOVERY_FILE]
    config_root = Path(values.get("XDG_CONFIG_HOME") or user_home / ".config")
    return [config_root / "OfficeWhere" / DISCOVERY_FILE]


def discovered_base_urls(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> list[str]:
    urls: list[str] = []
    for path in discovery_file_candidates(env=env, home=home, platform_name=platform_name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(payload, dict)
            or payload.get("provider") != "OfficeWhere"
            or payload.get("contract_version") != "v1"
            or payload.get("api_base_path") != "/api/provider/v1"
        ):
            continue
        base_url = str(payload.get("base_url") or "").rstrip("/")
        if base_url and is_loopback(base_url) and base_url not in urls:
            urls.append(base_url)
    return urls


class OfficeWhereProvider:
    provider = "officewhere"

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        configured = base_url or os.environ.get("OFFICEWHERE_BASE_URL")
        urls = [configured] if configured else [*discovered_base_urls(), DEFAULT_BASE_URL]
        self._base_urls = list(dict.fromkeys(url.rstrip("/") for url in urls if url))
        self.base_url = self._base_urls[0]
        self.timeout = timeout
        self._validated = False

    def _request_at(self, base_url: str, method: str, path: str, payload: dict | None = None) -> ProviderResult:
        if not is_loopback(base_url):
            return result_unavailable(self.provider, "unsafe_url", base_url=base_url)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(base_url + path, data=data, method=method, headers={"content-type": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            return result_unavailable(self.provider, "http_error", status_code=exc.code)
        except URLError as exc:
            return result_unavailable(self.provider, "not_running", error=str(exc.reason))
        except TimeoutError:
            return result_unavailable(self.provider, "timeout")
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError:
            return result_unavailable(self.provider, "invalid_json")
        if not isinstance(parsed, dict):
            return result_unavailable(self.provider, "invalid_json")
        items = parsed.get("items") or parsed.get("results") or parsed.get("files") or []
        if not isinstance(items, list):
            items = []
        return ProviderResult(provider=self.provider, ok=True, status="ok", items=items, manifest=parsed if path.endswith("/manifest") else None, details=parsed)

    def _request(self, method: str, path: str, payload: dict | None = None) -> ProviderResult:
        last_result: ProviderResult | None = None
        requires_identity = path.endswith(("/health", "/manifest"))
        for base_url in self._base_urls:
            result = self._request_at(base_url, method, path, payload)
            if result.ok and requires_identity:
                details = result.details or {}
                if details.get("provider") != "OfficeWhere" or details.get("contract_version") != "v1":
                    result = result_unavailable(self.provider, "invalid_provider", base_url=base_url)
            if result.ok:
                self.base_url = base_url
                self._base_urls = [base_url]
                self._validated = self._validated or requires_identity
                return result
            last_result = result
        return last_result or result_unavailable(self.provider, "not_running")

    def health(self) -> ProviderResult:
        return self._request("GET", "/api/provider/v1/health")

    def manifest(self) -> ProviderResult:
        return self._request("GET", "/api/provider/v1/manifest")

    def search(self, query: str, limit: int = 20) -> ProviderResult:
        if not self._validated:
            health = self.health()
            if not health.ok:
                return health
        return self._request("POST", "/api/provider/v1/search", {"query": query, "limit": limit})
