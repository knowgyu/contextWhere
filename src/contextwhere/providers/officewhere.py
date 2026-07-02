from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .base import ProviderResult, result_unavailable

DEFAULT_BASE_URL = "http://127.0.0.1:18765"


def is_loopback(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


class OfficeWhereProvider:
    provider = "officewhere"

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or os.environ.get("OFFICEWHERE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> ProviderResult:
        if not is_loopback(self.base_url):
            return result_unavailable(self.provider, "unsafe_url", base_url=self.base_url)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(self.base_url + path, data=data, method=method, headers={"content-type": "application/json"})
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
        items = parsed.get("items") or parsed.get("results") or parsed.get("files") or []
        if not isinstance(items, list):
            items = []
        return ProviderResult(provider=self.provider, ok=True, status="ok", items=items, manifest=parsed if path.endswith("/manifest") else None, details=parsed)

    def health(self) -> ProviderResult:
        return self._request("GET", "/api/provider/v1/health")

    def manifest(self) -> ProviderResult:
        return self._request("GET", "/api/provider/v1/manifest")

    def search(self, query: str, limit: int = 20) -> ProviderResult:
        return self._request("POST", "/api/provider/v1/search", {"query": query, "limit": limit})
