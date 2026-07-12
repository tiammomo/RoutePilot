"""Secure-by-default authentication adapter for the V1 API."""

from __future__ import annotations

import hmac
import inspect
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from .models import Principal


Authenticator = Callable[[Request], Principal | Awaitable[Principal]]
TokenDecoder = Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]]


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "AUTHENTICATION_REQUIRED",
            "message": "Authentication is required.",
            "retryable": False,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(request: Request) -> str:
    value = request.headers.get("Authorization", "")
    scheme, separator, token = value.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise _authentication_error()
    token = token.strip()
    if len(token) > 16_384 or any(character.isspace() for character in token):
        raise _authentication_error()
    return token


@dataclass(frozen=True, slots=True)
class OIDCSettings:
    """Explicit OIDC JWT verification settings."""

    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    tenant_claim: str = "tenant_id"
    roles_claim: str = "roles"
    authorization_epoch_claim: str = "authorization_epoch"
    leeway_seconds: int = 30

    def __post_init__(self) -> None:
        allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        if not self.issuer or not self.audience or not self.jwks_url:
            raise ValueError("issuer, audience, and jwks_url are required")
        if not self.algorithms or not set(self.algorithms).issubset(allowed):
            raise ValueError("OIDC algorithms must be an explicit asymmetric allowlist")
        parsed = urlparse(self.jwks_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("OIDC JWKS URL must use HTTP(S)")
        environment = os.getenv("ENVIRONMENT", "dev").strip().lower()
        if environment in {"production", "prod", "staging"} and parsed.scheme != "https":
            raise ValueError("OIDC JWKS URL must use HTTPS outside local/test environments")

    @classmethod
    def from_environment(cls) -> "OIDCSettings | None":
        values = {
            "issuer": os.getenv("ROUTEPILOT_OIDC_ISSUER", "").strip(),
            "audience": os.getenv("ROUTEPILOT_OIDC_AUDIENCE", "").strip(),
            "jwks_url": os.getenv("ROUTEPILOT_OIDC_JWKS_URL", "").strip(),
        }
        if not any(values.values()):
            return None
        if not all(values.values()):
            raise RuntimeError("ROUTEPILOT OIDC issuer, audience, and JWKS URL must be set together")
        algorithms = tuple(
            item.strip()
            for item in os.getenv("ROUTEPILOT_OIDC_ALGORITHMS", "RS256,ES256").split(",")
            if item.strip()
        )
        return cls(
            issuer=values["issuer"],
            audience=values["audience"],
            jwks_url=values["jwks_url"],
            algorithms=algorithms,
            tenant_claim=os.getenv("ROUTEPILOT_OIDC_TENANT_CLAIM", "tenant_id").strip(),
            roles_claim=os.getenv("ROUTEPILOT_OIDC_ROLES_CLAIM", "roles").strip(),
            authorization_epoch_claim=os.getenv(
                "ROUTEPILOT_OIDC_AUTHORIZATION_EPOCH_CLAIM",
                "authorization_epoch",
            ).strip(),
        )


class OIDCAuthenticator:
    """Verify OIDC access tokens and derive the server-trusted tenant principal."""

    def __init__(self, settings: OIDCSettings, *, decoder: TokenDecoder | None = None):
        self.settings = settings
        self._jwk_client = PyJWKClient(
            settings.jwks_url,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )
        self._decoder = decoder or self._decode_verified

    def _decode_verified(self, token: str) -> dict[str, Any]:
        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(self.settings.algorithms),
            audience=self.settings.audience,
            issuer=self.settings.issuer,
            leeway=self.settings.leeway_seconds,
            options={
                "require": ["exp", "iat", "iss", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        return claims if isinstance(claims, dict) else {}

    @staticmethod
    def _roles(raw: Any) -> frozenset[str]:
        if isinstance(raw, str):
            values = raw.replace(",", " ").split()
        elif isinstance(raw, list):
            values = [item for item in raw if isinstance(item, str)]
        else:
            values = []
        normalized = {item.strip() for item in values if 0 < len(item.strip()) <= 64}
        if len(normalized) > 64:
            raise _authentication_error()
        return frozenset(normalized)

    async def __call__(self, request: Request) -> Principal:
        token = _bearer_token(request)
        try:
            result = self._decoder(token)
            claims = await result if inspect.isawaitable(result) else result
        except (InvalidTokenError, PyJWKClientError, ValueError, TypeError):
            raise _authentication_error() from None
        tenant_id = claims.get(self.settings.tenant_claim)
        user_id = claims.get("sub")
        if not isinstance(tenant_id, str) or not isinstance(user_id, str):
            raise _authentication_error()
        if not (0 < len(tenant_id.strip()) <= 128 and 0 < len(user_id.strip()) <= 128):
            raise _authentication_error()
        raw_epoch = claims.get(self.settings.authorization_epoch_claim, 0)
        if isinstance(raw_epoch, bool):
            raise _authentication_error()
        try:
            epoch = int(raw_epoch)
        except (TypeError, ValueError):
            raise _authentication_error() from None
        if epoch < 0:
            raise _authentication_error()
        return Principal(
            tenant_id=tenant_id.strip(),
            user_id=user_id.strip(),
            roles=self._roles(claims.get(self.settings.roles_claim)),
            authorization_epoch=epoch,
        )


def install_oidc_authenticator(app: Any) -> None:
    """Install configured OIDC verification without performing startup network I/O."""

    settings = OIDCSettings.from_environment()
    if settings is not None:
        app.state.routepilot_v1_authenticator = OIDCAuthenticator(settings)


def _is_loopback(host: str | None) -> bool:
    """Return whether a request peer is local-only."""

    normalized = str(host or "").strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_development_environment() -> bool:
    """Keep every header-based development identity out of deployed environments."""

    environments = {
        os.getenv("ENVIRONMENT", "dev").strip().lower(),
        os.getenv("ROUTEPILOT_DEPLOYMENT_ENV", "").strip().lower(),
    }
    return not environments.intersection({"production", "prod", "staging", "preprod"})


def _trusted_development_bff(request: Request) -> bool:
    """Authenticate a non-loopback local BFF with an operator-provided secret."""

    expected = os.getenv("ROUTEPILOT_V1_DEV_BFF_SECRET", "").strip()
    provided = request.headers.get("X-RoutePilot-Dev-BFF-Secret", "").strip()
    return (
        len(expected) >= 32
        and len(provided) == len(expected)
        and hmac.compare_digest(provided, expected)
    )


async def require_principal(request: Request) -> Principal:
    """Resolve an authenticated principal without trusting public tenant headers.

    Production deployments must install `app.state.routepilot_v1_authenticator`
    from the same-origin BFF/OIDC adapter. A header-based development principal
    is available only behind an explicit flag and from a loopback peer.
    """

    authenticator = getattr(request.app.state, "routepilot_v1_authenticator", None)
    if authenticator is not None:
        result = authenticator(request)
        principal = await result if inspect.isawaitable(result) else result
        if not isinstance(principal, Principal):
            raise RuntimeError("routepilot_v1_authenticator must return Principal")
        return principal

    dev_enabled = os.getenv("ROUTEPILOT_V1_DEV_AUTH", "").strip().lower() in {"1", "true", "yes"}
    client_host = request.client.host if request.client else None
    trusted_peer = _is_loopback(client_host) or _trusted_development_bff(request)
    if dev_enabled and _is_development_environment() and trusted_peer:
        tenant_id = request.headers.get("X-RoutePilot-Dev-Tenant", "").strip()
        user_id = request.headers.get("X-RoutePilot-Dev-User", "").strip()
        if tenant_id and user_id:
            roles = frozenset(
                item.strip()
                for item in request.headers.get("X-RoutePilot-Dev-Roles", "owner").split(",")
                if item.strip()
            )
            return Principal(tenant_id=tenant_id, user_id=user_id, roles=roles)

    raise _authentication_error()
