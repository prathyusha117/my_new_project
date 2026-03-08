"""
Input validation for trading bot CLI arguments.
All validators raise ValueError with a human-readable message on failure.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}


def validate_symbol(symbol: str) -> str:
    """Ensure symbol is a non-empty uppercase string (e.g. BTCUSDT)."""
    s = symbol.strip().upper()
    if not s:
        raise ValueError("Symbol must not be empty.")
    if not s.isalnum():
        raise ValueError(f"Symbol '{s}' contains invalid characters. Use alphanumeric only (e.g. BTCUSDT).")
    return s


def validate_side(side: str) -> str:
    """Ensure side is BUY or SELL."""
    s = side.strip().upper()
    if s not in VALID_SIDES:
        raise ValueError(f"Side must be one of {sorted(VALID_SIDES)}, got '{side}'.")
    return s


def validate_order_type(order_type: str) -> str:
    """Ensure order_type is one of the supported types."""
    t = order_type.strip().upper()
    if t not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Order type must be one of {sorted(VALID_ORDER_TYPES)}, got '{order_type}'."
        )
    return t


def validate_quantity(quantity: str | float) -> Decimal:
    """Ensure quantity is a positive number."""
    try:
        q = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")
    if q <= 0:
        raise ValueError(f"Quantity must be greater than zero, got {q}.")
    return q


def validate_price(price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """
    Validate price field.
    - Required for LIMIT and STOP_MARKET orders.
    - Should be None / not provided for MARKET orders.
    """
    if order_type == "LIMIT":
        if price is None:
            raise ValueError(f"Price is required for {order_type} orders.")
        try:
            p = Decimal(str(price))
        except InvalidOperation:
            raise ValueError(f"Price '{price}' is not a valid number.")
        if p <= 0:
            raise ValueError(f"Price must be greater than zero, got {p}.")
        return p

    # MARKET order — price should be ignored
    if price is not None:
        # Warn but don't fail; just ignore
        return None
    return None


def validate_all(
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Run all validators and return a cleaned parameter dict.
    Raises ValueError on the first validation failure.
    """
    cleaned = {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "order_type": validate_order_type(order_type),
        "quantity": validate_quantity(quantity),
        "price": validate_price(price, order_type.strip().upper()),
    }

    # stop_price validation for STOP_MARKET
    if cleaned["order_type"] == "STOP_MARKET":
        if stop_price is None:
            raise ValueError("stop_price is required for STOP_MARKET orders.")
        try:
            sp = Decimal(str(stop_price))
        except InvalidOperation:
            raise ValueError(f"stop_price '{stop_price}' is not a valid number.")
        if sp <= 0:
            raise ValueError(f"stop_price must be greater than zero, got {sp}.")
        cleaned["stop_price"] = sp
    else:
        cleaned["stop_price"] = None

    return cleaned
