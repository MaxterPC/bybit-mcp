from mcp.server.auth.provider import AccessToken, TokenVerifier

from bybit_mcp.config import MCP_AUTH_TOKEN


class BearerTokenVerifier(TokenVerifier):
    """Verify bearer tokens for remote MCP access."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not MCP_AUTH_TOKEN:
            # No token configured = allow all (local dev)
            return AccessToken(token=token, client_id="local", scopes=["all"])

        if token == MCP_AUTH_TOKEN:
            return AccessToken(token=token, client_id="authorized", scopes=["all"])

        return None
