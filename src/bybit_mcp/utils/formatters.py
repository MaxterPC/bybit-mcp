from typing import Any


def format_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract and return the Bybit API response consistently."""
    if data.get("retCode") != 0:
        return {
            "error": True,
            "code": data.get("retCode"),
            "message": data.get("retMsg", "Unknown error"),
        }
    return data.get("result", data)
