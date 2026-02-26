import os

from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))

# Auth: OAuth 2.1 + API Key
OAUTH_SECRET = os.getenv("OAUTH_SECRET", "")
MCP_API_KEY = os.getenv("MCP_API_KEY", "") or os.getenv("MCP_AUTH_TOKEN", "")
SERVICE_URL = os.getenv("SERVICE_URL", f"http://localhost:{PORT}")
REGISTRATION_TOKEN = os.getenv("REGISTRATION_TOKEN", "")

# Backward compat
MCP_AUTH_TOKEN = MCP_API_KEY

# Treat placeholder values as empty
if BYBIT_API_KEY in ("", "placeholder", "your_api_key_here"):
    BYBIT_API_KEY = ""
if BYBIT_API_SECRET in ("", "placeholder", "your_api_secret_here"):
    BYBIT_API_SECRET = ""


def get_bybit_session(authenticated: bool = True) -> HTTP:
    """Create a pybit HTTP session."""
    if authenticated and BYBIT_API_KEY and BYBIT_API_SECRET:
        return HTTP(
            testnet=BYBIT_TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )
    return HTTP(testnet=BYBIT_TESTNET)


# Shared sessions - lazy init to avoid crash on startup with bad credentials
public_session = HTTP(testnet=BYBIT_TESTNET)
private_session: HTTP | None = None

if BYBIT_API_KEY and BYBIT_API_SECRET:
    try:
        private_session = get_bybit_session(authenticated=True)
    except Exception:
        private_session = None
