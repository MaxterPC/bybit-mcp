from typing import Any

from bybit_mcp.config import private_session
from bybit_mcp.utils.formatters import format_response


def _require_auth() -> None:
    if private_session is None:
        raise RuntimeError("Bybit API credentials not configured. Set BYBIT_API_KEY and BYBIT_API_SECRET.")


def place_order(
    category: str,
    symbol: str,
    side: str,
    order_type: str,
    qty: str,
    price: str | None = None,
    time_in_force: str | None = None,
    trigger_price: str | None = None,
    trigger_direction: int | None = None,
    take_profit: str | None = None,
    stop_loss: str | None = None,
    reduce_only: bool = False,
    position_idx: int = 0,
    order_link_id: str | None = None,
    tp_order_type: str | None = None,
    sl_order_type: str | None = None,
    tp_limit_price: str | None = None,
    sl_limit_price: str | None = None,
    is_leverage: int | None = None,
) -> dict[str, Any]:
    """Place a new order (market, limit, or conditional).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT
        side: Buy or Sell
        order_type: Market or Limit
        qty: Order quantity as string
        price: Limit price (required for Limit orders)
        time_in_force: GTC, IOC, FOK, or PostOnly
        trigger_price: Trigger price for conditional orders
        trigger_direction: 1=price rises to trigger, 2=price falls to trigger
        take_profit: Take profit price
        stop_loss: Stop loss price
        reduce_only: If true, only reduces position
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
        order_link_id: Custom order ID (max 36 chars, must be unique)
        tp_order_type: TP order type - Market or Limit
        sl_order_type: SL order type - Market or Limit
        tp_limit_price: Limit price for TP (when tp_order_type=Limit)
        sl_limit_price: Limit price for SL (when sl_order_type=Limit)
        is_leverage: 0=spot, 1=margin trading (spot category only)
    """
    _require_auth()
    params: dict[str, Any] = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": qty,
        "positionIdx": position_idx,
    }
    if price:
        params["price"] = price
    if time_in_force:
        params["timeInForce"] = time_in_force
    if trigger_price:
        params["triggerPrice"] = trigger_price
    if trigger_direction:
        params["triggerDirection"] = trigger_direction
    if take_profit:
        params["takeProfit"] = take_profit
    if stop_loss:
        params["stopLoss"] = stop_loss
    if reduce_only:
        params["reduceOnly"] = reduce_only
    if order_link_id:
        params["orderLinkId"] = order_link_id
    if tp_order_type:
        params["tpOrderType"] = tp_order_type
    if sl_order_type:
        params["slOrderType"] = sl_order_type
    if tp_limit_price:
        params["tpLimitPrice"] = tp_limit_price
    if sl_limit_price:
        params["slLimitPrice"] = sl_limit_price
    if is_leverage is not None:
        params["isLeverage"] = is_leverage
    return format_response(private_session.place_order(**params))


def cancel_order(
    category: str,
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
) -> dict[str, Any]:
    """Cancel an active order.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT
        order_id: Bybit order ID (provide this or order_link_id)
        order_link_id: Custom order ID (provide this or order_id)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "symbol": symbol}
    if order_id:
        params["orderId"] = order_id
    if order_link_id:
        params["orderLinkId"] = order_link_id
    return format_response(private_session.cancel_order(**params))


def cancel_all_orders(
    category: str,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Cancel all active orders for a category (optionally filtered by symbol).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair to cancel orders for (optional, cancels all if omitted)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category}
    if symbol:
        params["symbol"] = symbol
    return format_response(private_session.cancel_all_orders(**params))


def amend_order(
    category: str,
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    qty: str | None = None,
    price: str | None = None,
    trigger_price: str | None = None,
    take_profit: str | None = None,
    stop_loss: str | None = None,
) -> dict[str, Any]:
    """Modify an existing active order (change price, qty, TP/SL).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT
        order_id: Bybit order ID (provide this or order_link_id)
        order_link_id: Custom order ID (provide this or order_id)
        qty: New quantity
        price: New price
        trigger_price: New trigger price
        take_profit: New take profit price
        stop_loss: New stop loss price
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "symbol": symbol}
    if order_id:
        params["orderId"] = order_id
    if order_link_id:
        params["orderLinkId"] = order_link_id
    if qty:
        params["qty"] = qty
    if price:
        params["price"] = price
    if trigger_price:
        params["triggerPrice"] = trigger_price
    if take_profit:
        params["takeProfit"] = take_profit
    if stop_loss:
        params["stopLoss"] = stop_loss
    return format_response(private_session.amend_order(**params))


def get_open_orders(
    category: str,
    symbol: str | None = None,
    order_id: str | None = None,
    order_link_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get all active/open orders.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter (optional)
        order_id: Filter by specific order ID
        order_link_id: Filter by custom order ID
        limit: Results per page 1-50 (default: 20)
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "limit": limit}
    if symbol:
        params["symbol"] = symbol
    if order_id:
        params["orderId"] = order_id
    if order_link_id:
        params["orderLinkId"] = order_link_id
    return format_response(private_session.get_open_orders(**params))


def get_order_history(
    category: str,
    symbol: str | None = None,
    order_status: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get order history (filled, cancelled, rejected orders).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter (optional)
        order_status: Filter by status - Cancelled, Filled, Rejected, etc.
        limit: Results per page 1-50 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    _require_auth()
    params: dict[str, Any] = {"category": category, "limit": limit}
    if symbol:
        params["symbol"] = symbol
    if order_status:
        params["orderStatus"] = order_status
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(private_session.get_order_history(**params))


def batch_place_orders(
    category: str,
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Place multiple orders in a single request (up to 20).

    Args:
        category: Product type - linear, inverse, spot, option
        orders: List of order dicts, each with: symbol, side, orderType, qty, and optional price, timeInForce, etc.
    """
    _require_auth()
    return format_response(
        private_session.place_batch_order(category=category, request=orders)
    )


def batch_cancel_orders(
    category: str,
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cancel multiple orders in a single request.

    Args:
        category: Product type - linear, inverse, spot, option
        orders: List of dicts with symbol and either orderId or orderLinkId
    """
    _require_auth()
    return format_response(
        private_session.cancel_batch_order(category=category, request=orders)
    )
