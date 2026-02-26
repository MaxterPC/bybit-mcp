"""OAuth 2.1 Authorization Server + API Key auth for Bybit MCP.

Two authentication mechanisms coexist:
1. OAuth 2.1 Authorization Code + PKCE (for Claude custom integrations)
2. Static API key as Bearer token (for Manus, Claude Code)
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict
from html import escape as html_escape
from urllib.parse import urlencode

import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

# JWT config
_ACCESS_TOKEN_TTL = 3600  # 1 hour
_REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 days
_AUTH_CODE_TTL = 600  # 10 minutes
_JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Rate limiter (sliding window)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple in-memory sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        # Prune expired timestamps
        self._timestamps[key] = [t for t in self._timestamps[key] if t > cutoff]
        if len(self._timestamps[key]) >= self.max_requests:
            return False
        self._timestamps[key].append(now)
        return True


# Global rate limiter: max 5 registrations per 10 minutes
_registration_limiter = RateLimiter(max_requests=5, window_seconds=600)


class InvalidPINError(ValueError):
    """Raised when the consent PIN is wrong or brute-force limit exceeded."""


class BybitOAuthProvider:
    """Full OAuth 2.1 provider with PKCE + static API key support."""

    _MAX_PIN_ATTEMPTS = 5

    def __init__(
        self,
        oauth_secret: str,
        api_key: str = "",
        consent_pin: str = "",
    ) -> None:
        self.oauth_secret = oauth_secret
        self.api_key = api_key
        self.consent_pin = consent_pin
        # In-memory stores (stateless per-instance; JWTs survive restarts)
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        # Pending consent sessions: consent_id -> (client, params)
        self.pending_consents: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}
        # Revoked token JTIs (for token revocation)
        self.revoked_jtis: set[str] = set()
        # PIN brute-force protection: consent_id -> failure count
        self._pin_failures: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Rate-limit registrations globally (5 per 10 min)
        if not _registration_limiter.check("global"):
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Rate limit exceeded. Try again later.",
            )

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

    def approve_consent(self, consent_id: str, pin: str = "") -> str:
        """Approve a consent request. Returns the redirect URL with auth code.

        If a consent_pin is configured, the caller must provide the correct PIN.
        Raises InvalidPINError on wrong PIN (max 5 attempts per consent).
        """
        if consent_id not in self.pending_consents:
            raise ValueError("Invalid or expired consent")

        # Verify PIN when configured
        if self.consent_pin:
            # Check brute-force limit
            failures = self._pin_failures.get(consent_id, 0)
            if failures >= self._MAX_PIN_ATTEMPTS:
                self.pending_consents.pop(consent_id, None)
                self._pin_failures.pop(consent_id, None)
                raise InvalidPINError("Too many failed attempts. Authorization cancelled.")

            # Always run compare_digest for uniform timing (no short-circuit)
            pin_ok = secrets.compare_digest(pin or "", self.consent_pin)
            if not pin_ok:
                self._pin_failures[consent_id] = failures + 1
                raise InvalidPINError("Invalid PIN")

        # PIN passed (or not required) — clean up failure counter and consume consent
        self._pin_failures.pop(consent_id, None)
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

        # Revoke the old refresh token (rotation)
        old_payload = self._decode_jwt(refresh_token.token, skip_revocation_check=True)
        if old_payload and old_payload.get("jti"):
            self.revoked_jtis.add(old_payload["jti"])

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
    # Revocation (jti blacklist)
    # ------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Revoke a token by adding its jti to the blacklist."""
        raw = token.token
        payload = self._decode_jwt(raw, skip_revocation_check=True)
        if payload and payload.get("jti"):
            self.revoked_jtis.add(payload["jti"])

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

    def _decode_jwt(self, token: str, *, skip_revocation_check: bool = False) -> dict | None:
        try:
            payload = jwt.decode(
                token,
                self.oauth_secret,
                algorithms=[_JWT_ALGORITHM],
                issuer="bybit-mcp",
                audience="bybit-mcp",
            )
        except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
            return None

        # Check jti revocation blacklist
        if not skip_revocation_check and payload.get("jti") in self.revoked_jtis:
            return None

        return payload

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

PIN_FIELD_HTML = """<div class="pin-group">
      <label>Security PIN</label>
      <input type="password" name="pin" class="pin-input"
             placeholder="Enter PIN" required autocomplete="off">
    </div>"""

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
  .pin-group {
    margin-bottom: 24px;
  }
  .pin-group label {
    display: block;
    font-size: 13px;
    color: #888;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .pin-input {
    width: 100%;
    padding: 12px 16px;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    background: #0a0a0f;
    color: #e0e0e0;
    font-size: 16px;
    letter-spacing: 4px;
    text-align: center;
    outline: none;
    transition: border-color 0.2s;
  }
  .pin-input:focus {
    border-color: #f7a600;
  }
  .pin-input::placeholder {
    letter-spacing: normal;
    color: #555;
  }
  .error-msg {
    color: #ef4444;
    font-size: 13px;
    margin-top: 8px;
    display: none;
  }
  .error-msg.show {
    display: block;
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
    {pin_field}
    <div class="error-msg {error_class}">{error_msg}</div>
    <div class="buttons">
      <button type="submit" name="action" value="deny" class="btn btn-deny">Deny</button>
      <button type="submit" name="action" value="approve" class="btn btn-approve">Approve</button>
    </div>
  </form>
</div>
</body>
</html>"""
