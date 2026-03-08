#!/usr/bin/env python3
"""
cli.py — Command-line interface for the Binance Futures Testnet trading bot.

Usage examples
--------------
# Market BUY
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

# Limit SELL
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 100000

# Stop-Market BUY (bonus order type)
python cli.py --symbol BTCUSDT --side BUY --type STOP_MARKET --quantity 0.001 --stop-price 95000

# Override credentials inline (or set env vars)
python cli.py --api-key YOUR_KEY --api-secret YOUR_SECRET --symbol ETHUSDT --side BUY --type MARKET --quantity 0.01
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap

import requests

from bot import (
    BinanceClient,
    BinanceAPIError,
    place_order,
    validate_all,
    setup_logging,
    get_logger,
)

# ── Logging bootstrap ─────────────────────────────────────────────────────────
setup_logging("DEBUG")
logger = get_logger("cli")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_request_summary(args: argparse.Namespace) -> None:
    """Print a formatted summary of what is about to be sent."""
    print()
    print("=" * 52)
    print("  ORDER REQUEST SUMMARY")
    print("=" * 52)
    print(f"  Symbol     : {args.symbol.upper()}")
    print(f"  Side       : {args.side.upper()}")
    print(f"  Order Type : {args.type.upper()}")
    print(f"  Quantity   : {args.quantity}")
    if args.price:
        print(f"  Price      : {args.price}")
    if args.stop_price:
        print(f"  Stop Price : {args.stop_price}")
    if args.type.upper() == "LIMIT":
        print(f"  TIF        : {args.time_in_force}")
    print("=" * 52)
    print()


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """
    Resolve API key / secret from (in priority order):
      1. CLI flags  --api-key / --api-secret
      2. Environment variables  BINANCE_API_KEY / BINANCE_API_SECRET
    """
    api_key = args.api_key or os.environ.get("BINANCE_API_KEY", "")
    api_secret = args.api_secret or os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        print(
            "\n[ERROR] Binance API credentials are missing.\n"
            "  Set them via:\n"
            "    export BINANCE_API_KEY=<your_key>\n"
            "    export BINANCE_API_SECRET=<your_secret>\n"
            "  or pass --api-key / --api-secret flags.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key, api_secret


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Binance Futures Testnet — simple trading bot CLI
            ────────────────────────────────────────────────
            Place MARKET, LIMIT, or STOP_MARKET orders on the
            Binance USDT-M Futures Testnet.

            Credentials are read from environment variables by default:
              BINANCE_API_KEY
              BINANCE_API_SECRET
            """
        ),
        epilog=textwrap.dedent(
            """\
            Examples:
              python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
              python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 100000
              python cli.py --symbol BTCUSDT --side BUY --type STOP_MARKET --quantity 0.001 --stop-price 95000
            """
        ),
    )

    # Credentials (optional — fall back to env vars)
    cred = parser.add_argument_group("credentials (override env vars)")
    cred.add_argument("--api-key", default=None, help="Binance API key")
    cred.add_argument("--api-secret", default=None, help="Binance API secret")

    # Order parameters
    order = parser.add_argument_group("order parameters")
    order.add_argument(
        "--symbol", required=True,
        help="Trading pair (e.g. BTCUSDT)",
    )
    order.add_argument(
        "--side", required=True, choices=["BUY", "SELL", "buy", "sell"],
        help="Order side: BUY or SELL",
    )
    order.add_argument(
        "--type", required=True,
        choices=["MARKET", "LIMIT", "STOP_MARKET", "market", "limit", "stop_market"],
        metavar="ORDER_TYPE",
        help="Order type: MARKET | LIMIT | STOP_MARKET",
    )
    order.add_argument(
        "--quantity", required=True, type=float,
        help="Order quantity (base asset, e.g. 0.001 BTC)",
    )
    order.add_argument(
        "--price", default=None, type=float,
        help="Limit price (required for LIMIT orders)",
    )
    order.add_argument(
        "--stop-price", dest="stop_price", default=None, type=float,
        help="Stop trigger price (required for STOP_MARKET orders)",
    )
    order.add_argument(
        "--time-in-force", dest="time_in_force", default="GTC",
        choices=["GTC", "IOC", "FOK"],
        help="Time-in-force for LIMIT orders (default: GTC)",
    )

    # Misc
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and print the request but do NOT submit to Binance",
    )
    parser.add_argument(
        "--log-level", default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity for the log file (default: DEBUG)",
    )

    return parser


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logger.info("CLI invoked | args=%s", vars(args))

    # ── 1. Validate all inputs ────────────────────────────────────────────
    try:
        cleaned = validate_all(
            symbol=args.symbol,
            side=args.side,
            order_type=args.type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
        )
    except ValueError as exc:
        print(f"\n[VALIDATION ERROR] {exc}\n", file=sys.stderr)
        logger.error("Validation failed | %s", exc)
        sys.exit(2)

    # ── 2. Print request summary ──────────────────────────────────────────
    _print_request_summary(args)

    if args.dry_run:
        print("[DRY RUN] Order NOT submitted. Exiting.")
        logger.info("Dry-run mode — order skipped.")
        sys.exit(0)

    # ── 3. Resolve credentials ────────────────────────────────────────────
    api_key, api_secret = _resolve_credentials(args)

    # ── 4. Build client ───────────────────────────────────────────────────
    client = BinanceClient(api_key=api_key, api_secret=api_secret)

    # ── 5. Connectivity check ─────────────────────────────────────────────
    try:
        server_time = client.get_server_time()
        logger.info("Server time: %s ms", server_time)
    except Exception as exc:
        print(f"\n[ERROR] Cannot reach Binance Testnet: {exc}\n", file=sys.stderr)
        logger.error("Connectivity check failed | %s", exc)
        sys.exit(1)

    # ── 6. Place order ────────────────────────────────────────────────────
    try:
        result = place_order(
            client,
            symbol=cleaned["symbol"],
            side=cleaned["side"],
            order_type=cleaned["order_type"],
            quantity=cleaned["quantity"],
            price=cleaned.get("price"),
            stop_price=cleaned.get("stop_price"),
            time_in_force=args.time_in_force,
        )
    except BinanceAPIError as exc:
        print(f"\n[BINANCE API ERROR] {exc}\n", file=sys.stderr)
        logger.error("BinanceAPIError | %s", exc)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("\n[NETWORK ERROR] Request timed out. Check your connection.\n", file=sys.stderr)
        logger.error("Request timed out.")
        sys.exit(1)
    except requests.exceptions.ConnectionError as exc:
        print(f"\n[NETWORK ERROR] Connection failed: {exc}\n", file=sys.stderr)
        logger.error("Connection error | %s", exc)
        sys.exit(1)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}\n", file=sys.stderr)
        logger.error("Order dispatch error | %s", exc)
        sys.exit(2)

    # ── 7. Print response ─────────────────────────────────────────────────
    print("  ORDER RESPONSE")
    result.print_summary()

    if result.is_filled():
        print(f"✅  SUCCESS — Order FILLED | orderId={result.order_id}\n")
        logger.info("Order FILLED | orderId=%s", result.order_id)
    elif result.is_rejected():
        print(f"❌  FAILED  — Order {result.status} | orderId={result.order_id}\n")
        logger.warning("Order %s | orderId=%s", result.status, result.order_id)
    else:
        print(f"📋  Order {result.status} | orderId={result.order_id}\n")
        logger.info("Order %s | orderId=%s", result.status, result.order_id)


if __name__ == "__main__":
    main()
