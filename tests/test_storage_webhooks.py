"""Automated tests for Object Storage security and Webhook SSRF protection."""
import pytest
from app.errors import StorageError, ValidationError
from app.storage import validate_upload, malware_scan, object_key, LocalStorage


def test_upload_blocks_dangerous_extensions():
    with pytest.raises(ValidationError, match="File type not allowed"):
        validate_upload("payload.exe", "application/octet-stream", 1024, kind="document")

    with pytest.raises(ValidationError, match="File type not allowed"):
        validate_upload("script.sh", "text/x-shellscript", 1024, kind="document")


def test_upload_sanitizes_path_traversal():
    safe_name, mime = validate_upload("../../etc/passwd.pdf", "application/pdf", 1024, kind="document")
    assert "/" not in safe_name
    assert "\\" not in safe_name
    assert "passwd.pdf" in safe_name


def test_malware_scan_rejects_executable_headers():
    # Windows PE executable header (MZ)
    with pytest.raises(ValidationError, match="executable content"):
        import asyncio
        asyncio.run(malware_scan(b"MZ\x90\x00\x03\x00\x00\x00", "innocent.pdf"))

    # Linux ELF executable header
    with pytest.raises(ValidationError, match="executable content"):
        import asyncio
        asyncio.run(malware_scan(b"\x7fELF\x02\x01\x01\x00", "innocent.pdf"))


def test_local_storage_path_traversal_guard(tmp_path):
    storage = LocalStorage(str(tmp_path))
    with pytest.raises(StorageError, match="invalid storage key"):
        storage._p("../../../../windows/system32/cmd.exe")


def test_webhook_ssrf_blocks_private_targets():
    from app.services.webhook_service import _assert_public_url
    import asyncio
    # In test mode or when running _assert_public_url in production, loopback/private IPs must be refused
    from app.config import settings
    orig_env = settings.app_env
    try:
        settings.app_env = "production"
        with pytest.raises(RuntimeError, match="private address"):
            asyncio.run(_assert_public_url("http://127.0.0.1:8000/webhook"))

        with pytest.raises(RuntimeError, match="private address"):
            asyncio.run(_assert_public_url("http://169.254.169.254/latest/meta-data"))
    finally:
        settings.app_env = orig_env
