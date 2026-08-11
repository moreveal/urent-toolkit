from __future__ import annotations

import unittest
from unittest.mock import Mock

import httpx

from urent_toolkit.auth import (
    AuthenticationError,
    Authenticator,
    auth_response_summary,
    normalize_phone,
    redact_diagnostic_text,
    select_callback_option,
    set_callback_input,
)


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

    def test_auth_summary_includes_safe_callback_error(self) -> None:
        payload = {
            "authId": "secret-auth-id",
            "callbacks": [
                {
                    "type": "TextOutputCallback",
                    "output": [
                        {"name": "message", "value": "Wrong code 1234 for 79990000000"},
                        {"name": "prompt", "value": "Choose account 79990000000"},
                        {"name": "choices", "value": ["Continue", "Use 79990000000"]},
                        {"name": "defaultChoice", "value": 0},
                        {"name": "token", "value": "must-not-appear"},
                    ],
                }
            ],
        }
        summary = auth_response_summary(payload)
        self.assertIn("TextOutputCallback", summary)
        self.assertIn("Wrong code <digits> for <digits>", summary)
        self.assertIn("prompt=Choose account <digits>", summary)
        self.assertIn("choices=['Continue', 'Use <digits>']", summary)
        self.assertIn("defaultChoice=0", summary)
        self.assertNotIn("secret-auth-id", summary)
        self.assertNotIn("must-not-appear", summary)

    def test_diagnostic_text_redacts_long_digit_sequences(self) -> None:
        self.assertEqual(redact_diagnostic_text("phone 79990000000"), "phone <digits>")

    def test_selects_callback_option_by_name_not_position(self) -> None:
        payload = {
            "callbacks": [
                {
                    "type": "ChoiceCallback",
                    "output": [
                        {"name": "choices", "value": ["PASSWORD+SMS", "SMS"]},
                    ],
                    "input": [{"name": "IDToken1", "value": 0}],
                },
                {
                    "type": "ConfirmationCallback",
                    "output": [
                        {"name": "options", "value": ["IGNORE", "OK", "RESTART"]},
                    ],
                    "input": [{"name": "IDToken2", "value": 0}],
                },
            ]
        }
        self.assertTrue(select_callback_option(payload, "ChoiceCallback", "choices", "SMS"))
        self.assertTrue(select_callback_option(payload, "ConfirmationCallback", "options", "OK"))
        self.assertEqual(payload["callbacks"][0]["input"][0]["value"], 1)
        self.assertEqual(payload["callbacks"][1]["input"][0]["value"], 1)

    def test_does_not_guess_unknown_callback_option(self) -> None:
        payload = {
            "callbacks": [
                {
                    "type": "ChoiceCallback",
                    "output": [{"name": "choices", "value": ["PASSWORD"]}],
                    "input": [{"name": "IDToken1", "value": 0}],
                }
            ]
        }
        self.assertFalse(select_callback_option(payload, "ChoiceCallback", "choices", "SMS"))

    def test_raw_exchange_contains_actual_request_and_response(self) -> None:
        captured: list[tuple[str, dict[str, object]]] = []
        authenticator = Authenticator(
            Mock(),
            Mock(),
            Mock(),
            raw_output=lambda stage, payload: captured.append((stage, payload)),
        )
        request = httpx.Request(
            "POST",
            "https://example.test/auth?phone=79990000000",
            headers={"Authorization": "Bearer secret"},
            content=b'{"otp":"1234"}',
        )
        response = httpx.Response(
            200,
            request=request,
            headers={"Set-Cookie": "session=secret"},
            content=b'{"access_token":"secret"}',
        )

        authenticator._emit_raw_exchange("test_http", response)

        self.assertEqual(captured[0][0], "test_http")
        exchange = captured[0][1]
        self.assertEqual(exchange["request"]["body"], '{"otp":"1234"}')
        self.assertEqual(exchange["response"]["body"], '{"access_token":"secret"}')


if __name__ == "__main__":
    unittest.main()
