"""
Order placement logic for Binance Futures Testnet.

This module sits between the CLI layer and the raw BinanceClient.
It handles parameter construction, response normalisation, and
pretty-printing of order summaries.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from .client import BinanceClient, BinanceAPIError
from .logging_config import get_logger

logger = get_logger("orders")


# ── Response model ────────────────────────────────────────────────────────────

class OrderResult:
    """Normalised view of a Binance order response."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw
        self.order_id: int = raw.get("orderId", 0)
        self.symbol: str = raw.get("symbol", "")
        self.status: str = raw.get("status", "")
        self.side: str = raw.get("side", "")
        self.order_type: str = raw.get("type", "")
        self.price: str = raw.get("price", "0")
        self.avg_price: str = raw.get("avgPrice", "0")
        self.orig_qty: str = raw.get("origQty", "0")
        self.executed_qty: str = raw.get("executedQty", "0")
        self.time_in_force: str = raw.get("timeInForce", "")
        self.client_order_id: str = raw.get("clientOrderId", "")

    def is_filled(self) -> bool:
        return self.status == "FILLED"

    def is_rejected(self) -> bool:
        return self.status in ("REJECTED", "EXPIRED", "CANCELED")

    def summary_lines(self) -> list[str]:
        lines = [
            "─" * 50,
            f"  Order ID       : {self.order_id}",
            f"  Client OID     : {self.client_order_id}",
            f"  Symbol         : {self.symbol}",
            f"  Side           : {self.side}",
            f"  Type           : {self.order_type}",
            f"  Status         : {self.status}",
            f"  Orig Qty       : {self.orig_qty}",
            f"  Executed Qty   : {self.executed_qty}",
            f"  Order Price    : {self.price}",
            f"  Avg Fill Price : {self.avg_price}",
        ]
        if self.time_in_force:
            lines.append(f"  Time In Force  : {self.time_in_force}")
        lines.append("─" * 50)
        return lines

    def print_summary(self) -> None:
        for line in self.summary_lines():
            print(line)


# ── Order placement functions ─────────────────────────────────────────────────

def place_market_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
) -> OrderResult:
    """
    Place a MARKET order on Binance Futures.

    Parameters
    ----------
    client   : Authenticated BinanceClient instance.
    symbol   : Trading pair, e.g. 'BTCUSDT'.
    side     : 'BUY' or 'SELL'.
    quantity : Order quantity (base asset).
    """
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": str(quantity),
    }

    logger.info(
        "Placing MARKET order | symbol=%s | side=%s | qty=%s",
        symbol, side, quantity,
    )

    raw = client.new_order(**params)
    result = OrderResult(raw)

    logger.info(
        "MARKET order placed | orderId=%s | status=%s | executedQty=%s | avgPrice=%s",
        result.order_id, result.status, result.executed_qty, result.avg_price,
    )
    return result


def place_limit_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    time_in_force: str = "GTC",
) -> OrderResult:
    """
    Place a LIMIT order on Binance Futures.

    Parameters
    ----------
    client        : Authenticated BinanceClient instance.
    symbol        : Trading pair, e.g. 'BTCUSDT'.
    side          : 'BUY' or 'SELL'.
    quantity      : Order quantity (base asset).
    price         : Limit price.
    time_in_force : 'GTC' (default), 'IOC', or 'FOK'.
    """
    params = {
        "symbol": symbol,
        "side": side,
        "type": "LIMIT",
        "quantity": str(quantity),
        "price": str(price),
        "timeInForce": time_in_force,
    }

    logger.info(
        "Placing LIMIT order | symbol=%s | side=%s | qty=%s | price=%s | tif=%s",
        symbol, side, quantity, price, time_in_force,
    )

    raw = client.new_order(**params)
    result = OrderResult(raw)

    logger.info(
        "LIMIT order placed | orderId=%s | status=%s | executedQty=%s",
        result.order_id, result.status, result.executed_qty,
    )
    return result


def place_stop_market_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    stop_price: Decimal,
) -> OrderResult:
    """
    Place a STOP_MARKET order on Binance Futures (bonus order type).

    Parameters
    ----------
    client     : Authenticated BinanceClient instance.
    symbol     : Trading pair, e.g. 'BTCUSDT'.
    side       : 'BUY' or 'SELL'.
    quantity   : Order quantity (base asset).
    stop_price : Trigger price for the stop.
    """
    params = {
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "quantity": str(quantity),
        "stopPrice": str(stop_price),
    }

    logger.info(
        "Placing STOP_MARKET order | symbol=%s | side=%s | qty=%s | stopPrice=%s",
        symbol, side, quantity, stop_price,
    )

    raw = client.new_order(**params)
    result = OrderResult(raw)

    logger.info(
        "STOP_MARKET order placed | orderId=%s | status=%s",
        result.order_id, result.status,
    )
    return result


# ── Dispatcher ───────────────────────────────────────────────────────────────

def place_order(
    client: BinanceClient,
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    time_in_force: str = "GTC",
) -> OrderResult:
    """
    Unified entry point — dispatches to the correct order function.

    Raises
    ------
    ValueError       – unsupported order_type
    BinanceAPIError  – Binance rejected the order
    """
    ot = order_type.upper()

    if ot == "MARKET":
        return place_market_order(client, symbol, side, quantity)

    elif ot == "LIMIT":
        if price is None:
            raise ValueError("price is required for LIMIT orders.")
        return place_limit_order(client, symbol, side, quantity, price, time_in_force)

    elif ot == "STOP_MARKET":
        if stop_price is None:
            raise ValueError("stop_price is required for STOP_MARKET orders.")
        return place_stop_market_order(client, symbol, side, quantity, stop_price)

    else:
        raise ValueError(f"Unsupported order type: '{order_type}'. Use MARKET, LIMIT, or STOP_MARKET.")
