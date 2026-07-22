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
        alice = auth._upsert_user("alice@org.com")
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
        alice = auth._upsert_user("alice@org.com")
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

    def test_identity_comes_from_the_key_not_the_payload(self) -> None:
        alice = auth._upsert_user("alice@org.com")
        key = self.make_key(alice)
        hdr = {"Authorization": f"Bearer {key}"}
        # payload tries to claim a different email; it must be ignored
        body = self.batch("e1", "acct@x", email="attacker@evil.com", input_tokens=5)
        self.client.post("/api/events/batch", headers=hdr, json=body)

        self.login(alice)
        rows = self.client.get("/api/summary").json()
        self.assertEqual([r["email"] for r in rows], ["alice@org.com"])

    def test_member_visibility_covers_shared_account_co_users(self) -> None:
        alice = auth._upsert_user("alice@org.com")
        bob = auth._upsert_user("bob@org.com")
        carol = auth._upsert_user("carol@org.com")

        # alice + bob share account "acme"; carol is on "other"
        for user, acct, eid in ((alice, "acme@shared", "a1"), (bob, "acme@shared", "b1"), (carol, "other@shared", "c1")):
            key = self.make_key(user)
            self.client.post(
                "/api/events/batch",
                headers={"Authorization": f"Bearer {key}"},
                json=self.batch(eid, acct, input_tokens=10),
            )

        # alice (member) sees herself + bob, but not carol
        self.login(alice)
        self.assertEqual(
            sorted(r["email"] for r in self.client.get("/api/summary").json()),
            ["alice@org.com", "bob@org.com"],
        )
        # carol sees only herself
        self.login(carol)
        self.assertEqual(
            [r["email"] for r in self.client.get("/api/summary").json()],
            ["carol@org.com"],
        )
        # an admin sees everyone
        self.login(alice, is_admin=True)
        self.assertEqual(
            sorted(r["email"] for r in self.client.get("/api/summary").json()),
            ["alice@org.com", "bob@org.com", "carol@org.com"],
        )


if __name__ == "__main__":
    unittest.main()
