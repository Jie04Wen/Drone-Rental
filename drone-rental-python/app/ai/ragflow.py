"""RAGFlow HTTP client corresponding to RagflowClient/RagflowService."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import Settings

LOGGER = logging.getLogger(__name__)


class RagflowClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return (
            self.settings.ai_ragflow_enabled
            and bool(self.settings.ai_ragflow_base_url)
            and bool(self.settings.ai_ragflow_api_key)
        )

    def _url(self, path: str) -> str:
        return self.settings.ai_ragflow_base_url.rstrip("/") + path

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.ai_ragflow_api_key:
            headers["Authorization"] = "Bearer " + self.settings.ai_ragflow_api_key
        return headers

    def list_datasets(self) -> list[dict[str, Any]]:
        if not self.available:
            return []
        try:
            response = httpx.get(self._url("/api/v1/datasets"), headers=self._headers(), timeout=15)
            response.raise_for_status()
            data = response.json().get("data") or []
            return [
                {"id": item.get("id"), "name": item.get("name"), "doc_num": item.get("doc_num", 0)}
                for item in data
            ]
        except Exception as exc:
            LOGGER.warning("RAGFlow list_datasets failed: %s", exc)
            return []

    def upload_document(self, dataset_id: str, filename: str, content: bytes) -> dict[str, Any]:
        if not self.available:
            return {"error": "RAGFlow not configured"}
        try:
            headers = self._headers()
            headers.pop("Content-Type", None)
            response = httpx.post(
                self._url(f"/api/v1/datasets/{dataset_id}/documents"),
                headers=headers,
                files={"file": (filename, content)},
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("data") or {}
        except Exception as exc:
            LOGGER.warning("RAGFlow upload_document failed: %s", exc)
            return {"error": str(exc)}

    def retrieval(self, dataset_ids: list[str], query: str, top_k: int) -> list[dict[str, Any]]:
        if not self.available or not dataset_ids:
            return []
        try:
            response = httpx.post(
                self._url("/api/v1/retrieval"),
                headers=self._headers(),
                json={
                    "question": query,
                    "dataset_ids": dataset_ids,
                    "page": 1,
                    "page_size": top_k,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (None, 0):
                LOGGER.warning("RAGFlow retrieval failed: %s", payload.get("message", "unknown error"))
                return []
            chunks = ((payload.get("data") or {}).get("chunks") or [])
            return [
                {
                    "content": item.get("content", ""),
                    "document_name": item.get("document_name", ""),
                    "similarity": item.get("similarity", 0.0),
                }
                for item in chunks
            ]
        except Exception as exc:
            LOGGER.warning("RAGFlow retrieval failed: %s", exc)
            return []

    def retrieve_context(self, query: str, top_k: int = 3) -> str | None:
        dataset_ids = self.settings.ragflow_dataset_ids
        if not dataset_ids:
            datasets = self.list_datasets()
            dataset_ids = [str(datasets[0]["id"])] if datasets and datasets[0].get("id") else []
        chunks = self.retrieval(dataset_ids, query, top_k)
        if not chunks:
            return None
        lines = ["【知识库参考信息】"]
        lines.extend(f"[{index}] {item['content']}" for index, item in enumerate(chunks, 1))
        return "\n".join(lines) + "\n"
