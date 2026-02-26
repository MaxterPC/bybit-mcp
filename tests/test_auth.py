"""Security tests for the Bybit MCP OAuth provider."""

import time

import jwt
import pytest

from bybit_mcp.auth import BybitOAuthProvider, InvalidPINError, RateLimiter, _JWT_ALGORITHM

# Shared test secret
_SECRET = "test-secret-key-for-unit-tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client_info():
    """Create a minimal OAuthClientInformationFull-like object for testing."""
    from mcp.shared.auth import OAuthClientInformationFull

    return OAuthClientInformationFull(
        client_id="test-client-id",
        redirect_uris=["http://localhost:3000/callback"],
    )


# ---------------------------------------------------------------------------
# Registration tests (open registration, rate-limited only)
# ---------------------------------------------------------------------------


class TestRegistration:
    @pytest.mark.asyncio
    async def test_allows_registration_without_restrictions(self):
        """Registration is open — no software_id / token needed."""
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="my-pin")
        client = _make_client_info()
        await provider.register_client(client)  # Should not raise
        assert await provider.get_client("test-client-id") is not None


# ---------------------------------------------------------------------------
# Consent PIN tests
# ---------------------------------------------------------------------------


class TestConsentPIN:
    def _setup_consent(self, provider: BybitOAuthProvider) -> str:
        """Register a client and create a pending consent, return consent_id."""
        import secrets as _secrets

        from mcp.server.auth.provider import AuthorizationParams

        client = _make_client_info()
        provider.clients[client.client_id] = client

        consent_id = _secrets.token_urlsafe(16)
        params = AuthorizationParams(
            state="test-state",
            scopes=["all"],
            code_challenge="test-challenge",
            code_challenge_method="S256",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
            response_type="code",
            client_id=client.client_id,
        )
        provider.pending_consents[consent_id] = (client, params)
        return consent_id

    def test_rejects_approve_without_pin(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="secret-pin")
        consent_id = self._setup_consent(provider)
        with pytest.raises(ValueError, match="Invalid PIN"):
            provider.approve_consent(consent_id, pin="")

    def test_rejects_approve_with_wrong_pin(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="secret-pin")
        consent_id = self._setup_consent(provider)
        with pytest.raises(ValueError, match="Invalid PIN"):
            provider.approve_consent(consent_id, pin="wrong-pin")

    def test_approves_with_correct_pin(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="secret-pin")
        consent_id = self._setup_consent(provider)
        redirect_url = provider.approve_consent(consent_id, pin="secret-pin")
        assert "code=" in redirect_url
        # Consent consumed
        assert consent_id not in provider.pending_consents

    def test_approves_without_pin_when_not_configured(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="")
        consent_id = self._setup_consent(provider)
        redirect_url = provider.approve_consent(consent_id, pin="")
        assert "code=" in redirect_url

    def test_consent_not_consumed_on_wrong_pin(self):
        """Wrong PIN must NOT consume the pending consent."""
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="correct-pin")
        consent_id = self._setup_consent(provider)

        with pytest.raises(InvalidPINError):
            provider.approve_consent(consent_id, pin="wrong-pin")

        # Consent must still be there for retry
        assert consent_id in provider.pending_consents

    def test_brute_force_lockout_after_max_attempts(self):
        """After 5 wrong PINs, consent is cancelled and removed."""
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="correct-pin")
        consent_id = self._setup_consent(provider)

        for _ in range(5):
            with pytest.raises(InvalidPINError, match="Invalid PIN"):
                provider.approve_consent(consent_id, pin="wrong")

        # 6th attempt — consent should be cancelled
        with pytest.raises(InvalidPINError, match="Too many failed attempts"):
            provider.approve_consent(consent_id, pin="correct-pin")

        # Consent consumed (removed)
        assert consent_id not in provider.pending_consents

    def test_invalid_consent_id_raises(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, consent_pin="pin")
        with pytest.raises(ValueError, match="Invalid or expired"):
            provider.approve_consent("nonexistent-id", pin="pin")


