from __future__ import annotations

import unittest

from urent_toolkit.auth import AuthenticationError, normalize_phone, set_callback_input


class AuthHelpersTest(unittest.TestCase):
    def test_normalizes_common_russian_phone_formats(self) -> None:
        self.assertEqual(normalize_phone("+7 (999) 000-00-00"), "79990000000")
        self.assertEqual(normalize_phone("8 999 000 00 00"), "79990000000")
        self.assertEqual(normalize_phone("9990000000"), "79990000000")

    def test_rejects_invalid_phone(self) -> None:
        with self.assertRaises(AuthenticationError):
            normalize_phone("123")

    def test_updates_forge_rock_callback(self) -> None:
        payload = {"callbacks": [{"input": [{"name": "IDToken1", "value": ""}]}]}
        self.assertTrue(set_callback_input(payload, "IDToken1", "1234"))
        self.assertEqual(payload["callbacks"][0]["input"][0]["value"], "1234")


if __name__ == "__main__":
    unittest.main()
