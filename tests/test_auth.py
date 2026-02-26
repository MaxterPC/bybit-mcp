"""Security tests for the Bybit MCP OAuth provider."""

import time

import jwt
import pytest

from bybit_mcp.auth import BybitOAuthProvider, RateLimiter, _JWT_ALGORITHM

# Shared test secret
_SECRET = "test-secret-key-for-unit-tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client_info(software_id: str | None = None):
    """Create a minimal OAuthClientInformationFull-like object for testing."""
    from mcp.shared.auth import OAuthClientInformationFull

    return OAuthClientInformationFull(
        client_id="test-client-id",
        redirect_uris=["http://localhost:3000/callback"],
        software_id=software_id,
    )


# ---------------------------------------------------------------------------
# Registration gating tests
# ---------------------------------------------------------------------------


class TestRegistrationGating:
    @pytest.mark.asyncio
    async def test_rejects_without_software_id_when_token_set(self):
        provider = BybitOAuthProvider(
            oauth_secret=_SECRET, registration_token="my-secret-token"
        )
        client = _make_client_info(software_id=None)
        with pytest.raises(Exception) as exc_info:
            await provider.register_client(client)
        assert "registration token" in str(exc_info.value).lower() or "unapproved" in str(
            exc_info.value
        ).lower()

    @pytest.mark.asyncio
    async def test_rejects_wrong_software_id(self):
        provider = BybitOAuthProvider(
            oauth_secret=_SECRET, registration_token="correct-token"
        )
        client = _make_client_info(software_id="wrong-token")
        with pytest.raises(Exception):
            await provider.register_client(client)

    @pytest.mark.asyncio
    async def test_accepts_correct_software_id(self):
        provider = BybitOAuthProvider(
            oauth_secret=_SECRET, registration_token="correct-token"
        )
        client = _make_client_info(software_id="correct-token")
        await provider.register_client(client)  # Should not raise
        assert await provider.get_client("test-client-id") is not None

    @pytest.mark.asyncio
    async def test_allows_all_when_no_registration_token(self):
        provider = BybitOAuthProvider(oauth_secret=_SECRET, registration_token="")
        client = _make_client_info(software_id=None)
        await provider.register_client(client)  # Should not raise
        assert await provider.get_client("test-client-id") is not None


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
