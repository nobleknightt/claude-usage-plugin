"""Grant or revoke admin for a user, identified by email.

Admin is a per-user flag on the user record (not a config allowlist). The user
is created if they don't exist yet, so you can pre-provision an admin before
their first login. The flag takes effect the next time they log in (it is read
into their session then).

Run from the server/ directory as a module so the `app` package resolves:
  uv run python -m scripts.set_admin you@org.com
  uv run python -m scripts.set_admin you@org.com --revoke
"""

import argparse
from urllib.parse import quote

from app.db import get_db, now


def set_admin(email: str, is_admin: bool) -> None:
    """Set a user's admin flag, creating the user if they don't exist yet.

    Creating on demand lets you pre-provision an admin before their first login;
    when they later log in, the stored flag is read into their session.

    Args:
        email: The email identifying the user.
        is_admin: True to grant admin, False to revoke.
    """
    flag = 1 if is_admin else 0
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (email, is_admin, created_at) VALUES (?, ?, ?)",
            (email, flag, now()),
        )
        conn.execute("UPDATE users SET is_admin = ? WHERE email = ?", (flag, email))
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke admin for a user.")
    parser.add_argument("email", help="the user's email address")
    parser.add_argument("--revoke", action="store_true", help="revoke admin instead of granting")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8137",
        help="base URL for the dev-login link (default: %(default)s)",
    )
    args = parser.parse_args()

    granted = not args.revoke
    set_admin(args.email, granted)

    print(f"{args.email}: is_admin = {granted}")
    # The flag is read into the session at login, so a fresh login is needed.
    # In development, this dev-login link logs straight in as that user:
    url = f"{args.base_url}/api/auth/login?email={quote(args.email)}"
    print(f"Log in as them (ENVIRONMENT=development only): {url}")
    print("With real Entra login, they just sign out and back in.")


if __name__ == "__main__":
    main()
