"""Small RAGFlow HTTP client for offline curriculum-evidence scripts.

This module is intentionally script-scoped. Do not import it from lesson runtime,
TeachingMove planner, redirect policy, or the live classroom RAG chain.
"""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request


class RAGFlowError(RuntimeError):
    """Raised for configured RAGFlow calls that fail."""


class RAGFlowTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, dict[str, str], bytes]: ...


@dataclass(frozen=True)
class RAGFlowConfig:
    base_url: str = ""
    api_key: str = ""
    dataset_id: str = ""
    timeout_seconds: float = 10.0
    enabled: bool = False

    @classmethod
    def from_env(cls) -> "RAGFlowConfig":
        enabled = os.getenv("PEPTUTOR_RAGFLOW_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
        timeout_raw = os.getenv("RAGFLOW_TIMEOUT_SECONDS", "10").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 10.0
        return cls(
            base_url=os.getenv("RAGFLOW_BASE_URL", "").strip().rstrip("/"),
            api_key=os.getenv("RAGFLOW_API_KEY", "").strip(),
            dataset_id=os.getenv("RAGFLOW_DATASET_ID", "").strip(),
            timeout_seconds=timeout,
            enabled=enabled,
        )

    def disabled_reason(self) -> str:
        if not self.enabled:
            return "PEPTUTOR_RAGFLOW_ENABLED is not enabled."
        if not self.base_url:
            return "RAGFLOW_BASE_URL is not configured."
        if not self.api_key:
            return "RAGFLOW_API_KEY is not configured."
        return ""


def _default_transport(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    data: bytes | None,
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    req = request.Request(url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - configured operator URL.
            return response.status, dict(response.headers), response.read()
    except error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except error.URLError as exc:
        raise RAGFlowError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise RAGFlowError("RAGFlow request timed out") from exc


class RAGFlowClient:
    def __init__(
        self,
        config: RAGFlowConfig | None = None,
        *,
        transport: RAGFlowTransport | None = None,
    ) -> None:
        self.config = config or RAGFlowConfig.from_env()
        self._transport = transport or _default_transport

    @property
    def configured(self) -> bool:
        return not self.config.disabled_reason()

    def health_check(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {
                "reachable": False,
                "api_auth_ok": False,
                "dataset_exists": False,
                "warning": self.config.disabled_reason(),
            }
        if self.config.disabled_reason():
            return {
                "reachable": False,
                "api_auth_ok": False,
                "dataset_exists": False,
                "warning": self.config.disabled_reason(),
            }
        try:
            datasets = self.list_datasets()
        except RAGFlowError as exc:
            return {
                "reachable": False,
                "api_auth_ok": False,
                "dataset_exists": False,
                "warning": str(exc),
            }
        dataset_exists = not self.config.dataset_id or any(
            str(dataset.get("id", "")) == self.config.dataset_id for dataset in datasets
        )
        return {
            "reachable": True,
            "api_auth_ok": True,
            "dataset_exists": dataset_exists,
            "warning": "" if dataset_exists else f"Dataset {self.config.dataset_id!r} was not found.",
        }

    def list_datasets(self, *, page: int = 1, page_size: int = 100) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/api/v1/datasets", query={"page": page, "page_size": page_size})
        return _extract_items(payload)

    def list_documents(
        self,
        dataset_id: str | None = None,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        dataset = dataset_id or self.config.dataset_id
        if not dataset:
            raise RAGFlowError("dataset_id is required")
        payload = self._request_json(
            "GET",
            f"/api/v1/datasets/{parse.quote(dataset)}/documents",
            query={"page": page, "page_size": page_size},
        )
        return _extract_items(payload)

    def upload_document(self, path: Path, dataset_id: str | None = None) -> dict[str, Any]:
        dataset = dataset_id or self.config.dataset_id
        if not dataset:
            raise RAGFlowError("dataset_id is required")
        file_path = Path(path)
        if not file_path.is_file():
            raise RAGFlowError(f"Document not found: {file_path}")
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        boundary = f"----peptutor-ragflow-{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode(),
                file_path.read_bytes(),
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        return self._request_json(
            "POST",
            f"/api/v1/datasets/{parse.quote(dataset)}/documents",
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def export_chunks(
        self,
        dataset_id: str | None = None,
        *,
        document_ids: list[str] | None = None,
        page_size: int = 1024,
    ) -> list[dict[str, Any]]:
        dataset = dataset_id or self.config.dataset_id
        if not dataset:
            raise RAGFlowError("dataset_id is required")
        documents = self.list_documents(dataset, page_size=page_size)
        allowed = set(document_ids or [])
        chunks: list[dict[str, Any]] = []
        for document in documents:
            document_id = str(document.get("id", ""))
            if not document_id or (allowed and document_id not in allowed):
                continue
            payload = self._request_json(
                "GET",
                f"/api/v1/datasets/{parse.quote(dataset)}/documents/{parse.quote(document_id)}/chunks",
                query={"page": 1, "page_size": page_size},
            )
            for chunk in _extract_items(payload):
                item = dict(chunk)
                item.setdefault("document_id", document_id)
                item.setdefault("document_name", document.get("name", ""))
                chunks.append(item)
        return chunks

    def retrieve(
        self,
        question: str,
        dataset_ids: list[str] | None = None,
        *,
        top_k: int = 6,
    ) -> dict[str, Any]:
        datasets = dataset_ids or ([self.config.dataset_id] if self.config.dataset_id else [])
        if not datasets:
            raise RAGFlowError("dataset_ids is required")
        return self._request_json(
            "POST",
            "/api/v1/retrieval",
            body={"question": question, "dataset_ids": datasets, "top_k": top_k, "top_n": top_k},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        data: bytes | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        if self.config.disabled_reason():
            raise RAGFlowError(self.config.disabled_reason())
        url = f"{self.config.base_url}{path}"
        if query:
            url = f"{url}?{parse.urlencode(query)}"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        request_data = data
        if body is not None:
            request_data = json.dumps(body).encode("utf-8")
        if request_data is not None:
            headers["Content-Type"] = content_type
        status, _, raw = self._transport(
            method,
            url,
            headers=headers,
            data=request_data,
            timeout=self.config.timeout_seconds,
        )
        text = raw.decode("utf-8", errors="replace") if raw else "{}"
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RAGFlowError(f"RAGFlow returned non-JSON response: HTTP {status}") from exc
        if status >= 400 or payload.get("code", 0) not in {0, "0", None}:
            message = payload.get("message") or payload.get("msg") or f"HTTP {status}"
            raise RAGFlowError(str(message))
        return payload


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "datasets", "documents", "chunks", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(key in data for key in ("id", "name")):
            return [data]
    return []
