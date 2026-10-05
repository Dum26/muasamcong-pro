"""Private document object storage for local development and Cloud Run."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from server.config import ROOT, storage_backend


class StorageProvider(Protocol):
    def put(self, key: str, data: bytes, mime_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def object_key(user_id: str, document_id: str) -> str:
    if not all(len(part) == 32 and all(char in "0123456789abcdef" for char in part)
               for part in (user_id, document_id)):
        raise ValueError("Invalid document key")
    return f"documents/{user_id}/{document_id}"


def source_object_key(document_id: str, version: int) -> str:
    if len(document_id) != 32 or any(char not in "0123456789abcdef" for char in document_id):
        raise ValueError("Invalid source document key")
    if not 1 <= int(version) <= 1_000_000:
        raise ValueError("Invalid source document version")
    return f"source-documents/{document_id}/v{int(version)}"


class LocalStorageProvider:
    def __init__(self, root: Path | None = None):
        self.root = (root or ROOT / "data" / "uploads").resolve()

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return target

    def put(self, key: str, data: bytes, mime_type: str) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class CloudStorageProvider:
    def __init__(self, bucket_name: str):
        from google.cloud import storage
        self.bucket = storage.Client().bucket(bucket_name)

    def put(self, key: str, data: bytes, mime_type: str) -> None:
        self.bucket.blob(key).upload_from_string(data, content_type=mime_type, if_generation_match=0)

    def get(self, key: str) -> bytes:
        return self.bucket.blob(key).download_as_bytes()

    def delete(self, key: str) -> None:
        self.bucket.blob(key).delete()


@lru_cache(maxsize=4)
def _provider(backend: str, bucket: str) -> StorageProvider:
    return CloudStorageProvider(bucket) if backend == "gcs" else LocalStorageProvider()


def get_storage() -> StorageProvider:
    backend = storage_backend()
    return _provider(backend, os.environ.get("GCS_BUCKET", "").strip())
