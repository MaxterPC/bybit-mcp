from typing import Any

from bybit_mcp.config import private_session
from bybit_mcp.utils.formatters import format_response


def _require_auth() -> None:
    if private_session is None:
        raise RuntimeError("Bybit API credentials not configured. Set BYBIT_API_KEY and BYBIT_API_SECRET.")


def get_wallet_balance(
    account_type: str = "UNIFIED",
    coin: str | None = None,
) -> dict[str, Any]:
    """Get wallet balance for the unified account.

    Args:
        account_type: Account type - UNIFIED (default) or CONTRACT
        coin: Specific coin e.g. USDT, BTC (optional, comma-separated for multiple)
    """
    _require_auth()
    params: dict[str, Any] = {"accountType": account_type}
    if coin:
        params["coin"] = coin
    return format_response(private_session.get_wallet_balance(**params))


def get_fee_rate(
    category: str,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Get trading fee rates.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter (optional)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category}
    if symbol:
        params["symbol"] = symbol
    return format_response(private_session.get_fee_rates(**params))


def get_account_info() -> dict[str, Any]:
    """Get account information (margin mode, account type, SMP group, etc.)."""
    _require_auth()
    return format_response(private_session.get_account_info())


def get_transaction_log(
    category: str | None = None,
    coin: str | None = None,
    type: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get transaction log (trades, funding, transfers, etc.).

    Args:
        category: Product type filter - spot, linear, inverse, option
        coin: Coin filter e.g. USDT
        type: Transaction type - TRANSFER_IN, TRANSFER_OUT, TRADE, FEE, etc.
        limit: Results per page 1-50 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    _require_auth()
    params: dict[str, Any] = {"limit": limit}
    if category:
        params["category"] = category
    if coin:
        params["coin"] = coin
    if type:
        params["type"] = type
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(private_session.get_transaction_log(**params))
