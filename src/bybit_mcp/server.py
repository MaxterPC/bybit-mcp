import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from bybit_mcp.config import BYBIT_TESTNET, MCP_API_KEY, OAUTH_SECRET, PORT, SERVICE_URL
from bybit_mcp.tools import account, asset, market, position, trading

# ---------------------------------------------------------------------------
# Auth: OAuth 2.1 + API Key when OAUTH_SECRET is configured
# ---------------------------------------------------------------------------
_auth_kwargs: dict[str, Any] = {}
_oauth_provider = None

if OAUTH_SECRET:
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions

    from bybit_mcp.auth import BybitOAuthProvider

    _oauth_provider = BybitOAuthProvider(oauth_secret=OAUTH_SECRET, api_key=MCP_API_KEY)
    _auth_kwargs["auth_server_provider"] = _oauth_provider
    _auth_kwargs["auth"] = AuthSettings(
        issuer_url=SERVICE_URL,
        resource_server_url=SERVICE_URL,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    )

mcp = FastMCP(
    "Bybit Trading",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=PORT,
    **_auth_kwargs,
)


# ---------------------------------------------------------------------------
# Consent page (OAuth authorization approval)
# ---------------------------------------------------------------------------

@mcp.custom_route("/consent", methods=["GET", "POST"])
async def consent_page(request: Request) -> Response:
    """Render consent page (GET) or process approval/denial (POST)."""
    if _oauth_provider is None:
        return Response("OAuth not configured", status_code=503)

    if request.method == "GET":
        consent_id = request.query_params.get("id", "")
        if consent_id not in _oauth_provider.pending_consents:
            return Response("Invalid or expired consent request", status_code=400)

        from bybit_mcp.auth import CONSENT_PAGE_HTML

        html = CONSENT_PAGE_HTML.replace("{consent_id}", consent_id)
        return HTMLResponse(html)

    # POST — process approval or denial
    form = await request.form()
    consent_id = form.get("consent_id", "")
    action = form.get("action", "deny")

    try:
        if action == "approve":
            redirect_url = _oauth_provider.approve_consent(consent_id)
        else:
            redirect_url = _oauth_provider.deny_consent(consent_id)
    except ValueError:
        return Response("Invalid or expired consent request", status_code=400)

    return RedirectResponse(url=redirect_url, status_code=302)

# ---------------------------------------------------------------------------
# Market Data Tools (public - no auth required)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_tickers(category: str, symbol: str | None = None) -> str:
    """Get real-time ticker data including price, volume, 24h change, and funding rate.

    Args:
        category: Product type - spot, linear, inverse, or option
        symbol: Trading pair e.g. BTCUSDT (required for option)
    """
    return json.dumps(market.get_tickers(category, symbol))


@mcp.tool()
def get_klines(
    symbol: str,
    interval: str,
    category: str = "linear",
    limit: int = 200,
    start: int | None = None,
    end: int | None = None,
) -> str:
    """Get candlestick/kline historical data for technical analysis.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval: Candle interval - 1,3,5,15,30,60,120,240,360,720,D,W,M (minutes or D/W/M)
        category: Product type - spot, linear, inverse (default: linear)
        limit: Number of candles 1-1000 (default: 200)
        start: Start timestamp in milliseconds
        end: End timestamp in milliseconds
    """
    return json.dumps(market.get_klines(symbol, interval, category, limit, start, end))


@mcp.tool()
def get_orderbook(
    symbol: str,
    category: str = "linear",
    limit: int = 25,
) -> str:
    """Get order book depth data showing bids and asks.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - spot, linear, inverse, option
        limit: Depth limit - spot:1-200, linear/inverse:1-500, option:1-25
    """
    return json.dumps(market.get_orderbook(symbol, category, limit))


@mcp.tool()
def get_recent_trades(
    symbol: str,
    category: str = "linear",
    limit: int = 60,
) -> str:
    """Get recent public trades executed on the exchange.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - spot, linear, inverse, option
        limit: Number of trades 1-1000 (default: 60)
    """
    return json.dumps(market.get_recent_trades(symbol, category, limit))


