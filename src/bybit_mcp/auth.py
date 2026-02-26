"""OAuth 2.1 Authorization Server + API Key auth for Bybit MCP.

Two authentication mechanisms coexist:
1. OAuth 2.1 Authorization Code + PKCE (for Claude custom integrations)
2. Static API key as Bearer token (for Manus, Claude Code)
"""

from __future__ import annotations

import secrets
import time
from html import escape as html_escape
from urllib.parse import urlencode

import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

# JWT config
_ACCESS_TOKEN_TTL = 3600  # 1 hour
_REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days
_AUTH_CODE_TTL = 600  # 10 minutes
_JWT_ALGORITHM = "HS256"


class BybitOAuthProvider:
    """Full OAuth 2.1 provider with PKCE + static API key support."""

    def __init__(self, oauth_secret: str, api_key: str = "") -> None:
        self.oauth_secret = oauth_secret
        self.api_key = api_key
        # In-memory stores (stateless per-instance; JWTs survive restarts)
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        # Pending consent sessions: consent_id -> (client, params)
        self.pending_consents: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    # ------------------------------------------------------------------
    # Authorization flow
    # ------------------------------------------------------------------

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Store pending consent and return consent page URL."""
        consent_id = secrets.token_urlsafe(32)
        self.pending_consents[consent_id] = (client, params)
        return f"/consent?id={consent_id}"

    def approve_consent(self, consent_id: str) -> str:
        """Approve a consent request. Returns the redirect URL with auth code."""
        if consent_id not in self.pending_consents:
            raise ValueError("Invalid or expired consent")

        client, params = self.pending_consents.pop(consent_id)

        code = secrets.token_urlsafe(32)
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + _AUTH_CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )

        return construct_redirect_uri(
            str(params.redirect_uri),
            code=code,
            state=params.state,
        )

    def deny_consent(self, consent_id: str) -> str:
        """Deny a consent request. Returns redirect URL with error."""
        if consent_id not in self.pending_consents:
            raise ValueError("Invalid or expired consent")

        _client, params = self.pending_consents.pop(consent_id)
        return construct_redirect_uri(
            str(params.redirect_uri),
            error="access_denied",
            error_description="User denied access",
            state=params.state,
        )

    # ------------------------------------------------------------------
    # Authorization code
    # ------------------------------------------------------------------

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        return self.auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        # Remove code (single-use)
        self.auth_codes.pop(authorization_code.code, None)

        now = int(time.time())
        scopes = authorization_code.scopes

        access_token = self._create_jwt(
            sub=client.client_id,
            token_type="access",
            scopes=scopes,
            ttl=_ACCESS_TOKEN_TTL,
        )
        refresh_token = self._create_jwt(
            sub=client.client_id,
            token_type="refresh",
            scopes=scopes,
            ttl=_REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token,
        )

    # ------------------------------------------------------------------
    # Refresh token
    # ------------------------------------------------------------------

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        payload = self._decode_jwt(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        if payload.get("sub") != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=payload["sub"],
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        use_scopes = scopes if scopes else refresh_token.scopes

        access_token = self._create_jwt(
            sub=client.client_id,
            token_type="access",
            scopes=use_scopes,
            ttl=_ACCESS_TOKEN_TTL,
        )
        new_refresh = self._create_jwt(
            sub=client.client_id,
            token_type="refresh",
            scopes=use_scopes,
            ttl=_REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(use_scopes) if use_scopes else None,
            refresh_token=new_refresh,
        )

    # ------------------------------------------------------------------
    # Access token verification (also handles API key)
    # ------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        # Check static API key first (timing-safe comparison)
        if self.api_key and secrets.compare_digest(token, self.api_key):
            return AccessToken(
                token=token,
                client_id="api-key",
                scopes=["all"],
            )

        # Check JWT
        payload = self._decode_jwt(token)
        if not payload or payload.get("type") != "access":
            return None

        return AccessToken(
            token=token,
            client_id=payload.get("sub", "unknown"),
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
        )

    # ------------------------------------------------------------------
    # Revocation (no-op for stateless JWTs)
    # ------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        pass  # JWTs expire naturally

    # ------------------------------------------------------------------
    # JWT helpers
    # ------------------------------------------------------------------

    def _create_jwt(self, sub: str, token_type: str, scopes: list[str], ttl: int) -> str:
        now = int(time.time())
        payload = {
            "sub": sub,
            "type": token_type,
            "scopes": scopes,
            "iat": now,
            "exp": now + ttl,
            "iss": "bybit-mcp",
            "aud": "bybit-mcp",
            "jti": secrets.token_urlsafe(16),
        }
        return jwt.encode(payload, self.oauth_secret, algorithm=_JWT_ALGORITHM)

    def _decode_jwt(self, token: str) -> dict | None:
        try:
            return jwt.decode(
                token,
                self.oauth_secret,
                algorithms=[_JWT_ALGORITHM],
                issuer="bybit-mcp",
                audience="bybit-mcp",
            )
        except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
            return None

    def cleanup_expired_consents(self) -> None:
        """Remove pending consents older than the auth code TTL."""
        now = time.time()
        expired = [
            cid for cid, (_, params) in self.pending_consents.items()
            if hasattr(params, "_created_at") and now - params._created_at > _AUTH_CODE_TTL
        ]
        for cid in expired:
            self.pending_consents.pop(cid, None)


# ---------------------------------------------------------------------------
# Consent page HTML
# ---------------------------------------------------------------------------

CONSENT_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bybit Trading MCP - Authorization</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .card {
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 16px;
    padding: 40px;
    max-width: 480px;
    width: 90%;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  .logo {
    font-size: 28px;
    font-weight: 700;
    color: #f7a600;
    margin-bottom: 8px;
  }
  .subtitle {
    color: #888;
    font-size: 14px;
    margin-bottom: 28px;
  }
  .section-title {
    font-size: 13px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 12px;
  }
  .permissions {
    list-style: none;
    margin-bottom: 32px;
  }
  .permissions li {
    padding: 10px 0;
    border-bottom: 1px solid #1e1e2e;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .permissions li::before {
    content: "\\2713";
    color: #f7a600;
    font-weight: bold;
  }
  .buttons {
    display: flex;
    gap: 12px;
  }
  .btn {
    flex: 1;
    padding: 14px 24px;
    border: none;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .btn:hover { opacity: 0.85; }
  .btn-approve {
    background: #22c55e;
    color: #fff;
  }
  .btn-deny {
    background: #2a2a3a;
    color: #e0e0e0;
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">Bybit Trading MCP</div>
  <div class="subtitle">An application is requesting access to your trading server</div>
  <div class="section-title">Permissions requested</div>
  <ul class="permissions">
    <li>View market data and prices</li>
    <li>Execute trades and manage orders</li>
    <li>View account balances and positions</li>
    <li>Manage positions (leverage, TP/SL)</li>
    <li>Transfer assets between accounts</li>
  </ul>
  <form method="POST">
    <input type="hidden" name="consent_id" value="{consent_id}">
    <div class="buttons">
      <button type="submit" name="action" value="deny" class="btn btn-deny">Deny</button>
      <button type="submit" name="action" value="approve" class="btn btn-approve">Approve</button>
    </div>
  </form>
</div>
</body>
</html>"""
