"""APEX / BENVIN Phase 2.35 - Real Deriv Account Connectivity.

Read-only connectivity foundation for a real Deriv Options account.

This module can obtain a short-lived authenticated WebSocket URL and verify
that the connection is scoped to the real endpoint by requesting account
balance. It deliberately does not place, modify, or close trades.

Credential values are accepted only at runtime and are never returned by
public result objects or summaries.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

try:
    import websocket
except ImportError:  # pragma: no cover - exercised only on missing dependency
    websocket = None


REAL_REST_BASE = "https://api.derivws.com"
REAL_WS_PREFIX = "wss://api.derivws.com/trading/v1/options/ws/real"
REAL_WS_PATH = "/trading/v1/options/ws/real"
OTP_PATH_TEMPLATE = "/trading/v1/options/accounts/{account_id}/otp"


class DerivLiveAccountError(ValueError):
    """Raised for invalid configuration or live connectivity failures."""


@dataclass(frozen=True)
class DerivLiveAccountConfig:
    """Runtime configuration for read-only real-account connectivity."""

    account_id: str
    app_id: str
    authorization_token: str
    rest_base_url: str = REAL_REST_BASE
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        for name in ("account_id", "app_id", "authorization_token"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DerivLiveAccountError(f"{name} must be a non-empty string")
        if not isinstance(self.rest_base_url, str) or not self.rest_base_url.strip():
            raise DerivLiveAccountError("rest_base_url must be a non-empty string")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool):
            raise DerivLiveAccountError("timeout_seconds must be numeric")
        if self.timeout_seconds <= 0:
            raise DerivLiveAccountError("timeout_seconds must be greater than zero")
        parsed = urlparse(self.rest_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise DerivLiveAccountError("rest_base_url must use HTTPS")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "DerivLiveAccountConfig":
        env = os.environ if environ is None else environ
        return cls(
            account_id=env.get("DERIV_REAL_ACCOUNT_ID", ""),
            app_id=env.get("DERIV_APP_ID", ""),
            authorization_token=env.get("DERIV_PAT", ""),
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "account_id_configured": bool(self.account_id.strip()),
            "app_id_configured": bool(self.app_id.strip()),
            "authorization_token_configured": bool(self.authorization_token.strip()),
            "rest_base_url": self.rest_base_url,
            "timeout_seconds": self.timeout_seconds,
            "credentials_exposed": False,
        }


@dataclass(frozen=True)
class DerivLiveConnectivityResult:
    """Verified real-account connectivity facts without secrets."""

    connected: bool
    real_endpoint_verified: bool
    authenticated: bool
    balance_verified: bool
    account_id: str | None
    currency: str | None
    message: str
    network_access_performed: bool
    trading_performed: bool = False
    live_execution: bool = False
    credentials_exposed: bool = False

    @property
    def ready_for_read_only(self) -> bool:
        return self.connected and self.real_endpoint_verified and self.authenticated and self.balance_verified

    @property
    def trading_authorized(self) -> bool:
        return False

    def safe_summary(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "real_endpoint_verified": self.real_endpoint_verified,
            "authenticated": self.authenticated,
            "balance_verified": self.balance_verified,
            "account_id": self.account_id,
            "currency": self.currency,
            "message": self.message,
            "network_access_performed": self.network_access_performed,
            "trading_performed": False,
            "live_execution": False,
            "trading_authorized": False,
            "credentials_exposed": False,
        }


class RestTransport(Protocol):
    def post_json(self, url: str, headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]: ...


class WebSocketTransport(Protocol):
    def request_balance(self, websocket_url: str, timeout: float) -> Mapping[str, Any]: ...


class UrllibRestTransport:
    def post_json(self, url: str, headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
        request = urllib.request.Request(url, method="POST", headers=dict(headers), data=b"")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DerivLiveAccountError(f"Deriv OTP request failed with HTTP {exc.code}: {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise DerivLiveAccountError(f"Deriv OTP request failed: {exc.reason}") from exc
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DerivLiveAccountError("Deriv OTP response was not valid JSON") from exc
        if not isinstance(result, Mapping):
            raise DerivLiveAccountError("Deriv OTP response was not an object")
        return result


class WebSocketClientTransport:
    def request_balance(self, websocket_url: str, timeout: float) -> Mapping[str, Any]:
        if websocket is None:
            raise DerivLiveAccountError("websocket-client is required for real-account connectivity")
        if not websocket_url.startswith(REAL_WS_PREFIX + "?"):
            raise DerivLiveAccountError("authenticated WebSocket URL is not scoped to the real endpoint")
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(json.dumps({"balance": 1, "req_id": 1}))
            raw = ws.recv()
            if not isinstance(raw, str):
                raise DerivLiveAccountError("Deriv WebSocket returned a non-text response")
            result = json.loads(raw)
            if not isinstance(result, Mapping):
                raise DerivLiveAccountError("Deriv WebSocket response was not an object")
            return result
        except DerivLiveAccountError:
            raise
        except Exception as exc:
            raise DerivLiveAccountError(f"Deriv real WebSocket request failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


class DerivLiveAccountConnectivity:
    """Obtain and verify a real authenticated session without trading."""

    def __init__(
        self,
        *,
        rest_transport: RestTransport | None = None,
        websocket_transport: WebSocketTransport | None = None,
    ) -> None:
        self._rest = rest_transport or UrllibRestTransport()
        self._websocket = websocket_transport or WebSocketClientTransport()

    @staticmethod
    def _extract_url(response: Mapping[str, Any]) -> str:
        data = response.get("data")
        if not isinstance(data, Mapping):
            raise DerivLiveAccountError("Deriv OTP response is missing data")
        url = data.get("url")
        if not isinstance(url, str) or not url.strip():
            raise DerivLiveAccountError("Deriv OTP response is missing WebSocket URL")
        return url

    @staticmethod
    def _verify_real_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "wss"
            and parsed.netloc == "api.derivws.com"
            and parsed.path == REAL_WS_PATH
            and bool(parsed.query)
        )

    def get_authenticated_websocket_url(self, config: DerivLiveAccountConfig) -> str:
        if not isinstance(config, DerivLiveAccountConfig):
            raise DerivLiveAccountError("config must be a DerivLiveAccountConfig")
        url = f"{config.rest_base_url.rstrip('/')}{OTP_PATH_TEMPLATE.format(account_id=config.account_id)}"
        headers = {
            "Authorization": f"Bearer {config.authorization_token}",
            "Deriv-App-ID": config.app_id,
            "Content-Type": "application/json",
        }
        response = self._rest.post_json(url, headers, config.timeout_seconds)
        ws_url = self._extract_url(response)
        if not self._verify_real_url(ws_url):
            raise DerivLiveAccountError("Deriv returned a WebSocket URL that is not scoped to the real endpoint")
        return ws_url

    def verify_read_only(self, config: DerivLiveAccountConfig) -> DerivLiveConnectivityResult:
        try:
            ws_url = self.get_authenticated_websocket_url(config)
            response = self._websocket.request_balance(ws_url, config.timeout_seconds)
            if response.get("msg_type") == "error" or "error" in response:
                return DerivLiveConnectivityResult(
                    connected=False,
                    real_endpoint_verified=True,
                    authenticated=False,
                    balance_verified=False,
                    account_id=config.account_id,
                    currency=None,
                    message="Deriv rejected the authenticated real-account request",
                    network_access_performed=True,
                )
            if response.get("msg_type") != "balance":
                return DerivLiveConnectivityResult(
                    connected=True,
                    real_endpoint_verified=True,
                    authenticated=False,
                    balance_verified=False,
                    account_id=config.account_id,
                    currency=None,
                    message="Real WebSocket connected, but response was not a balance response",
                    network_access_performed=True,
                )
            balance = response.get("balance")
            if not isinstance(balance, Mapping):
                return DerivLiveConnectivityResult(
                    connected=True,
                    real_endpoint_verified=True,
                    authenticated=False,
                    balance_verified=False,
                    account_id=config.account_id,
                    currency=None,
                    message="Real WebSocket connected, but no valid balance object was returned",
                    network_access_performed=True,
                )
            amount = balance.get("balance")
            currency = balance.get("currency")
            login_id = balance.get("loginid")
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or amount < 0
                or not isinstance(currency, str)
                or not currency.strip()
                or not isinstance(login_id, str)
                or not login_id.strip()
                or login_id.strip() != config.account_id.strip()
            ):
                return DerivLiveConnectivityResult(
                    connected=True,
                    real_endpoint_verified=True,
                    authenticated=False,
                    balance_verified=False,
                    account_id=config.account_id,
                    currency=currency.strip() if isinstance(currency, str) and currency.strip() else None,
                    message="Real WebSocket returned an invalid or mismatched balance identity",
                    network_access_performed=True,
                )
            return DerivLiveConnectivityResult(
                connected=True,
                real_endpoint_verified=True,
                authenticated=True,
                balance_verified=True,
                account_id=config.account_id,
                currency=currency.strip(),
                message="Real Deriv account authenticated and read-only balance verified",
                network_access_performed=True,
            )
        except DerivLiveAccountError as exc:
            return DerivLiveConnectivityResult(
                connected=False,
                real_endpoint_verified=False,
                authenticated=False,
                balance_verified=False,
                account_id=config.account_id,
                currency=None,
                message=str(exc),
                network_access_performed=True,
            )

    def connect_from_environment(self, environ: Mapping[str, str] | None = None) -> DerivLiveConnectivityResult:
        config = DerivLiveAccountConfig.from_environment(environ)
        return self.verify_read_only(config)
