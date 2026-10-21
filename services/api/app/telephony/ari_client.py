"""Asterisk ARI REST client (backend-only).

Per docs/ASTERISK_LOCAL_SIP_LAB.md (P1 design): ARI is the proposed control
plane for the Asterisk provider. Credentials stay server-side; the browser
never connects to ARI directly. Transport failures are deliberately typed so
the provider can honor the P2 provider-selection contract:

- an unreachable ARI server is an honest ``provider unavailable`` outcome;
- a *timeout after originate* is an **unknown outcome** (the request may have
  taken effect server-side) and must be reconciled by correlation ID instead
  of blindly retried (which could duplicate a real local call);
- a 404 means the resource does not exist (never fabricate success).

None of the paths here disables TLS / auth posture inspection implicitly; ARI
HTTP credentials are passed as standard Basic auth on the REST surface.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("app.telephony.ari")

# Client-chosen ARI channel IDs are namespaced with this prefix so a channel
# observed over the WebSocket can always be attributed to TalkFlow strictly by
# string shape (no ARI round-trip needed), including across API restarts.
CHANNEL_ID_PREFIX = "talkflow-"


class ARIError(Exception):
    """Base class for ARI transport / API failures."""


class ARIUnavailable(ARIError):
    """ARI could not be reached at all (connect failure or 5xx)."""


class ARITimeout(ARIError):
    """The request timed out; its server-side outcome is unknown."""


class ARINotFound(ARIError):
    """404: the requested ARI resource does not exist."""


class ARIRequestFailed(ARIError):
    """Other ARI API rejection (400/401/409/...)."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ARIConfig:
    """Explicit ARI connection settings (no global settings import: DI-friendly)."""

    base_url: str = ""
    username: str = ""
    password: str = ""
    app_name: str = "talkflow"
    timeout_seconds: float = 10.0

    @classmethod
    def from_settings(cls) -> "ARIConfig":
        from app.config import settings

        return cls(
            base_url=settings.asterisk_ari_base_url.rstrip("/"),
            username=settings.asterisk_ari_username,
            password=settings.asterisk_ari_password,
            app_name=settings.asterisk_ari_app_name,
            timeout_seconds=settings.asterisk_request_timeout_seconds,
        )

    def is_configured(self) -> bool:
        return bool(
            self.base_url and self.username and self.password and self.app_name
        )


