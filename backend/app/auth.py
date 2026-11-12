"""
Authentication via Auth0 access tokens.

The React app signs users in with Auth0 (PKCE) and sends the access token as
`Authorization: Bearer <jwt>`. Here we verify it against the tenant's
published signing keys (JWKS): RS256 signature, issuer, audience and
expiry. The tenant's post-login Action (`auth0/post-login-action.js`) adds
namespaced claims for role, department and employee name.

Each authenticated request upserts a local `User` row keyed by the token's
`sub`, so conversations (and, later, audit rows) have a stable foreign key,
and role changes in Auth0 take effect on the user's next token.
"""

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import User, utcnow

CLAIM_NAMESPACE = "https://expense-assistant/"
ROLES = ("employee", "manager", "admin")

ISSUER = f"https://{settings.auth0_domain}/"

# Fetches and caches the tenant's public signing keys; refetches on an
# unknown `kid`, so Auth0 key rotation needs no restart.
_jwks_client = jwt.PyJWKClient(f"{ISSUER}.well-known/jwks.json", cache_keys=True)

_bearer = HTTPBearer(auto_error=False)


class InvalidToken(Exception):
    """The token is missing, malformed, expired, or not issued for this API."""


@dataclass(frozen=True)
class Identity:
    sub: str
    role: str
    email: str | None
    name: str | None
    department: str | None
    employee_name: str | None


def verify_token(token: str) -> dict:
    """Verify an Auth0 access token and return its claims."""
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],  # never accept "none" or HS256 here
            audience=settings.auth0_audience,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:  # includes PyJWKClientError
        raise InvalidToken(type(e).__name__) from e


def identity_from_claims(claims: dict) -> Identity | None:
    """Read our namespaced claims. Returns None if the role is missing/unknown."""

    def claim(name: str) -> str | None:
        value = claims.get(CLAIM_NAMESPACE + name)
        return value if isinstance(value, str) and value else None

    role = claim("role")
    if role not in ROLES:
        return None
    return Identity(
        sub=claims["sub"],
        role=role,
        email=claim("email"),
        name=claim("name"),
        department=claim("department"),
        employee_name=claim("employee_name"),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _upsert_user(session: AsyncSession, identity: Identity) -> User:
    now = utcnow()
    fields = {
        "email": identity.email,
        "display_name": identity.name,
        "role": identity.role,
        "department": identity.department,
        "employee_name": identity.employee_name,
        "last_seen_at": now,
    }
    # ON CONFLICT keeps this safe when a user's first requests arrive together.
    await session.execute(
        insert(User)
        .values(id=uuid.uuid4(), auth0_sub=identity.sub, created_at=now, **fields)
        .on_conflict_do_update(index_elements=[User.auth0_sub], set_=fields)
    )
    await session.commit()
    user = (
        await session.execute(
            select(User)
            .where(User.auth0_sub == identity.sub)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """FastAPI dependency: the authenticated user, or 401/403."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = verify_token(credentials.credentials)
    except InvalidToken:
        raise _unauthorized() from None

    identity = identity_from_claims(claims)
    if identity is None:
        # Valid token, but the tenant hasn't given this user a role.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No role assigned")

    return await _upsert_user(session, identity)


def require_role(*roles: str):
    """Dependency factory: allow only users whose role is in `roles`."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
