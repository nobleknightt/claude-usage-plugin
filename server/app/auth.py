"""Dashboard authentication via OIDC (Microsoft Entra ID and/or Google).

Flow: the SPA sends the browser to `/api/auth/<provider>/login`, we redirect to
the provider, and it calls back to `/api/auth/<provider>/callback` with an
authorization code. We exchange it for an id_token, upsert the user (email from
the verified token), and store a signed session cookie. Users are keyed by
email, so the same address works across providers. `current_user` reads that
cookie for dashboard endpoints; API-key auth for the hook lives in `keys.py`.
"""

import logging
import time

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy import text
from starlette.responses import RedirectResponse

from .db import get_db, now
from .settings import get_settings

logger = logging.getLogger("usage-tracker.auth")
settings = get_settings()

# The logged-in user is carried as a signed JWT stored inside the session cookie
# (the cookie itself is signed by SessionMiddleware). Signed with the same
# session secret; HS256 is fine since we both issue and verify it.
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 8 * 60 * 60  # 8 hours
_claims_registry = JWTClaimsRegistry()  # validates exp / iat when present


def _jwt_key() -> OctKey:
    """Build the symmetric key used to sign and verify session JWTs.

    Returns:
        An HMAC key derived from the configured session secret.
    """
    return OctKey.import_key(settings.session_secret)

oauth = OAuth()
if settings.entra_configured:
    oauth.register(
        name="entra",
        server_metadata_url=settings.entra_metadata_url,
        client_id=settings.entra_client_id,
        client_secret=settings.entra_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )
if settings.google_configured:
    oauth.register(
        name="google",
        server_metadata_url=settings.google_metadata_url,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )

router = APIRouter(prefix="/api")


def _upsert_user(email: str, name: str = "") -> dict:
    """Insert the user if new, refresh their display name, then return them.

    Email is the user's identity; name is the Entra display-name claim (kept in
    sync on each login). Admin is a stored per-user flag: new users default to
    non-admin, and an existing user's flag is left untouched (grant it with
    scripts/set_admin.py).

    Args:
        email: The Entra-verified email address identifying the user.
        name: The user's display name from the Entra ``name`` claim.

    Returns:
        The user as a dict with ``id``, ``email``, ``name``, and ``is_admin``.
    """
    with get_db() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        ).first()
        if not existing:
            conn.execute(
                text(
                    "INSERT INTO users (email, name, is_admin, created_at) "
                    "VALUES (:email, :name, 0, :created_at)"
                ),
                {"email": email, "name": name, "created_at": now()},
            )
        elif name:
            conn.execute(
                text("UPDATE users SET name = :name WHERE email = :email"),
                {"name": name, "email": email},
            )
        conn.commit()
        row = conn.execute(
            text("SELECT id, email, name, is_admin FROM users WHERE email = :email"),
            {"email": email},
        ).mappings().fetchone()
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "is_admin": bool(row["is_admin"]),
    }


def _mint_token(user: dict) -> str:
    """Encode a user into a short-lived signed JWT.

    Args:
        user: A dict with ``id``, ``email``, and ``is_admin`` keys.

    Returns:
        A signed compact JWT string carrying the user claims and an expiry.
    """
    issued = int(time.time())
    claims = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "is_admin": user["is_admin"],
        "iat": issued,
        "exp": issued + JWT_TTL_SECONDS,
    }
    return jwt.encode({"alg": JWT_ALG}, claims, _jwt_key())


def current_user(request: Request) -> dict:
    """Resolve the logged-in dashboard user from the session cookie.

    Reads the JWT stored in the session and verifies its signature and expiry.

    Args:
        request: The incoming request carrying the session cookie.

    Returns:
        The user as a dict with ``id``, ``email``, and ``is_admin`` keys.

    Raises:
        HTTPException: 401 if no valid, unexpired session token is present.
    """
    token = request.session.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        decoded = jwt.decode(token, _jwt_key())
        _claims_registry.validate(decoded.claims)  # enforces exp / iat
    except (JoseError, ValueError) as e:
        raise HTTPException(status_code=401, detail="invalid or expired session") from e
    claims = decoded.claims
    return {
        "id": int(claims["sub"]),
        "email": claims["email"],
        "name": claims.get("name", ""),
        "is_admin": bool(claims["is_admin"]),
    }


def _complete_login(request: Request, claims: dict, verify_email: bool = False):
    """Turn verified OIDC claims into a session and redirect to the dashboard.

    Shared by every provider: identity is the verified email (users are keyed by
    it, so signing in with either provider under the same address lands on the
    same account), and only ``email`` + ``name`` are kept — the common fields
    both providers return.

    Args:
        request: The request whose session will carry the minted token.
        claims: The provider's ``userinfo`` claims.
        verify_email: If true, reject a claim whose ``email_verified`` is false
            (Google can assert an unverified address; Entra tenant emails are
            trusted).

    Returns:
        A redirect to the configured frontend URL.

    Raises:
        HTTPException: 401 if there is no email claim, or it is unverified.
    """
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="no email claim in token")
    if verify_email and claims.get("email_verified") is False:
        raise HTTPException(status_code=401, detail="email is not verified")

    name = (claims.get("name") or "").strip()
    request.session["token"] = _mint_token(_upsert_user(email, name))
    return RedirectResponse(url=settings.frontend_url)


@router.get("/auth/providers", summary="Which login providers are enabled")
def providers() -> dict:
    """Report which OIDC providers are configured, so the UI shows only those."""
    return {"microsoft": settings.entra_configured, "google": settings.google_configured}


@router.get("/auth/microsoft/login", summary="Start the Entra login flow")
async def entra_login(request: Request):
    if not settings.entra_configured:
        raise HTTPException(status_code=503, detail="Microsoft login is not configured")
    return await oauth.entra.authorize_redirect(request, settings.entra_redirect_uri)


@router.get("/auth/microsoft/callback", summary="Entra OIDC redirect target")
async def entra_callback(request: Request):
    if not settings.entra_configured:
        raise HTTPException(status_code=503, detail="Microsoft login is not configured")
    try:
        token = await oauth.entra.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("entra callback: OAuth error: %s", e)
        raise HTTPException(status_code=401, detail="login failed") from e
    return _complete_login(request, token.get("userinfo") or {})


@router.get("/auth/google/login", summary="Start the Google login flow")
async def google_login(request: Request):
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/auth/google/callback", summary="Google OIDC redirect target")
async def google_callback(request: Request):
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("google callback: OAuth error: %s", e)
        raise HTTPException(status_code=401, detail="login failed") from e
    return _complete_login(request, token.get("userinfo") or {}, verify_email=True)


@router.get("/auth/login", summary="Log in without Entra ID (development only)")
async def dev_login(request: Request, email: str = "dev@local"):
    """Log in as ``email`` without Entra, for local development only.

    Enabled only when ``ENVIRONMENT=development``; returns 404 otherwise so it is
    invisible in production.

    Args:
        request: The incoming request whose session will be populated.
        email: The email to log in as (defaults to ``dev@local``).

    Returns:
        A redirect to the frontend once the session is set.

    Raises:
        HTTPException: 404 when not running in development.
    """
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="not found")
    request.session["token"] = _mint_token(_upsert_user(email.strip().lower()))
    return RedirectResponse(url=settings.frontend_url)


@router.post("/auth/logout", summary="Clear the session")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me", summary="Current user + role")
def me(request: Request) -> dict:
    return current_user(request)
