from typing import Any

from bybit_mcp.config import private_session
from bybit_mcp.utils.formatters import format_response


def _require_auth() -> None:
    if private_session is None:
        raise RuntimeError("Bybit API credentials not configured. Set BYBIT_API_KEY and BYBIT_API_SECRET.")


def get_coin_balance(
    account_type: str = "UNIFIED",
    coin: str | None = None,
    member_id: str | None = None,
    with_bonus: int | None = None,
) -> dict[str, Any]:
    """Get balance for a specific coin across account types.

    Args:
        account_type: UNIFIED, CONTRACT, SPOT, INVESTMENT, OPTION, FUND
        coin: Coin name e.g. USDT, BTC
        member_id: Sub-account member ID (master account only)
        with_bonus: 0=exclude bonus, 1=include bonus
    """
    _require_auth()
    params: dict[str, Any] = {"accountType": account_type}
    if coin:
        params["coin"] = coin
    if member_id:
        params["memberId"] = member_id
    if with_bonus is not None:
        params["withBonus"] = with_bonus
    return format_response(private_session.get_coins_balance(**params))


def internal_transfer(
    coin: str,
    amount: str,
    from_account_type: str,
    to_account_type: str,
    transfer_id: str | None = None,
) -> dict[str, Any]:
    """Transfer funds between your own account types (e.g. UNIFIED to FUND).

    Args:
        coin: Coin to transfer e.g. USDT
        amount: Amount to transfer as string
        from_account_type: Source account - UNIFIED, CONTRACT, SPOT, FUND, etc.
        to_account_type: Destination account - UNIFIED, CONTRACT, SPOT, FUND, etc.
        transfer_id: Custom UUID for the transfer (auto-generated if omitted)
    """
    _require_auth()
    import uuid

    params: dict[str, Any] = {
        "transferId": transfer_id or str(uuid.uuid4()),
        "coin": coin,
        "amount": amount,
        "fromAccountType": from_account_type,
        "toAccountType": to_account_type,
    }
    return format_response(private_session.create_internal_transfer(**params))


def get_deposit_records(
    coin: str | None = None,
    limit: int = 50,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get deposit history records.

    Args:
        coin: Coin filter e.g. USDT (optional)
        limit: Results per page 1-50 (default: 50)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    _require_auth()
    params: dict[str, Any] = {"limit": limit}
    if coin:
        params["coin"] = coin
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(private_session.get_deposit_records(**params))


def get_withdrawal_records(
    coin: str | None = None,
    limit: int = 50,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Get withdrawal history records.

    Args:
        coin: Coin filter e.g. USDT (optional)
        limit: Results per page 1-50 (default: 50)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    """
    _require_auth()
    params: dict[str, Any] = {"limit": limit}
    if coin:
        params["coin"] = coin
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return format_response(private_session.get_withdraw_records(**params))
