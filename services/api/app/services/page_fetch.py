"""Safe fetching and text extraction for web-page translation.

The reference product translates a pasted web page. This is the server half of
that feature — and the half that has to be careful, because the URL comes
from the user and the fetch must not become a way to reach the machine's own
network.

Guards, all applied before a single byte is requested:

* ``http``/``https`` only — no ``file://``, ``data:``, ``ftp://`` …
* the host must resolve to **public** addresses only: loopback, private,
  link-local (where the cloud metadata endpoints live), carrier-grade NAT,
  multicast and reserved ranges are refused, and a host that resolves to
  *any* of them is refused even when it also has a public address
* host names that are always internal (``localhost``, ``*.internal`` …) are
  refused before any DNS lookup
* a response size cap, a request timeout and a content-type check
* redirects are followed manually (at most 3 hops) and **every hop is
  re-validated** — a public URL must not be able to bounce us onto localhost

Text extraction uses the standard library only, so this adds no dependency.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger("app.page_fetch")

MAX_BYTES = 2_000_000
MAX_TEXT_CHARS = 20_000
TIMEOUT_S = 10.0
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_MEDIA_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
}
BLOCKED_HOST_SUFFIXES = (".local", ".localdomain", ".internal", ".home.arpa")

#: Carrier-grade NAT space — not "private" in ipaddress terms, but not public.
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

USER_AGENT = "GlobalTalkAI-PageTranslate/1.0 (+https://github.com/Aman678317/TalkFlow)"


class PageFetchError(ValueError):
    """The page could not be fetched (unsafe, unreachable, or not a document)."""


@dataclass
class PageContent:
    title: str = ""
    text: str = ""
    truncated: bool = False


@dataclass
class FetchedPage:
    url: str
    final_url: str
    title: str
    text: str
    content_type: str = ""
    truncated: bool = False


def is_public_address(ip: ipaddress._BaseAddress) -> bool:
    """True only for addresses that are routable on the public internet."""
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    if ip.version == 4 and ip in CGNAT_NETWORK:
        return False
    return True


def check_scheme_and_host(url: str) -> tuple[str, str, int]:
    """Validate the scheme/host of a URL and return (scheme, host, port)."""
    parsed = urlparse((url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise PageFetchError("Only http:// and https:// URLs can be translated.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise PageFetchError("That URL has no host.")
    if host in BLOCKED_HOSTS or any(host.endswith(sfx) for sfx in BLOCKED_HOST_SUFFIXES):
        raise PageFetchError("That host cannot be translated as a public web page.")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:  # malformed port
        raise PageFetchError("That URL has an invalid port.") from exc
    return scheme, host, port


async def resolve_public_addresses(host: str, port: int) -> list[str]:
    """Resolve a host and refuse it unless every address is public."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise PageFetchError(f"Could not resolve {host}.") from exc
    addresses: list[str] = []
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as exc:
            raise PageFetchError(f"Could not resolve {host} to a usable address.") from exc
        if not is_public_address(ip):
            raise PageFetchError(
                "That address is private, loopback or link-local — refusing to fetch it."
            )
        addresses.append(str(ip))
    if not addresses:
        raise PageFetchError(f"Could not resolve {host}.")
    return addresses


# --------------------------------------------------------------------------- #
# Text extraction (standard library only)
# --------------------------------------------------------------------------- #
_SKIP_TAGS = {
    "script", "style", "noscript", "template", "svg", "head", "iframe",
    "object", "embed", "canvas", "nav", "footer", "aside", "form", "select",
    "button", "svg",
}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3",
    "h4", "h5", "h6", "tr", "td", "th", "blockquote", "pre", "br", "hr",
    "table", "header", "main", "figcaption", "dd", "dt",
}


class _ReadableTextParser(HTMLParser):
    """Collects the readable text of a document and its title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - stdlib signature
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        if data.strip():
            self.chunks.append(data)


def extract_readable_text(html: str) -> PageContent:
    """Extract the readable text and the title of an HTML document."""
    parser = _ReadableTextParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # malformed markup must not fail the whole request
        log.debug("html parsing stopped early", exc_info=True)
    lines: list[str] = []
    for raw in "".join(parser.chunks).splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) >= 2:
            lines.append(line)
    text = "\n".join(lines)
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
    return PageContent(
        title=re.sub(r"\s+", " ", parser.title).strip(),
        text=text,
        truncated=truncated,
    )


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def _charset_of(content_type: str) -> str:
    ctype = (content_type or "").lower()
    if "charset=" in ctype:
        return ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    return "utf-8"


async def fetch_page(url: str, *, client: httpx.AsyncClient | None = None) -> FetchedPage:
    """Fetch a public web page and return its readable text.

    Raises :class:`PageFetchError` for anything that is not a safe, readable
    public document.
    """
    current = (url or "").strip()
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(TIMEOUT_S),
            headers={"user-agent": USER_AGENT},
        )
    try:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port = check_scheme_and_host(current)
            await resolve_public_addresses(host, port)
            async with client.stream("GET", current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise PageFetchError("The page redirected without a target.")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise PageFetchError(
                        f"The page returned HTTP {response.status_code}."
                    )
                content_type = response.headers.get("content-type", "")
                media_type = content_type.split(";")[0].strip().lower()
                if media_type and media_type not in ALLOWED_MEDIA_TYPES:
                    raise PageFetchError(
                        f"That URL is not a web page (content type: {media_type})."
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise PageFetchError("The page is too large to translate.")
                html = bytes(body).decode(_charset_of(content_type), errors="replace")
                content = extract_readable_text(html)
                if not content.text:
                    raise PageFetchError("No readable text was found on that page.")
                return FetchedPage(
                    url=(url or "").strip(),
                    final_url=str(response.url),
                    title=content.title,
                    text=content.text,
                    content_type=media_type,
                    truncated=content.truncated,
                )
        raise PageFetchError("The page redirected too many times.")
    except httpx.HTTPError as exc:
        raise PageFetchError(f"Could not fetch the page: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
