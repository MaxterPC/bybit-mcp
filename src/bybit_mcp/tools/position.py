from typing import Any

from bybit_mcp.config import private_session
from bybit_mcp.utils.formatters import format_response


def _require_auth() -> None:
    if private_session is None:
        raise RuntimeError("Bybit API credentials not configured. Set BYBIT_API_KEY and BYBIT_API_SECRET.")


def get_positions(
    category: str,
    symbol: str | None = None,
    settle_coin: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get current open positions with real-time PnL and margin data.

    Args:
        category: Product type - linear, inverse, option
        symbol: Trading pair filter (optional)
        settle_coin: Settlement coin filter e.g. USDT, USDC
        limit: Results per page 1-200 (default: 20)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "limit": limit}
    if symbol:
        params["symbol"] = symbol
    if settle_coin:
        params["settleCoin"] = settle_coin
    return format_response(private_session.get_positions(**params))


def set_leverage(
    category: str,
    symbol: str,
    buy_leverage: str,
    sell_leverage: str,
) -> dict[str, Any]:
    """Set leverage for a trading pair.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        buy_leverage: Buy side leverage e.g. "10"
        sell_leverage: Sell side leverage e.g. "10"
    """
    _require_auth()
    return format_response(
        private_session.set_leverage(
            category=category,
            symbol=symbol,
            buyLeverage=buy_leverage,
            sellLeverage=sell_leverage,
        )
    )


def set_trading_stop(
    category: str,
    symbol: str,
    take_profit: str | None = None,
    stop_loss: str | None = None,
    tp_trigger_by: str | None = None,
    sl_trigger_by: str | None = None,
    tpsl_mode: str = "Full",
    tp_order_type: str | None = None,
    sl_order_type: str | None = None,
    tp_limit_price: str | None = None,
    sl_limit_price: str | None = None,
    position_idx: int = 0,
) -> dict[str, Any]:
    """Set take profit and/or stop loss for a position.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        take_profit: TP price (set to "0" to cancel)
        stop_loss: SL price (set to "0" to cancel)
        tp_trigger_by: TP trigger price type - LastPrice, IndexPrice, MarkPrice
        sl_trigger_by: SL trigger price type - LastPrice, IndexPrice, MarkPrice
        tpsl_mode: Full (entire position) or Partial
        tp_order_type: Market or Limit
        sl_order_type: Market or Limit
        tp_limit_price: Limit price for TP order
        sl_limit_price: Limit price for SL order
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
    """
    _require_auth()
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "tpslMode": tpsl_mode,
        "positionIdx": position_idx,
    }
    if take_profit is not None:
        params["takeProfit"] = take_profit
    if stop_loss is not None:
        params["stopLoss"] = stop_loss
    if tp_trigger_by:
        params["tpTriggerBy"] = tp_trigger_by
    if sl_trigger_by:
        params["slTriggerBy"] = sl_trigger_by
    if tp_order_type:
        params["tpOrderType"] = tp_order_type
    if sl_order_type:
        params["slOrderType"] = sl_order_type
    if tp_limit_price:
        params["tpLimitPrice"] = tp_limit_price
    if sl_limit_price:
        params["slLimitPrice"] = sl_limit_price
    return format_response(private_session.set_trading_stop(**params))


def switch_position_mode(
    category: str,
    mode: int,
    symbol: str | None = None,
    coin: str | None = None,
) -> dict[str, Any]:
    """Switch between one-way and hedge position mode.

    Args:
        category: Product type - linear or inverse
        mode: 0=Merged (one-way), 3=Both Sides (hedge mode)
        symbol: Trading pair (required for linear)
        coin: Coin (required for inverse)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "mode": mode}
    if symbol:
        params["symbol"] = symbol
    if coin:
        params["coin"] = coin
    return format_response(private_session.switch_position_mode(**params))


def set_auto_add_margin(
    category: str,
    symbol: str,
    auto_add_margin: int,
    position_idx: int = 0,
) -> dict[str, Any]:
    """Enable or disable auto-add margin for isolated margin positions.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        auto_add_margin: 0=disable, 1=enable
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
    """
    _require_auth()
    return format_response(
        private_session.set_auto_add_margin(
            category=category,
            symbol=symbol,
            autoAddMargin=auto_add_margin,
            positionIdx=position_idx,
        )
    )


def get_closed_pnl(
    category: str,
    symbol: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get closed position profit and loss history.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair filter (optional)
        limit: Results per page 1-100 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "limit": limit}
    if symbol:
        params["symbol"] = symbol
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(private_session.get_closed_pnl(**params))
