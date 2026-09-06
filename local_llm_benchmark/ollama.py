"""Small standard-library client for the local Ollama HTTP API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when Ollama cannot complete a requested operation."""


def normalize_host(host: str) -> str:
    normalized = host.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = f"http://{normalized}"
    return normalized.rstrip("/") + "/"


def decode_ndjson_line(raw_line: bytes) -> dict[str, Any] | None:
    line = raw_line.strip()
    if not line:
        return None
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        preview = line[:200].decode("utf-8", errors="replace")
        raise OllamaError(f"Invalid NDJSON from Ollama: {preview}") from exc
    if not isinstance(value, dict):
        raise OllamaError("Ollama returned a non-object NDJSON event")
    if value.get("error"):
        raise OllamaError(f"Ollama stream error: {value['error']}")
    return value


class OllamaClient:
    def __init__(self, host: str, timeout_seconds: float = 600.0) -> None:
        self.host = normalize_host(host)
        self.timeout_seconds = timeout_seconds

    def _url(self, path: str) -> str:
        return urljoin(self.host, path.lstrip("/"))

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.load(response)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama HTTP {exc.code} for {path}: {body}") from exc
        except URLError as exc:
            raise OllamaError(f"Cannot reach Ollama at {self.host}: {exc.reason}") from exc
        if not isinstance(value, dict):
            raise OllamaError(f"Ollama returned a non-object response for {path}")
        if value.get("error"):
            raise OllamaError(f"Ollama error for {path}: {value['error']}")
        return value

    def version(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/version")

    def list_models(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/tags")

    def list_running_models(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/ps")

    def show_model(self, model: str) -> dict[str, Any]:
        return self._request_json("POST", "/api/show", {"model": model, "verbose": False})

    def unload_model(self, model: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/generate",
            {"model": model, "stream": False, "keep_alive": 0},
        )

    def preload_model(self, model: str, keep_alive: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/generate",
            {"model": model, "stream": False, "keep_alive": keep_alive},
        )

    def stream_chat(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        request = Request(
            self._url("/api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/x-ndjson",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    event = decode_ndjson_line(raw_line)
                    if event is not None:
                        yield event
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama HTTP {exc.code} for /api/chat: {body}") from exc
        except URLError as exc:
            raise OllamaError(f"Cannot reach Ollama at {self.host}: {exc.reason}") from exc