# ---------------------------------------------------------------------------
# JWT validation tests
# ---------------------------------------------------------------------------


class TestJWTValidation:
    @pytest.mark.asyncio
    async def test_rejects_expired_jwt(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        # Create an expired token manually
        payload = {
            "sub": "test",
            "type": "access",
            "scopes": [],
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,  # expired 1 hour ago
            "iss": "bybit-mcp",
            "aud": "bybit-mcp",
            "jti": "test-jti",
        }
        expired_token = jwt.encode(payload, _SECRET, algorithm=_JWT_ALGORITHM)
        result = await provider.load_access_token(expired_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_wrong_issuer(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        payload = {
            "sub": "test",
            "type": "access",
            "scopes": [],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "wrong-issuer",
            "aud": "bybit-mcp",
            "jti": "test-jti",
        }
        bad_token = jwt.encode(payload, _SECRET, algorithm=_JWT_ALGORITHM)
        result = await provider.load_access_token(bad_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_wrong_audience(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        payload = {
            "sub": "test",
            "type": "access",
            "scopes": [],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "bybit-mcp",
            "aud": "wrong-audience",
            "jti": "test-jti",
        }
        bad_token = jwt.encode(payload, _SECRET, algorithm=_JWT_ALGORITHM)
        result = await provider.load_access_token(bad_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_wrong_secret(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        payload = {
            "sub": "test",
            "type": "access",
            "scopes": [],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "bybit-mcp",
            "aud": "bybit-mcp",
            "jti": "test-jti",
        }
        bad_token = jwt.encode(payload, "wrong-secret", algorithm=_JWT_ALGORITHM)
        result = await provider.load_access_token(bad_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_accepts_valid_jwt(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        token = provider._create_jwt(sub="test", token_type="access", scopes=["all"], ttl=3600)
        result = await provider.load_access_token(token)
        assert result is not None
        assert result.client_id == "test"


# ---------------------------------------------------------------------------
# API key tests
# ---------------------------------------------------------------------------


class TestAPIKeyAuth:
    @pytest.mark.asyncio
    async def test_accepts_valid_api_key(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, api_key="my-api-key")
        result = await provider.load_access_token("my-api-key")
        assert result is not None
        assert result.client_id == "api-key"
        assert result.scopes == ["all"]

    @pytest.mark.asyncio
    async def test_rejects_wrong_api_key(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, api_key="my-api-key")
        result = await provider.load_access_token("wrong-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, api_key="")
        result = await provider.load_access_token("any-key")
        assert result is None


# ---------------------------------------------------------------------------
# Token revocation tests
# ---------------------------------------------------------------------------


class TestTokenRevocation:
    @pytest.mark.asyncio
    async def test_revoke_access_token(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        token_str = provider._create_jwt(sub="test", token_type="access", scopes=[], ttl=3600)

        # Token works before revocation
        result = await provider.load_access_token(token_str)
        assert result is not None

        # Revoke it
        await provider.revoke_token(result)

        # Token rejected after revocation
        result2 = await provider.load_access_token(token_str)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_revoke_does_not_affect_other_tokens(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET)
        token1 = provider._create_jwt(sub="test", token_type="access", scopes=[], ttl=3600)
        token2 = provider._create_jwt(sub="test", token_type="access", scopes=[], ttl=3600)

        result1 = await provider.load_access_token(token1)
        await provider.revoke_token(result1)

        # token2 should still work
        result2 = await provider.load_access_token(token2)
        assert result2 is not None


# ---------------------------------------------------------------------------
# Rate limiter tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_allows_under_threshold(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.check("key") is True
        assert limiter.check("key") is True
        assert limiter.check("key") is True

    def test_blocks_over_threshold(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.check("key") is True
        assert limiter.check("key") is True
        assert limiter.check("key") is True
        assert limiter.check("key") is False

    def test_independent_keys(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("key-a") is True
        assert limiter.check("key-a") is False
        assert limiter.check("key-b") is True  # Different key, not limited
