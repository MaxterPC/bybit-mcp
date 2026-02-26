from typing import Any

from bybit_mcp.config import public_session
from bybit_mcp.utils.formatters import format_response


def get_tickers(category: str, symbol: str | None = None) -> dict[str, Any]:
    """Get real-time ticker data (price, volume, funding rate, 24h change).

    Args:
        category: Product type - spot, linear, inverse, or option
        symbol: Trading pair e.g. BTCUSDT (required for option, optional otherwise)
    """
    params: dict[str, Any] = {"category": category}
    if symbol:
        params["symbol"] = symbol
    return format_response(public_session.get_tickers(**params))


def get_klines(
    symbol: str,
    interval: str,
    category: str = "linear",
    limit: int = 200,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    """Get candlestick/kline historical data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval: Candle interval - 1,3,5,15,30,60,120,240,360,720,D,W,M
        category: Product type - spot, linear, inverse (default: linear)
        limit: Results per page 1-1000 (default: 200)
        start: Start timestamp in milliseconds
        end: End timestamp in milliseconds
    """
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return format_response(public_session.get_kline(**params))


def get_orderbook(
    symbol: str,
    category: str = "linear",
    limit: int = 25,
) -> dict[str, Any]:
    """Get order book depth data (bids and asks).

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - spot, linear, inverse, option
        limit: Depth limit - spot:1-200, linear/inverse:1-500, option:1-25
    """
    return format_response(
        public_session.get_orderbook(category=category, symbol=symbol, limit=limit)
    )


def get_recent_trades(
    symbol: str,
    category: str = "linear",
    limit: int = 60,
) -> dict[str, Any]:
    """Get recent public trades for a symbol.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - spot, linear, inverse, option
        limit: Number of trades 1-1000 (default: 60)
    """
    return format_response(
        public_session.get_public_trade_history(
            category=category, symbol=symbol, limit=limit
        )
    )


def get_instruments(
    category: str,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Get instrument specifications (tick size, lot size, leverage, trading rules).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT (optional, returns all if omitted)
        status: Filter by status - Trading, Settling, Delivering, Closed
        limit: Results per page (default: 500)
    """
    params: dict[str, Any] = {"category": category, "limit": limit}
    if symbol:
        params["symbol"] = symbol
    if status:
        params["status"] = status
    return format_response(public_session.get_instruments_info(**params))


def get_funding_rate_history(
    symbol: str,
    category: str = "linear",
    limit: int = 200,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get historical funding rate data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - linear or inverse
        limit: Results per page 1-200 (default: 200)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "limit": limit,
    }
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(public_session.get_funding_rate_history(**params))


def get_mark_price_kline(
    symbol: str,
    interval: str,
    category: str = "linear",
    limit: int = 200,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    """Get mark price kline/candlestick data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval: Candle interval - 1,3,5,15,30,60,120,240,360,720,D,W,M
        category: Product type - linear or inverse
        limit: Results per page 1-1000 (default: 200)
        start: Start timestamp in milliseconds
        end: End timestamp in milliseconds
    """
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return format_response(public_session.get_mark_price_kline(**params))


def get_open_interest(
    symbol: str,
    interval_time: str,
    category: str = "linear",
    limit: int = 200,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get historical open interest data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval_time: Interval - 5min, 15min, 30min, 1h, 4h, 1d
        category: Product type - linear or inverse
        limit: Results per page 1-200 (default: 200)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "intervalTime": interval_time,
        "limit": limit,
    }
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(public_session.get_open_interest(**params))


def get_server_time() -> dict[str, Any]:
    """Get Bybit server time. Useful for checking connectivity and clock sync."""
    return format_response(public_session.get_server_time())
