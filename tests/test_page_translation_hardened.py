"""Web-page translation: the fetch guards and the text extraction.

The endpoint takes a URL from the user, so the interesting part is what it
REFUSES. These tests pin the refusal behaviour (2026-10-21, reference-parity
queue — the reference product translates a pasted web page).

Nothing here touches the network: the HTTP layer is driven through
``httpx.MockTransport`` and DNS is stubbed.
"""
from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest

from app.services.page_fetch import (
    MAX_BYTES,
    PageFetchError,
    check_scheme_and_host,
    extract_readable_text,
    fetch_page,
    is_public_address,
    resolve_public_addresses,
)


def _public_resolver(*_args, **_kwargs):
    async def _resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    return _resolve


def _fake_getaddrinfo(host: str, port: int, *args, **kwargs):
    """Resolve like a real resolver: an IP literal resolves to itself."""
    try:
        ip = str(ipaddress.ip_address(host))
    except ValueError:
        ip = "93.184.216.34"
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """Stub DNS only — the guard code itself still runs."""
    import app.services.page_fetch as pf

    monkeypatch.setattr(pf.socket, "getaddrinfo", _fake_getaddrinfo)
    yield


# --------------------------------------------------------------------------- #
# Address classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254",
    "0.0.0.0", "100.64.0.1", "224.0.0.1", "::1", "fe80::1", "fc00::1",
])
def test_private_and_reserved_addresses_are_not_public(raw: str):
    assert is_public_address(ipaddress.ip_address(raw)) is False


@pytest.mark.parametrize("raw", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1::1"])
def test_public_addresses_are_public(raw: str):
    assert is_public_address(ipaddress.ip_address(raw)) is True


# --------------------------------------------------------------------------- #
# Scheme / host guards
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "data:text/html;base64,PGgxPmhpPC9oMT4=",
    "ftp://example.com/x.txt",
    "gopher://example.com/",
    "javascript:alert(1)",
])
def test_only_http_and_https_are_accepted(url: str):
    with pytest.raises(PageFetchError):
        check_scheme_and_host(url)


@pytest.mark.parametrize("host", [
    "localhost", "localhost.localdomain", "db.internal", "printer.local",
    "metadata.google.internal", "something.home.arpa",
])
def test_internal_host_names_are_refused_before_any_dns_lookup(host: str):
    with pytest.raises(PageFetchError):
        check_scheme_and_host(f"http://{host}/page")


def test_public_host_is_accepted():
    scheme, host, port = check_scheme_and_host("https://example.com/a/b?c=1")
    assert (scheme, host, port) == ("https", "example.com", 443)


def test_http_defaults_to_port_80():
    assert check_scheme_and_host("http://example.com/")[2] == 80


async def test_a_host_that_resolves_to_a_private_address_is_refused(monkeypatch):
    import app.services.page_fetch as pf

    def _private(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.5", port))]

    monkeypatch.setattr(pf.socket, "getaddrinfo", _private)
    with pytest.raises(PageFetchError):
        await resolve_public_addresses("evil.example", 80)


# --------------------------------------------------------------------------- #
# Text extraction
# --------------------------------------------------------------------------- #
def test_extraction_keeps_the_text_and_drops_scripts_and_navigation():
    html = """
    <html><head><title>Quarterly Report</title>
      <style>body { color: red }</style>
      <script>console.log('nope')</script>
    </head>
    <body>
      <nav>Home Products Pricing</nav>
      <main><h1>Quarterly Report</h1><p>Revenue grew by 11 percent.</p></main>
      <footer>Copyright 2026</footer>
    </body></html>
    """
    content = extract_readable_text(html)
    assert content.title == "Quarterly Report"
    assert "Revenue grew by 11 percent." in content.text
    assert "console.log" not in content.text
    assert "color: red" not in content.text
    assert "Home Products Pricing" not in content.text


def test_extraction_keeps_entities_readable():
    content = extract_readable_text("<p>Tom &amp; Jerry &mdash; 5 &lt; 7</p>")
    assert "Tom & Jerry" in content.text
    assert "—" in content.text


def test_extraction_of_a_page_without_text_is_empty():
    content = extract_readable_text("<html><body><script>1</script></body></html>")
    assert content.text == ""


def test_malformed_markup_does_not_raise():
    content = extract_readable_text("<p>unclosed <b>bold <p>next")
    assert "unclosed" in content.text


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_returns_the_readable_text_and_the_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><head><title>Doc</title></head><body><p>Hello there friend</p></body></html>",
        )

    page = await fetch_page("https://example.com/doc", client=_client(handler))
    assert page.title == "Doc"
    assert "Hello there friend" in page.text
    assert page.final_url.startswith("https://example.com")


async def test_a_redirect_to_a_private_url_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8088/admin"})
        return httpx.Response(200, content=b"secret")

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/x", client=_client(handler))


async def test_a_redirect_to_a_public_url_is_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/from":
            return httpx.Response(302, headers={"location": "https://example.org/to"})
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"<html><head><title>Final</title></head><body><p>Arrived safely here</p></body></html>",
        )

    page = await fetch_page("https://example.com/from", client=_client(handler))
    assert "Arrived safely here" in page.text
    assert page.final_url.startswith("https://example.org")


async def test_too_many_redirects_are_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/loop"})

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/loop", client=_client(handler))


async def test_a_non_html_content_type_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/file.pdf", client=_client(handler))


async def test_an_oversized_response_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"<p>x</p>" * (MAX_BYTES // 6 + 10)
        )

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/big", client=_client(handler))


async def test_an_error_status_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/missing", client=_client(handler))


async def test_a_page_without_readable_text_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"<html><body><script>1</script></body></html>"
        )

    with pytest.raises(PageFetchError):
        await fetch_page("https://example.com/empty", client=_client(handler))
