"""
Binance Futures Testnet REST client.

Wraps the raw HTTP layer with:
  - HMAC-SHA256 request signing
  - Automatic timestamp injection
  - Structured logging of every request / response / error
  - Retries with exponential back-off on transient network failures
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .logging_config import get_logger

logger = get_logger("client")

# ── Constants ────────────────────────────────────────────────────────────────
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
DEFAULT_TIMEOUT = 10  # seconds
RECV_WINDOW = 5000   # ms


class BinanceAPIError(Exception):
    """Raised when Binance returns a non-2xx status or an error payload."""

    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[HTTP {status_code}] Binance error {code}: {message}")


class BinanceClient:
    """
    Thin, synchronous wrapper around the Binance Futures Testnet REST API.

    Parameters
    ----------
    api_key:    Your Binance Futures Testnet API key.
    api_secret: Your Binance Futures Testnet API secret.
    base_url:   Override if you need a different environment.
    timeout:    HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = TESTNET_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Both api_key and api_secret must be provided.")

        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = self._build_session()

        logger.info("BinanceClient initialised | base_url=%s", self._base_url)

    # ── Session / retry ──────────────────────────────────────────────────────

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ── Signing helpers ──────────────────────────────────────────────────────

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add timestamp + recvWindow, then append HMAC-SHA256 signature."""
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    @property
    def _auth_headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self._api_key}

    # ── Low-level HTTP ───────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request against the Binance API.

        Raises
        ------
        BinanceAPIError  – non-2xx or Binance error body
        requests.exceptions.RequestException – network / timeout
        """
        url = f"{self._base_url}{endpoint}"
        params = params or {}

        if signed:
            params = self._sign(params)

        # Sanitise params for logging (hide signature)
        safe_params = {k: v for k, v in params.items() if k != "signature"}
        logger.info("REQUEST  | %s %s | params=%s", method.upper(), endpoint, safe_params)

        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params if method.upper() == "GET" else None,
                data=params if method.upper() == "POST" else None,
                headers=self._auth_headers,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.error("TIMEOUT  | %s %s | %s", method.upper(), endpoint, exc)
            raise
        except requests.exceptions.ConnectionError as exc:
            logger.error("CONN_ERR | %s %s | %s", method.upper(), endpoint, exc)
            raise
        except requests.exceptions.RequestException as exc:
            logger.error("NET_ERR  | %s %s | %s", method.upper(), endpoint, exc)
            raise

        logger.info(
            "RESPONSE | %s %s | HTTP %s | body=%s",
            method.upper(),
            endpoint,
            response.status_code,
            response.text[:500],   # truncate huge responses
        )

        # Parse JSON
        try:
            data = response.json()
        except ValueError:
            logger.error("JSON parse failed | body=%s", response.text[:200])
            response.raise_for_status()
            return {}

        # Binance error body even on HTTP 200
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            logger.error(
                "API_ERR  | code=%s | msg=%s", data.get("code"), data.get("msg")
            )
            raise BinanceAPIError(
                status_code=response.status_code,
                code=data["code"],
                message=data.get("msg", "Unknown error"),
            )

        if not response.ok:
            msg = data.get("msg", response.text) if isinstance(data, dict) else response.text
            raise BinanceAPIError(
                status_code=response.status_code,
                code=data.get("code", -1) if isinstance(data, dict) else -1,
                message=msg,
            )

        return data

    # ── Public API methods ───────────────────────────────────────────────────

    def get_server_time(self) -> int:
        """Return Binance server timestamp in milliseconds."""
        data = self._request("GET", "/fapi/v1/time", signed=False)
        return data["serverTime"]

    def get_exchange_info(self) -> Dict[str, Any]:
        """Return exchange info (symbols, filters, etc.)."""
        return self._request("GET", "/fapi/v1/exchangeInfo", signed=False)

    def get_account(self) -> Dict[str, Any]:
        """Return futures account information."""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def new_order(self, **params: Any) -> Dict[str, Any]:
        """
        Place a new futures order.

        Expected keyword arguments mirror the Binance API:
          symbol, side, type, quantity, price (LIMIT only),
          timeInForce (LIMIT only), stopPrice (STOP_MARKET only),
          positionSide, reduceOnly, etc.
        """
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def get_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Query a specific order by orderId."""
        return self._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )

    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an open order."""
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )
