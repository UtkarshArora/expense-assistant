"""
Tests for Auth0 token verification and route protection.

Tokens are signed in-test with a throwaway RSA key and the JWKS lookup is
monkeypatched, so nothing touches the network, Auth0, or a database.
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.auth import (
    CLAIM_NAMESPACE,
    ISSUER,
    InvalidToken,
    get_current_user,
    identity_from_claims,
    require_role,
    verify_token,
)
from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Conversation, User

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(
    *,
    key=KEY,
    algorithm="RS256",
    role: str | None = "employee",
    drop: tuple[str, ...] = (),
    **overrides,
) -> str:
    now = int(time.time())
    claims = {
        "sub": "auth0|marcus",
        "iss": ISSUER,
        "aud": settings.auth0_audience,
        "iat": now,
        "exp": now + 600,
        CLAIM_NAMESPACE + "email": "marcus.demo@example.com",
        CLAIM_NAMESPACE + "name": "Marcus Chen",
        CLAIM_NAMESPACE + "department": "Sales",
        CLAIM_NAMESPACE + "employee_name": "Marcus Chen",
    }
    if role is not None:
        claims[CLAIM_NAMESPACE + "role"] = role
    claims.update(overrides)
    for name in drop:
        claims.pop(name)
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": "test-kid"})


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch):
    """The JWKS lookup always returns the public half of KEY."""
    lookup = MagicMock(return_value=SimpleNamespace(key=KEY.public_key()))
    monkeypatch.setattr(auth._jwks_client, "get_signing_key_from_jwt", lookup)
    return lookup


@pytest.fixture
def client():
    # No `with`: the lifespan (which connects to Postgres) never runs.
    yield TestClient(app)
    app.dependency_overrides.clear()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------------
# verify_token
# ----------------------------------------------------------------------

def test_valid_token_returns_claims():
    claims = verify_token(make_token())
    assert claims["sub"] == "auth0|marcus"
    assert claims[CLAIM_NAMESPACE + "role"] == "employee"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(make_token(exp=int(time.time()) - 60), id="expired"),
        pytest.param(make_token(aud="https://some-other-api"), id="wrong-audience"),
        pytest.param(make_token(iss="https://evil.auth0.com/"), id="wrong-issuer"),
        pytest.param(make_token(key=OTHER_KEY), id="bad-signature"),
        pytest.param(make_token(drop=("sub",)), id="missing-sub"),
        pytest.param(make_token(drop=("exp",)), id="missing-exp"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_invalid_tokens_are_rejected(token):
    with pytest.raises(InvalidToken):
        verify_token(token)


def test_hs256_token_is_rejected():
    # Algorithm confusion: a token "signed" with a shared secret must never
    # verify, even though the server only holds public keys.
    token = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": settings.auth0_audience,
         "iat": int(time.time()), "exp": int(time.time()) + 600},
        "a-shared-secret-of-sufficient-length-for-hmac",
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        verify_token(token)


def test_jwks_failure_is_an_invalid_token(fake_jwks):
    fake_jwks.side_effect = jwt.PyJWKClientError("Unable to find a signing key")
    with pytest.raises(InvalidToken):
        verify_token(make_token())


# ----------------------------------------------------------------------
# identity_from_claims
# ----------------------------------------------------------------------

def test_identity_reads_namespaced_claims():
    identity = identity_from_claims(verify_token(make_token(role="manager")))
    assert identity is not None
    assert (identity.sub, identity.role, identity.department, identity.employee_name) == (
        "auth0|marcus", "manager", "Sales", "Marcus Chen",
    )


@pytest.mark.parametrize("role", [None, "", "superuser", "Admin"])
def test_missing_or_unknown_role_has_no_identity(role):
    claims = {"sub": "auth0|x"}
    if role is not None:
        claims[CLAIM_NAMESPACE + "role"] = role
    assert identity_from_claims(claims) is None


def test_non_string_claims_are_ignored():
    claims = {
        "sub": "auth0|x",
        CLAIM_NAMESPACE + "role": "admin",
        CLAIM_NAMESPACE + "department": ["Sales", "Engineering"],
    }
    identity = identity_from_claims(claims)
    assert identity is not None and identity.department is None


# ----------------------------------------------------------------------
# Route protection
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/me"),
        ("get", "/conversations"),
        ("get", f"/conversations/{uuid.uuid4()}"),
        ("post", "/chat"),
    ],
)
def test_protected_routes_require_a_token(client, method, path):
    kwargs = {"json": {"message": "hi"}} if method == "post" else {}
    res = getattr(client, method)(path, **kwargs)
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_401(client):
    res = client.get("/me", headers=bearer(make_token(key=OTHER_KEY)))
    assert res.status_code == 401


def test_valid_token_without_role_is_403(client):
    res = client.get("/me", headers=bearer(make_token(role=None)))
    assert res.status_code == 403


def test_valid_token_returns_me(client, monkeypatch):
    seen = {}

    async def fake_upsert(session, identity):
        seen["identity"] = identity
        return User(id=uuid.uuid4(), auth0_sub=identity.sub, role=identity.role,
                    display_name=identity.name, department=identity.department,
                    employee_name=identity.employee_name, email=identity.email)

    monkeypatch.setattr(auth, "_upsert_user", fake_upsert)
    res = client.get("/me", headers=bearer(make_token()))

    assert res.status_code == 200
    assert res.json()["role"] == "employee"
    assert res.json()["employee_name"] == "Marcus Chen"
    assert seen["identity"].sub == "auth0|marcus"


# ----------------------------------------------------------------------
# Ownership and limits (dependency overrides; no database)
# ----------------------------------------------------------------------

MARCUS = User(id=uuid.uuid4(), auth0_sub="auth0|marcus", role="employee")
PRIYA = User(id=uuid.uuid4(), auth0_sub="auth0|priya", role="manager")


class FakeSession:
    def __init__(self, conversation=None, sent_today=0):
        self.conversation = conversation
        self.sent_today = sent_today

    async def get(self, model, key):
        return self.conversation

    async def scalar(self, stmt):
        return self.sent_today

    async def execute(self, stmt):
        return MagicMock()


def as_user(user, session):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session


def test_other_users_conversation_is_404(client):
    convo = Conversation(id=uuid.uuid4(), user_id=MARCUS.id, title="Marcus's chat")
    as_user(PRIYA, FakeSession(conversation=convo))

    res = client.get(f"/conversations/{convo.id}")

    assert res.status_code == 404


def test_cannot_post_into_other_users_conversation(client, monkeypatch):
    run_agent = MagicMock()
    monkeypatch.setattr("app.routers.chat.run_agent", run_agent)
    convo = Conversation(id=uuid.uuid4(), user_id=MARCUS.id, title="Marcus's chat")
    as_user(PRIYA, FakeSession(conversation=convo))

    res = client.post("/chat", json={"message": "hi", "conversation_id": str(convo.id)})

    assert res.status_code == 404
    run_agent.assert_not_called()


def test_daily_limit_returns_429_before_calling_the_model(client, monkeypatch):
    run_agent = MagicMock()
    monkeypatch.setattr("app.routers.chat.run_agent", run_agent)
    as_user(MARCUS, FakeSession(sent_today=settings.daily_message_limit))

    res = client.post("/chat", json={"message": "hi"})

    assert res.status_code == 429
    run_agent.assert_not_called()


# ----------------------------------------------------------------------
# require_role
# ----------------------------------------------------------------------

def test_require_role():
    mini = FastAPI()

    @mini.get("/admin-only")
    async def admin_only(user: User = Depends(require_role("admin"))):
        return {"ok": True}

    mini.dependency_overrides[get_current_user] = lambda: MARCUS
    assert TestClient(mini).get("/admin-only").status_code == 403

    mini.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), auth0_sub="auth0|finance", role="admin"
    )
    assert TestClient(mini).get("/admin-only").status_code == 200
