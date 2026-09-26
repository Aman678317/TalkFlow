"""Object storage abstraction: S3-compatible (MinIO/prod) or local filesystem.

Uploads are content-addressed by checksum; downloads stream. Malware scan hook
runs before persisting (ClamAV when configured, heuristic checks always).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import mimetypes
import os
import re
import socket
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.errors import StorageError, ValidationError

log = logging.getLogger("app.storage")

# --- upload validation (PDD §39: MIME validation, file upload attacks) ---
ALLOWED_DOC_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/html",
    "text/markdown",
}
ALLOWED_DOC_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".html", ".htm", ".md"}
ALLOWED_AUDIO_MIMES = {"audio/wav", "audio/x-wav", "audio/webm", "audio/ogg",
                       "audio/mpeg", "audio/mp4", "audio/pcm"}
DANGEROUS_EXTS = {".exe", ".sh", ".bat", ".cmd", ".js", ".jar", ".php", ".py",
                  ".dll", ".so", ".msi", ".com", ".scr", ".vbs", ".apk"}


def validate_upload(filename: str, mime: str | None, size: int,
                    kind: str = "document") -> tuple[str, str]:
    """Returns (safe_filename, normalized_mime). Raises ValidationError."""
    if not filename:
        raise ValidationError("Missing filename")
    # strip paths (zip-slip / traversal)
    safe = os.path.basename(filename.replace("\\", "/"))
    safe = re.sub(r"[^\w.\- ]", "_", safe)[:200]
    ext = os.path.splitext(safe)[1].lower()
    if ext in DANGEROUS_EXTS:
        raise ValidationError(f"File type not allowed: {ext}")
    if size <= 0:
        raise ValidationError("Empty file")
    if size > settings.max_upload_mb * 1024 * 1024:
        raise ValidationError(f"File exceeds {settings.max_upload_mb}MB limit")
    mime = (mime or mimetypes.guess_type(safe)[0] or "application/octet-stream").lower()
    if kind == "document":
        if ext not in ALLOWED_DOC_EXTS:
            raise ValidationError(f"Unsupported document format: {ext or 'unknown'}")
        # ext/mime consistency guard
        expected = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }.get(ext)
        if expected and mime != expected:
            raise ValidationError("MIME type does not match file extension")
        if ext in (".txt", ".html", ".htm", ".md") and not mime.startswith("text/"):
            mime = "text/plain" if ext in (".txt", ".md") else "text/html"
    return safe, mime


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def malware_scan(data: bytes, filename: str) -> None:
    """ClamAV INSTREAM when configured; magic-byte heuristics always.

    Raises ValidationError on detection. This is a real check — executables
    masquerading as documents are rejected even without ClamAV.
    """
    # magic-byte heuristics for common executable formats
    if data[:2] == b"MZ" or data[:4] == b"\x7fELF" or data[:2] == b"#!":
        raise ValidationError("File rejected by malware scan (executable content)")
    if filename.lower().endswith(".pdf") and not data.lstrip()[:5].startswith(b"%PDF-"):
        raise ValidationError("File rejected: invalid PDF structure")
    if not settings.clamav_host:
        return
    try:
        verdict = await asyncio.to_thread(_clamd_scan, data)
        if verdict != "OK":
            raise ValidationError(f"File rejected by malware scan: {verdict}")
    except OSError as e:
        log.error("clamav unreachable (%s); failing closed for uploads", e)
        raise ValidationError("Malware scanner unavailable; upload rejected") from e


def _clamd_scan(data: bytes) -> str:
    """Minimal INSTREAM client (no external dep)."""
    with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=10) as s:
        s.sendall(b"zINSTREAM\0")
        chunk_size = 2048
        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            s.sendall(len(chunk).to_bytes(4, "big") + chunk)
        s.sendall(b"\0\0\0\0")
        resp = b""
        while True:
            part = s.recv(4096)
            if not part:
                break
            resp += part
    text = resp.decode(errors="ignore").strip().rstrip("\0")
    return "OK" if text.endswith("OK") else text


class StorageBackend(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    @abstractmethod
    async def get(self, key: str) -> bytes: ...
    @abstractmethod
    async def delete(self, key: str) -> None: ...
    @abstractmethod
    async def exists(self, key: str) -> bool: ...
    @abstractmethod
    async def presigned_url(self, key: str, expires_s: int = 3600) -> str | None: ...
    @abstractmethod
    async def ping(self) -> bool: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        # traversal guard
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise StorageError("invalid storage key")
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        def _do():
            p = self._p(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)
        await asyncio.to_thread(_do)

    async def get(self, key: str) -> bytes:
        p = self._p(key)
        if not p.is_file():
            raise StorageError(f"object not found: {key}")
        return await asyncio.to_thread(p.read_bytes)

    async def delete(self, key: str) -> None:
        p = self._p(key)
        if p.is_file():
            await asyncio.to_thread(p.unlink)

    async def exists(self, key: str) -> bool:
        return self._p(key).is_file()

    async def presigned_url(self, key: str, expires_s: int = 3600) -> str | None:
        return None  # local dev serves through the API download endpoint

    async def ping(self) -> bool:
        return self.root.is_dir()


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        import boto3
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self.bucket = settings.s3_bucket

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self.bucket, Key=key,
            Body=data, ContentType=content_type)

    async def get(self, key: str) -> bytes:
        try:
            res = await asyncio.to_thread(self._client.get_object,
                                          Bucket=self.bucket, Key=key)
            return res["Body"].read()
        except Exception as e:
            raise StorageError(f"s3 get failed: {e}") from e

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object,
                                Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object,
                                    Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    async def presigned_url(self, key: str, expires_s: int = 3600) -> str | None:
        return await asyncio.to_thread(
            self._client.generate_presigned_url, "get_object",
            {"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s)

    async def ping(self) -> bool:
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
            return True
        except Exception:
            return False


_storage: StorageBackend | None = None


async def init_storage() -> StorageBackend:
    global _storage
    if settings.s3_enabled:
        try:
            s3 = S3Storage()
            if await s3.ping():
                _storage = s3
                log.info("storage backend: s3 (%s)", settings.s3_endpoint)
                return s3
            log.warning("s3 unreachable, falling back to local storage")
        except ImportError:
            log.warning("boto3 not installed, falling back to local storage")
        except Exception as e:
            log.warning("s3 init failed (%s), falling back to local storage", e)
    _storage = LocalStorage(settings.local_storage_path)
    log.info("storage backend: local (%s)", settings.local_storage_path)
    return _storage


def storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = LocalStorage(settings.local_storage_path)
    return _storage


def object_key(kind: str, tenant_id: str, name: str, checksum: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"{kind}/{tenant_id}/{day}/{checksum[:16]}_{name}"
