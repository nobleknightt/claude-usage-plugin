"""Server configuration, read from environment variables.

Entra (Azure AD) app-registration values, the session-cookie secret, and the
admin allowlist all live here. See `.env.example` for the full list.
"""

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache


def _csv(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


@dataclass(slots=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str
    session_secret: str
    admin_emails: set[str]
    cors_origins: list[str]
    dev_login: bool

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

    def is_admin(self, email: str) -> bool:
        """Check whether an email is on the admin allowlist.

        Args:
            email: The Entra-verified email address to check.

        Returns:
            True if the email is listed in ``ADMIN_EMAILS``.
        """
        return email.strip().lower() in self.admin_emails


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
        admin_emails={e.lower() for e in _csv("ADMIN_EMAILS")},
        cors_origins=_csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000"),
        # Local-only shortcut to log in without Entra; never enable in production.
        dev_login=os.environ.get("DEV_LOGIN", "").strip().lower() in {"1", "true", "yes"},
    )
