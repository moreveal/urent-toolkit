from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from urent_toolkit.cli import build_parser, main, prompt_token_document


class CliTest(unittest.TestCase):
    def test_parses_refresh_options(self) -> None:
        args = build_parser().parse_args(
            [
                "refresh",
                "--refresh-token",
                "refresh-value",
                "--access-token",
                "access-value",
            ]
        )
        self.assertEqual(args.command, "refresh")
        self.assertEqual(args.refresh_token, "refresh-value")
        self.assertEqual(args.access_token, "access-value")

    @patch("urent_toolkit.cli.UrentClient")
    @patch("builtins.print")
    def test_refresh_prints_json_without_persisting(
        self,
        print_mock: Mock,
        client_class: Mock,
    ) -> None:
        client = client_class.from_env.return_value
        tokens = {"access_token": "new-access", "refresh_token": "new-refresh"}
        client.refresh_tokens.return_value = tokens

        result = main(
            [
                "refresh",
                "--refresh-token",
                "old-refresh",
                "--access-token",
                "old-access",
            ]
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            client.tokens,
            {"refresh_token": "old-refresh", "access_token": "old-access"},
        )
        client.refresh_tokens.assert_called_once_with(
            token_file=None,
            persist_tokens=False,
            output=unittest.mock.ANY,
        )
        printed = print_mock.call_args.args[0]
        self.assertEqual(json.loads(printed), tokens)

    @patch("urent_toolkit.cli.UrentClient")
    @patch("builtins.print")
    def test_refresh_reads_and_writes_token_files(
        self,
        print_mock: Mock,
        client_class: Mock,
    ) -> None:
        del print_mock
        client = client_class.from_env.return_value
        client.refresh_tokens.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tokens.json"
            target = Path(directory) / "refreshed.json"
            source.write_text(
                json.dumps({"access_token": "old-access", "refresh_token": "old-refresh"}),
                encoding="utf-8",
            )

            result = main(
                [
                    "refresh",
                    "--token-file",
                    str(source),
                    "--output-file",
                    str(target),
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            client.tokens,
            {"refresh_token": "old-refresh", "access_token": "old-access"},
        )
        client.refresh_tokens.assert_called_once_with(
            token_file=target,
            persist_tokens=True,
            output=unittest.mock.ANY,
        )

    @patch("builtins.input")
    @patch("builtins.print")
    def test_reads_pretty_printed_token_json(
        self,
        print_mock: Mock,
        input_mock: Mock,
    ) -> None:
        del print_mock
        input_mock.side_effect = [
            "{",
            '  "access_token": "access",',
            '  "refresh_token": "refresh"',
            "}",
        ]

        result = prompt_token_document()

        self.assertEqual(
            result,
            {"access_token": "access", "refresh_token": "refresh"},
        )

    @patch("urent_toolkit.cli.UrentClient")
    @patch("builtins.print")
    def test_filepath_reads_and_updates_the_same_file(
        self,
        print_mock: Mock,
        client_class: Mock,
    ) -> None:
        del print_mock
        client = client_class.from_env.return_value
        client.refresh_tokens.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokens.json"
            path.write_text(
                json.dumps({"access_token": "old-access", "refresh_token": "old-refresh"}),
                encoding="utf-8",
            )

            result = main(["refresh", "--filepath", str(path)])

        self.assertEqual(result, 0)
        client.refresh_tokens.assert_called_once_with(
            token_file=path,
            persist_tokens=True,
            output=unittest.mock.ANY,
        )


if __name__ == "__main__":
    unittest.main()
