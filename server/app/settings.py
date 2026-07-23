"""Server configuration, read from environment variables.

Entra (Azure AD) app-registration values and the session-cookie secret live
here. See `.env.example` for the full list. Admin status is not configured here
— it is a per-user flag stored on the user record (see scripts/set_admin.py).
"""

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

Environment = Literal["development", "production"]


def _csv(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


def _environment() -> Environment:
    """Read ENVIRONMENT, falling back to production for anything unrecognized."""
    return "development" if os.environ.get("ENVIRONMENT", "").strip().lower() == "development" else "production"


@dataclass(slots=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str
    session_secret: str
    cors_origins: list[str]
    environment: Environment

    @property
    def is_development(self) -> bool:
        """Whether the server is running in development mode.

        Development-only conveniences (e.g. the dev-login shortcut) are enabled
        only when this is true. Defaults to production.
        """
        return self.environment == "development"

    @property
    def auth_configured(self) -> bool:
        """Whether the Entra app-registration values are all present.

        Returns:
            True if tenant, client id, and client secret are set.
        """
        return bool(self.tenant_id and self.client_id and self.client_secret)

    @property
    def oidc_metadata_url(self) -> str:
        """Return the Entra OpenID Connect discovery document URL.

        Returns:
            The tenant-specific ``.well-known/openid-configuration`` URL.
        """
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}"
            "/v2.0/.well-known/openid-configuration"
        )


@lru_cache
def get_settings() -> Settings:
    """Load settings from the environment (cached for the process lifetime).

    Returns:
        The populated :class:`Settings` instance.
    """
    return Settings(
        tenant_id=os.environ.get("ENTRA_TENANT_ID", "").strip(),
        client_id=os.environ.get("ENTRA_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("ENTRA_CLIENT_SECRET", "").strip(),
        redirect_uri=os.environ.get(
            "ENTRA_REDIRECT_URI", "http://localhost:8000/api/auth/microsoft/callback"
        ).strip(),
        frontend_url=os.environ.get("FRONTEND_URL", "/").strip(),
        # A generated fallback keeps dev working, but rotates on restart (all
        # sessions drop). Set SESSION_SECRET in production for stable sessions.
        session_secret=os.environ.get("SESSION_SECRET", "").strip() or secrets.token_hex(32),
        cors_origins=_csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000"),
        # Defaults to production; set ENVIRONMENT=development to enable dev-only
        # conveniences such as the /api/auth/login shortcut.
        environment=_environment(),
    )