class ARIClient:
    """Thin async REST wrapper over the ARI surface used by the adapter."""

    def __init__(self, config: ARIConfig) -> None:
        self._config = config
        self._auth = (config.username, config.password)

    @property
    def config(self) -> ARIConfig:
        return self._config

    # ------------------------------------------------------------------ #
    # plumbing
    # ------------------------------------------------------------------ #
    def _url(self, path: str) -> str:
        return f"{self._config.base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                return await client.request(
                    method,
                    self._url(path),
                    params=params,
                    auth=self._auth,
                )
        except httpx.TimeoutException as exc:
            raise ARITimeout(f"ARI request timed out: {method} {path}") from exc
        except httpx.ConnectError as exc:
            raise ARIUnavailable(f"ARI server unreachable ({method} {path})") from exc
        except httpx.TransportError as exc:
            raise ARIUnavailable(f"ARI transport error ({method} {path}): {exc}") from exc

    async def _json_ok(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code == 404:
            raise ARINotFound(f"ARI resource not found: {resp.request.url}")
        if resp.status_code >= 500:
            raise ARIUnavailable(f"ARI server error {resp.status_code}")
        if resp.status_code >= 400:
            try:
                message = resp.json().get("message", resp.text)
            except Exception:
                message = resp.text
            raise ARIRequestFailed(
                f"ARI request rejected ({resp.status_code}): {message}",
                resp.status_code,
            )
        try:
            data = resp.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def request_json(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._json_ok(await self._request(method, path, params))

    # ------------------------------------------------------------------ #
    # adapter surface
    # ------------------------------------------------------------------ #
    async def health(self) -> dict[str, Any]:
        """GET /ari/asterisk/info — bounded PBX health probe."""
        return await self.request_json("GET", "/ari/asterisk/info")

    async def create_channel(
        self,
        *,
        channel_id: str,
        endpoint: str,
        app: str,
        app_args: list[str],
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST /ari/channels — place the channel into the Stasis app.

        ``channel_id`` is client-chosen so TalkFlow's correlation UUID becomes
        the provider reference (``CallSession.call_sid``), making originate
        reconciliation deterministic after a timeout.
        """
        params: dict[str, Any] = {
            "endpoint": endpoint,
            "app": app,
            "appArgs": ",".join(app_args) if app_args else "",
            "channelId": channel_id,
        }
        if variables:
            params["variables"] = json.dumps({k: str(v) for k, v in variables.items()})
        return await self.request_json("POST", "/ari/channels", params=params)

    async def dial(self, channel_id: str) -> None:
        """POST /ari/channels/{id}/dial — start dialing the created channel."""
        await self.request_json("POST", f"/ari/channels/{channel_id}/dial")

    async def answer(self, channel_id: str) -> None:
        """POST /ari/channels/{id}/answer — answer an inbound Stasis leg."""
        await self.request_json("POST", f"/ari/channels/{channel_id}/answer")

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        """GET /ari/channels/{id} — raises ARINotFound when the channel is gone."""
        return await self.request_json("GET", f"/ari/channels/{channel_id}")

    async def get_channel_variable(self, channel_id: str, variable: str) -> str | None:
        try:
            data = await self.request_json(
                "GET", f"/ari/channels/{channel_id}/variable", params={"variable": variable}
            )
        except ARIRequestFailed:
            return None
        value = data.get("value")
        return str(value) if value else None

    async def hangup(self, channel_id: str) -> None:
        """DELETE /ari/channels/{id} — terminate a channel (idempotent-ish)."""
        await self.request_json("DELETE", f"/ari/channels/{channel_id}")

    # ------------------------------------------------------------------ #
    # externalMedia + bridging surface (P3 media spike)
    # ------------------------------------------------------------------ #

    async def external_media(self, *, params: dict[str, Any]) -> dict[str, Any]:
        """POST /ari/channels/externalMedia (websocket transport, see media pkg)."""
        return await self.request_json(
            "POST", "/ari/channels/externalMedia", params=params
        )

    async def list_channels(self) -> list[dict[str, Any]]:
        """GET /ari/channels — raw listing (residual audits)."""
        resp = await self._request("GET", "/ari/channels")
        if resp.status_code == 404:
            raise ARINotFound("ARI resource not found: /ari/channels")
        if resp.status_code >= 400:
            raise ARIRequestFailed(
                f"ARI request rejected ({resp.status_code})", resp.status_code
            )
        try:
            data = resp.json()
        except Exception:
            return []
        return data if isinstance(data, list) else []

    async def create_bridge(
        self, *, bridge_id: str, type: str = "mixing", name: str = ""
    ) -> dict[str, Any]:
        """POST /ari/bridges with a client-chosen bridge ID."""
        params: dict[str, Any] = {"type": type, "bridgeId": bridge_id}
        if name:
            params["name"] = name
        return await self.request_json("POST", "/ari/bridges", params=params)

    async def get_bridge(self, bridge_id: str) -> dict[str, Any]:
        """GET /ari/bridges/{id} — raises ARINotFound when it no longer exists."""
        return await self.request_json("GET", f"/ari/bridges/{bridge_id}")

    async def delete_bridge(self, bridge_id: str) -> None:
        """DELETE /ari/bridges/{id} (404 absorbed by caller policy)."""
        await self.request_json("DELETE", f"/ari/bridges/{bridge_id}")

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        """POST /ari/bridges/{id}/addChannel."""
        await self.request_json(
            "POST", f"/ari/bridges/{bridge_id}/addChannel", params={"channel": channel_id}
        )
