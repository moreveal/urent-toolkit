from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from urent_test_bot.main import (
    LoginSession,
    configure_logging,
    normalize_phone_input,
    parse_allowed_user_ids,
    redact_error_text,
    token_document,
)


class TelegramBotHelpersTest(unittest.TestCase):
    def test_parses_allowlist(self) -> None:
        self.assertEqual(parse_allowed_user_ids("123, 456"), frozenset({123, 456}))

    def test_rejects_empty_allowlist(self) -> None:
        with self.assertRaises(ValueError):
            parse_allowed_user_ids("")

    def test_normalizes_phone(self) -> None:
        self.assertEqual(normalize_phone_input("8 (999) 000-00-00"), "79990000000")

    def test_builds_json_document_in_memory(self) -> None:
        document = token_document({"access_token": "secret", "expires_in": 60})
        self.assertEqual(document.name, "tokens.json")
        self.assertEqual(json.load(document), {"access_token": "secret", "expires_in": 60})

    def test_session_accepts_one_otp(self) -> None:
        session = LoginSession()
        session.provide_otp("1234")
        self.assertEqual(session.wait_for_otp(), "1234")

    def test_error_logging_redacts_query_phone_and_secret(self) -> None:
        value = (
            "request https://example.test/auth?phone=79990000000 token abcdefghijklmnopqrstuvwxyz"
        )
        redacted = redact_error_text(value)
        self.assertEqual(
            redacted,
            "request https://example.test/auth?<redacted> token <secret>",
        )

    def test_configures_rotating_file_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = configure_logging(Path(directory))
            logger.info("diagnostic-marker")
            for handler in logger.handlers:
                handler.flush()
            log_text = (Path(directory) / "logs" / "bot.log").read_text(encoding="utf-8")
            self.assertIn("diagnostic-marker", log_text)
            for handler in logger.handlers:
                handler.close()
            logger.handlers.clear()
            logging.shutdown()


if __name__ == "__main__":
    unittest.main()
