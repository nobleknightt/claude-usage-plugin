"""API tests for the usage tracker server.

Uses the stdlib `unittest` runner with FastAPI's TestClient. Each test gets an
isolated temporary SQLite file, and the logged-in dashboard user is simulated by
overriding the `current_user` dependency (so we don't need a live Entra flow).

Run:  uv run python -m unittest
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app import auth, db, main


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db.DB = self.db_path  # point all get_db()/init_db() calls at the temp file
        db.init_db()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        os.unlink(self.db_path)

    # --- helpers -----------------------------------------------------------
    def login(self, user: dict, is_admin: bool = False) -> None:
        """Simulate a logged-in dashboard session for `user`."""
        main.app.dependency_overrides[auth.current_user] = lambda: {
            "id": user["id"],
            "email": user["email"],
            "is_admin": is_admin,
        }

    def make_key(self, user: dict, label: str = "") -> str:
        self.login(user)
        resp = self.client.post("/api/keys", json={"label": label})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["key"]

    @staticmethod
    def batch(event_id: str, email_account: str, **payload) -> dict:
        payload.setdefault("session_id", event_id)
        payload["account_email"] = email_account
        return {"events": [{"event_id": event_id, "event_type": "usage", "payload": payload}]}

    # --- tests -------------------------------------------------------------
    def test_health_is_open(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

    def test_spa_is_served_when_built(self) -> None:
        # Only runs once the client has been built (dist present); the server
        # mounts the SPA at import time when client/dist exists.
        if not main.CLIENT_DIST.is_dir():
            self.skipTest("client/dist not built")
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn('<div id="root"', root.text)
        # a client-side deep link falls back to index.html rather than 404ing
        self.assertEqual(self.client.get("/sessions").status_code, 200)

    def test_dashboard_endpoints_require_login(self) -> None:
        for path in ("/api/me", "/api/summary", "/api/sessions", "/api/keys"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_ingestion_requires_valid_key(self) -> None:
        # no Authorization header
        self.assertEqual(self.client.post("/api/usage", json={"session_id": "s"}).status_code, 401)
        self.assertEqual(
            self.client.post("/api/events/batch", json={"events": []}).status_code, 401
        )
        # garbage key
        bad = {"Authorization": "Bearer nope"}
        self.assertEqual(
            self.client.post("/api/events/batch", headers=bad, json={"events": []}).status_code,
            401,
        )

    def test_key_lifecycle_and_revocation(self) -> None:
        alice = auth._upsert_user("alice@example.com")
        key = self.make_key(alice, label="laptop")

        listed = self.client.get("/api/keys").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["status"], "active")
        self.assertEqual(listed[0]["label"], "laptop")
        key_id = listed[0]["id"]

        # key works for ingestion
        auth_hdr = {"Authorization": f"Bearer {key}"}
        r = self.client.post("/api/events/batch", headers=auth_hdr, json=self.batch("e1", "acct@x"))
        self.assertEqual(r.json(), {"accepted": 1, "duplicates": 0})

        # revoke, then the same key is rejected
        self.assertEqual(self.client.delete(f"/api/keys/{key_id}").status_code, 200)
        self.assertEqual(
            self.client.post("/api/events/batch", headers=auth_hdr, json=self.batch("e2", "acct@x")).status_code,
            401,
        )
        # revoking again -> 404
        self.assertEqual(self.client.delete(f"/api/keys/{key_id}").status_code, 404)

    def test_batch_is_idempotent_on_event_id(self) -> None:
        alice = auth._upsert_user("alice@example.com")
        key = self.make_key(alice)
        hdr = {"Authorization": f"Bearer {key}"}
        body = self.batch("dup-1", "acct@x", input_tokens=100, cost_usd=0.1)

        first = self.client.post("/api/events/batch", headers=hdr, json=body).json()
        second = self.client.post("/api/events/batch", headers=hdr, json=body).json()
        self.assertEqual(first, {"accepted": 1, "duplicates": 0})
        self.assertEqual(second, {"accepted": 0, "duplicates": 1})

        # counted exactly once
        self.login(alice)
        summary = self.client.get("/api/summary").json()
        self.assertEqual(summary[0]["input_tokens"], 100)

    def test_usage_daily_groups_by_day(self) -> None:
        alice = auth._upsert_user("alice@example.com")
        key = self.make_key(alice)
        hdr = {"Authorization": f"Bearer {key}"}
        # two events on the same day, different sessions
        self.client.post("/api/events/batch", headers=hdr, json={"events": [
            {"event_id": "d1", "payload": {"session_id": "s1", "timestamp": "2026-07-01T09:00:00+00:00", "input_tokens": 100, "output_tokens": 50}},
            {"event_id": "d2", "payload": {"session_id": "s2", "timestamp": "2026-07-01T15:00:00+00:00", "input_tokens": 200, "output_tokens": 20}},
        ]})

        self.login(alice)
        daily = self.client.get("/api/usage/daily").json()
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]["date"], "2026-07-01")
        # (100+50) + (200+20) = 370
        self.assertEqual(daily[0]["tokens"], 370)

    def test_identity_comes_from_the_key_not_the_payload(self) -> None:
        alice = auth._upsert_user("alice@example.com")
        key = self.make_key(alice)
        hdr = {"Authorization": f"Bearer {key}"}
        # payload tries to claim a different email; it must be ignored
        body = self.batch("e1", "acct@x", email="attacker@evil.com", input_tokens=5)
        self.client.post("/api/events/batch", headers=hdr, json=body)

        self.login(alice)
        rows = self.client.get("/api/summary").json()
        self.assertEqual([r["email"] for r in rows], ["alice@example.com"])

    def test_account_owner_sees_all_usage_on_their_account(self) -> None:
        # The Claude account is owned by team@example.com; alice and bob borrow it.
        owner = auth._upsert_user("team@example.com")
        alice = auth._upsert_user("alice@example.com")
        bob = auth._upsert_user("bob@example.com")

        for user, eid in ((alice, "a1"), (bob, "b1")):
            key = self.make_key(user)
            self.client.post(
                "/api/events/batch",
                headers={"Authorization": f"Bearer {key}"},
                json=self.batch(eid, "team@example.com", input_tokens=10),
            )

        # the owner (login email == account_email) sees everyone on the account
        self.login(owner)
        self.assertEqual(
            sorted(r["email"] for r in self.client.get("/api/summary").json()),
            ["alice@example.com", "bob@example.com"],
        )
        # a borrower (non-owner) sees only their own usage
        self.login(alice)
        self.assertEqual(
            [r["email"] for r in self.client.get("/api/summary").json()],
            ["alice@example.com"],
        )
        # an admin sees everyone
        self.login(alice, is_admin=True)
        self.assertEqual(
            sorted(r["email"] for r in self.client.get("/api/summary").json()),
            ["alice@example.com", "bob@example.com"],
        )

        # the owner can filter to a specific co-user on their account
        self.login(owner)
        self.assertEqual(
            [r["email"] for r in self.client.get("/api/summary?email=bob@example.com").json()],
            ["bob@example.com"],
        )
        # but filtering to a user outside the scope returns nothing
        self.login(alice)  # borrower
        self.assertEqual(self.client.get("/api/summary?email=bob@example.com").json(), [])


if __name__ == "__main__":
    unittest.main()
