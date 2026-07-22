"""Bootstrap an API key from the command line.

Creates the user if needed (optionally as an admin) and prints a fresh API key.
Useful for seeding the first admin and for local testing without the Entra login
flow. The key is shown only once — store it somewhere safe.

Run from the server/ directory as a module so the `app` package resolves:
  uv run python -m scripts.create_key you@org.com
  uv run python -m scripts.create_key you@org.com --admin --label laptop
"""

import argparse
import secrets

from app.db import get_db, init_db, now
from app.keys import hash_key


def create_key(email: str, label: str, admin: bool) -> str:
    """Ensure the user exists and mint a new API key for them.

    Args:
        email: The user's email address.
        label: A human-readable label for the key.
        admin: Whether to mark the user as an admin.

    Returns:
        The plaintext API key (not stored; shown once).
    """
    raw = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (email, is_admin, created_at) VALUES (?, ?, ?)",
            (email, 1 if admin else 0, now()),
        )
        if admin:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.execute(
            "INSERT INTO api_keys (user_id, label, key_hash, prefix, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, label, hash_key(raw), raw[:8], now()),
        )
        conn.commit()
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an API key for a user.")
    parser.add_argument("email", help="the user's email address")
    parser.add_argument("--label", default="", help="a label for the key")
    parser.add_argument("--admin", action="store_true", help="mark the user as an admin")
    args = parser.parse_args()

    init_db()
    key = create_key(args.email, args.label, args.admin)
    print(f"user:  {args.email}{' (admin)' if args.admin else ''}")
    print(f"key:   {key}")
    print("\nStore this key now — it is not shown again.")


if __name__ == "__main__":
    main()
