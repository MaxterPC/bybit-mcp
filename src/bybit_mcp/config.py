import os

from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
PORT = int(os.getenv("PORT", "8080"))


def get_bybit_session(authenticated: bool = True) -> HTTP:
    """Create a pybit HTTP session."""
    if authenticated and BYBIT_API_KEY:
        return HTTP(
            testnet=BYBIT_TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )
    return HTTP(testnet=BYBIT_TESTNET)


# Shared sessions
public_session = HTTP(testnet=BYBIT_TESTNET)
private_session = get_bybit_session(authenticated=True) if BYBIT_API_KEY else None
