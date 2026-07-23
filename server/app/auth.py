"""Dashboard authentication via Microsoft Entra ID (OIDC).

Flow: the SPA sends the browser to `/api/auth/login`, we redirect to Entra, and
Entra calls back to `/api/auth/callback` with an authorization code. We exchange
it for an id_token, upsert the user (email from the verified token), and store a
signed session cookie. `current_user` reads that cookie for dashboard endpoints;
API-key auth for the hook lives in `keys.py`.
"""

import logging
import time

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry
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
if settings.auth_configured:
    oauth.register(
        name="entra",
        server_metadata_url=settings.oidc_metadata_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
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
        conn.execute(
            "INSERT OR IGNORE INTO users (email, name, is_admin, created_at) VALUES (?, ?, 0, ?)",
            (email, name, now()),
        )
        if name:
            conn.execute("UPDATE users SET name = ? WHERE email = ?", (name, email))
        conn.commit()
        row = conn.execute(
            "SELECT id, email, name, is_admin FROM users WHERE email = ?", (email,)
        ).fetchone()
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


@router.get("/auth/microsoft/login", summary="Start the Entra login flow")
async def login(request: Request):
    if not settings.auth_configured:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    return await oauth.entra.authorize_redirect(request, settings.redirect_uri)


@router.get("/auth/microsoft/callback", summary="Entra OIDC redirect target")
async def callback(request: Request):
    if not settings.auth_configured:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    try:
        token = await oauth.entra.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("callback: OAuth error: %s", e)
        raise HTTPException(status_code=401, detail="login failed") from e

    claims = token.get("userinfo") or {}
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="no email claim in token")

    name = (claims.get("name") or "").strip()
    request.session["token"] = _mint_token(_upsert_user(email, name))
    return RedirectResponse(url=settings.frontend_url)


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
