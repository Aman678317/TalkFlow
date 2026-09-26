"""Object storage abstraction: S3/MinIO in prod, local filesystem in dev."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from globaltalk.core.config import settings
from globaltalk.core.errors import StorageError
from globaltalk.core.logging import get_logger

log = get_logger("storage")


class StorageBackend(Protocol):
    name: str

    def put(self, key: str, data: BinaryIO | bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, key: str) -> bytes: ...
    def open_write(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def presigned_url(self, key: str, expires: int = 3600) -> str | None: ...
    def healthy(self) -> bool: ...


class LocalStorage:
    name = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise StorageError("Invalid storage key", code="storage_path_traversal")
        return p

    def put(self, key: str, data, content_type: str = "application/octet-stream") -> str:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            with p.open("wb") as f:
                shutil.copyfileobj(data, f)
        return key

    def get(self, key: str) -> bytes:
        p = self._p(key)
        if not p.exists():
            raise StorageError(f"Object not found: {key}", http_status=404, code="storage_not_found")
        return p.read_bytes()

    def open_write(self, key: str) -> BinaryIO:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p.open("wb")

    def delete(self, key: str) -> None:
        p = self._p(key)
        if p.exists():
            p.unlink()

    def exists(self, key: str) -> bool:
        return self._p(key).exists()

    def presigned_url(self, key: str, expires: int = 3600) -> str | None:
        return None

    def healthy(self) -> bool:
        try:
            probe = self.root / ".health"
            probe.write_text("ok")
            return True
        except Exception:
            return False


class S3Storage:
    name = "s3"

    def __init__(self):
        import boto3
        self._client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region)
        self.bucket = settings.s3_bucket

    def put(self, key: str, data, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError(f"Object not found: {key}", http_status=404,
                               code="storage_not_found", details={"reason": str(exc)})

    def open_write(self, key: str):
        import tempfile
        return _S3WriteThrough(self, key, tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024))

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def presigned_url(self, key: str, expires: int = 3600) -> str | None:
        return self._client.generate_presigned_url("get_object",
                                                   Params={"Bucket": self.bucket, "Key": key},
                                                   ExpiresIn=expires)

    def healthy(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


class _S3WriteThrough:
    def __init__(self, storage: S3Storage, key: str, fh):
        self._s, self._k, self._fh = storage, key, fh

    def write(self, b):
        return self._fh.write(b)

    def close(self):
        self._fh.seek(0)
        self._s._client.put_object(Bucket=self._s.bucket, Key=self._k, Body=self._fh.read())
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        if settings.storage_backend == "s3":
            try:
                _backend = S3Storage()
            except Exception as exc:
                log.warning("storage_fallback_local", extra={"reason": str(exc)})
                _backend = LocalStorage(settings.resolve(settings.storage_local_path))
        else:
            _backend = LocalStorage(settings.resolve(settings.storage_local_path))
    return _backend


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(fh, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    while True:
        b = fh.read(chunk)
        if not b:
            break
        h.update(b)
    fh.seek(0)
    return h.hexdigest()
