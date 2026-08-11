from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from urent_toolkit.storage import (
    deserialize_tokens,
    load_tokens,
    save_tokens,
    serialize_tokens,
    token_document,
    tokens_are_valid,
)


class TokenStorageTest(unittest.TestCase):
    def test_serialization_round_trip_preserves_tokens_and_expiration(self) -> None:
        now = datetime(2026, 8, 11, tzinfo=UTC)
        document = token_document(
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 1800},
            now=now,
        )

        restored = deserialize_tokens(serialize_tokens(document))

        self.assertEqual(restored, document)
        self.assertEqual(restored["expires_at"], "2026-08-11T00:30:00+00:00")

    def test_validity_honors_expiration_and_leeway(self) -> None:
        now = datetime(2026, 8, 11, tzinfo=UTC)
        tokens = {
            "access_token": "access",
            "expires_at": (now + timedelta(seconds=60)).isoformat(),
        }
        self.assertTrue(tokens_are_valid(tokens, now=now, leeway=30))
        self.assertFalse(tokens_are_valid(tokens, now=now, leeway=60))

    def test_save_creates_parent_and_loads_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "session.json"
            saved = save_tokens(path, {"access_token": "access", "expires_in": 60})

            self.assertEqual(load_tokens(path), saved)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)


if __name__ == "__main__":
    unittest.main()