@mcp.tool()
def get_instruments(
    category: str,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> str:
    """Get instrument specifications including tick size, lot size, leverage limits, and trading rules.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT (optional)
        status: Filter - Trading, Settling, Delivering, Closed
        limit: Results per page (default: 500)
    """
    return json.dumps(market.get_instruments(category, symbol, status, limit))


@mcp.tool()
def get_funding_rate_history(
    symbol: str,
    category: str = "linear",
    limit: int = 200,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get historical funding rate data for perpetual contracts.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        category: Product type - linear or inverse
        limit: Results 1-200 (default: 200)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(
        market.get_funding_rate_history(symbol, category, limit, start_time, end_time)
    )


@mcp.tool()
def get_mark_price_kline(
    symbol: str,
    interval: str,
    category: str = "linear",
    limit: int = 200,
    start: int | None = None,
    end: int | None = None,
) -> str:
    """Get mark price kline/candlestick data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval: Candle interval - 1,3,5,15,30,60,120,240,360,720,D,W,M
        category: Product type - linear or inverse
        limit: Results 1-1000 (default: 200)
        start: Start timestamp in milliseconds
        end: End timestamp in milliseconds
    """
    return json.dumps(
        market.get_mark_price_kline(symbol, interval, category, limit, start, end)
    )


@mcp.tool()
def get_open_interest(
    symbol: str,
    interval_time: str,
    category: str = "linear",
    limit: int = 200,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get historical open interest data.

    Args:
        symbol: Trading pair e.g. BTCUSDT
        interval_time: Interval - 5min, 15min, 30min, 1h, 4h, 1d
        category: Product type - linear or inverse
        limit: Results 1-200 (default: 200)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(
        market.get_open_interest(
            symbol, interval_time, category, limit, start_time, end_time
        )
    )


@mcp.tool()
def get_server_time() -> str:
    """Get Bybit server time. Useful for checking connectivity and time sync."""
    return json.dumps(market.get_server_time())


# ---------------------------------------------------------------------------
# Trading Tools (require Bybit API auth)
# ---------------------------------------------------------------------------


@mcp.tool()
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
) -> str:
    """Place a new order on Bybit (market, limit, or conditional with optional TP/SL).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT
        side: Buy or Sell
        order_type: Market or Limit
        qty: Order quantity as string e.g. "0.001"
        price: Limit price (required for Limit orders)
        time_in_force: GTC, IOC, FOK, or PostOnly
        trigger_price: Trigger price for conditional orders
        trigger_direction: 1=price rises to trigger, 2=price falls to trigger
        take_profit: Take profit price
        stop_loss: Stop loss price
        reduce_only: If true, only reduces existing position
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
        order_link_id: Custom order ID (max 36 chars, unique)
        tp_order_type: TP execution type - Market or Limit
        sl_order_type: SL execution type - Market or Limit
        tp_limit_price: Limit price for TP (when tp_order_type=Limit)
        sl_limit_price: Limit price for SL (when sl_order_type=Limit)
        is_leverage: 0=spot, 1=margin trading (spot only)
    """
    return json.dumps(
        trading.place_order(
            category,
            symbol,
            side,
            order_type,
            qty,
            price,
            time_in_force,
            trigger_price,
            trigger_direction,
            take_profit,
            stop_loss,
            reduce_only,
            position_idx,
            order_link_id,
            tp_order_type,
            sl_order_type,
            tp_limit_price,
            sl_limit_price,
            is_leverage,
        )
    )


@mcp.tool()
def cancel_order(
    category: str,
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
) -> str:
    """Cancel an active order by order ID or custom order link ID.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair e.g. BTCUSDT
        order_id: Bybit order ID (provide this or order_link_id)
        order_link_id: Custom order ID (provide this or order_id)
    """
    return json.dumps(trading.cancel_order(category, symbol, order_id, order_link_id))


@mcp.tool()
def cancel_all_orders(
    category: str,
    symbol: str | None = None,
) -> str:
    """Cancel all active orders for a category, optionally filtered by symbol.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair to cancel orders for (cancels all if omitted)
    """
    return json.dumps(trading.cancel_all_orders(category, symbol))


@mcp.tool()
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
) -> str:
    """Modify an existing order (change price, quantity, trigger, TP/SL).

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
    return json.dumps(
        trading.amend_order(
            category,
            symbol,
            order_id,
            order_link_id,
            qty,
            price,
            trigger_price,
            take_profit,
            stop_loss,
        )
    )


@mcp.tool()
def get_open_orders(
    category: str,
    symbol: str | None = None,
    order_id: str | None = None,
    order_link_id: str | None = None,
    limit: int = 20,
) -> str:
    """Get all active/open orders.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter
        order_id: Filter by specific order ID
        order_link_id: Filter by custom order ID
        limit: Results per page 1-50 (default: 20)
    """
    return json.dumps(
        trading.get_open_orders(category, symbol, order_id, order_link_id, limit)
    )


@mcp.tool()
def get_order_history(
    category: str,
    symbol: str | None = None,
    order_status: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get order history (filled, cancelled, rejected orders).

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter
        order_status: Filter - Cancelled, Filled, Rejected, etc.
        limit: Results 1-50 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(
        trading.get_order_history(
            category, symbol, order_status, limit, start_time, end_time
        )
    )


@mcp.tool()
def batch_place_orders(
    category: str,
    orders: list[dict[str, Any]],
) -> str:
    """Place multiple orders in a single request (up to 20 orders).

    Args:
        category: Product type - linear, inverse, spot, option
        orders: List of order objects. Each must have: symbol, side, orderType, qty. Optional: price, timeInForce, positionIdx, etc.
    """
    return json.dumps(trading.batch_place_orders(category, orders))


@mcp.tool()
def batch_cancel_orders(
    category: str,
    orders: list[dict[str, Any]],
) -> str:
    """Cancel multiple orders in a single request.

    Args:
        category: Product type - linear, inverse, spot, option
        orders: List of objects with symbol and either orderId or orderLinkId
    """
    return json.dumps(trading.batch_cancel_orders(category, orders))


# ---------------------------------------------------------------------------
# Account Tools (require Bybit API auth)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_wallet_balance(
    account_type: str = "UNIFIED",
    coin: str | None = None,
) -> str:
    """Get wallet balance showing equity, available balance, unrealized PnL per coin.

    Args:
        account_type: UNIFIED (default) or CONTRACT
        coin: Specific coin e.g. USDT, BTC (comma-separated for multiple)
    """
    return json.dumps(account.get_wallet_balance(account_type, coin))


@mcp.tool()
def get_fee_rate(
    category: str,
    symbol: str | None = None,
) -> str:
    """Get current trading fee rates.

    Args:
        category: Product type - spot, linear, inverse, option
        symbol: Trading pair filter
    """
    return json.dumps(account.get_fee_rate(category, symbol))


@mcp.tool()
def get_account_info() -> str:
    """Get account information including margin mode, account type, and SMP group."""
    return json.dumps(account.get_account_info())


@mcp.tool()
def get_transaction_log(
    category: str | None = None,
    coin: str | None = None,
    type: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get transaction log (trades, funding fees, transfers, settlements).

    Args:
        category: Product type filter - spot, linear, inverse, option
        coin: Coin filter e.g. USDT
        type: Transaction type - TRANSFER_IN, TRANSFER_OUT, TRADE, FEE, FUNDING_FEE, etc.
        limit: Results 1-50 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(
        account.get_transaction_log(category, coin, type, limit, start_time, end_time)
    )


# ---------------------------------------------------------------------------
# Position Tools (require Bybit API auth)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_positions(
    category: str,
    symbol: str | None = None,
    settle_coin: str | None = None,
    limit: int = 20,
) -> str:
    """Get current open positions with real-time PnL, leverage, and margin data.

    Args:
        category: Product type - linear, inverse, option
        symbol: Trading pair filter
        settle_coin: Settlement coin filter e.g. USDT, USDC
        limit: Results 1-200 (default: 20)
    """
    return json.dumps(position.get_positions(category, symbol, settle_coin, limit))


@mcp.tool()
def set_leverage(
    category: str,
    symbol: str,
    buy_leverage: str,
    sell_leverage: str,
) -> str:
    """Set leverage for a trading pair.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        buy_leverage: Buy side leverage e.g. "10"
        sell_leverage: Sell side leverage e.g. "10"
    """
    return json.dumps(
        position.set_leverage(category, symbol, buy_leverage, sell_leverage)
    )


@mcp.tool()
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
) -> str:
    """Set take profit and/or stop loss for an existing position.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        take_profit: TP price (set "0" to cancel)
        stop_loss: SL price (set "0" to cancel)
        tp_trigger_by: TP trigger type - LastPrice, IndexPrice, MarkPrice
        sl_trigger_by: SL trigger type - LastPrice, IndexPrice, MarkPrice
        tpsl_mode: Full (entire position) or Partial
        tp_order_type: Market or Limit
        sl_order_type: Market or Limit
        tp_limit_price: Limit price for TP
        sl_limit_price: Limit price for SL
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
    """
    return json.dumps(
        position.set_trading_stop(
            category,
            symbol,
            take_profit,
            stop_loss,
            tp_trigger_by,
            sl_trigger_by,
            tpsl_mode,
            tp_order_type,
            sl_order_type,
            tp_limit_price,
            sl_limit_price,
            position_idx,
        )
    )


@mcp.tool()
def switch_position_mode(
    category: str,
    mode: int,
    symbol: str | None = None,
    coin: str | None = None,
) -> str:
    """Switch between one-way and hedge position mode.

    Args:
        category: Product type - linear or inverse
        mode: 0=Merged (one-way), 3=Both Sides (hedge mode)
        symbol: Trading pair (required for linear)
        coin: Coin (required for inverse)
    """
    return json.dumps(position.switch_position_mode(category, mode, symbol, coin))


@mcp.tool()
def set_auto_add_margin(
    category: str,
    symbol: str,
    auto_add_margin: int,
    position_idx: int = 0,
) -> str:
    """Enable or disable auto-add margin for isolated margin positions.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair e.g. BTCUSDT
        auto_add_margin: 0=disable, 1=enable
        position_idx: 0=one-way, 1=hedge-buy, 2=hedge-sell
    """
    return json.dumps(
        position.set_auto_add_margin(category, symbol, auto_add_margin, position_idx)
    )


@mcp.tool()
def get_closed_pnl(
    category: str,
    symbol: str | None = None,
    limit: int = 20,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get closed position profit and loss history.

    Args:
        category: Product type - linear or inverse
        symbol: Trading pair filter
        limit: Results 1-100 (default: 20)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(
        position.get_closed_pnl(category, symbol, limit, start_time, end_time)
    )


# ---------------------------------------------------------------------------
# Asset Management Tools (require Bybit API auth)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_coin_balance(
    account_type: str = "UNIFIED",
    coin: str | None = None,
    member_id: str | None = None,
    with_bonus: int | None = None,
) -> str:
    """Get coin balance across different account types.

    Args:
        account_type: UNIFIED, CONTRACT, SPOT, INVESTMENT, OPTION, FUND
        coin: Coin name e.g. USDT, BTC
        member_id: Sub-account member ID (master account only)
        with_bonus: 0=exclude bonus, 1=include bonus
    """
    return json.dumps(
        asset.get_coin_balance(account_type, coin, member_id, with_bonus)
    )


@mcp.tool()
def internal_transfer(
    coin: str,
    amount: str,
    from_account_type: str,
    to_account_type: str,
    transfer_id: str | None = None,
) -> str:
    """Transfer funds between your own accounts (e.g. UNIFIED to FUND).

    Args:
        coin: Coin to transfer e.g. USDT
        amount: Amount as string e.g. "100"
        from_account_type: Source - UNIFIED, CONTRACT, SPOT, FUND
        to_account_type: Destination - UNIFIED, CONTRACT, SPOT, FUND
        transfer_id: Custom UUID (auto-generated if omitted)
    """
    return json.dumps(
        asset.internal_transfer(coin, amount, from_account_type, to_account_type, transfer_id)
    )


@mcp.tool()
def get_deposit_records(
    coin: str | None = None,
    limit: int = 50,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get deposit history records.

    Args:
        coin: Coin filter e.g. USDT
        limit: Results 1-50 (default: 50)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(asset.get_deposit_records(coin, limit, start_time, end_time))


@mcp.tool()
def get_withdrawal_records(
    coin: str | None = None,
    limit: int = 50,
    start_time: int | None = None,
    end_time: int | None = None,
) -> str:
    """Get withdrawal history records.

    Args:
        coin: Coin filter e.g. USDT
        limit: Results 1-50 (default: 50)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    return json.dumps(asset.get_withdrawal_records(coin, limit, start_time, end_time))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    env_label = "TESTNET" if BYBIT_TESTNET else "MAINNET"
    if OAUTH_SECRET:
        auth_label = "OAuth 2.1"
        if MCP_API_KEY:
            auth_label += " + API Key"
    else:
        auth_label = "NO AUTH"
    print(f"Starting Bybit MCP Server ({env_label}, {auth_label}) on port {PORT}...")
    print(f"Service URL: {SERVICE_URL}")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
