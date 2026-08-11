from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import httpx

from urent_toolkit.client import UrentClient


class UrentClientTest(unittest.TestCase):
    @patch("urent_toolkit.client.save_tokens")
    @patch("urent_toolkit.client.Authenticator")
    def test_login_can_return_tokens_without_persisting_them(
        self,
        authenticator_class: Mock,
        save_tokens: Mock,
    ) -> None:
        tokens = {"access_token": "access", "refresh_token": "refresh"}
        authenticator_class.return_value.login.return_value = tokens
        client = UrentClient(Mock(), Mock(), Mock())

        result = client.login("79990000000", Mock(), persist_tokens=False)

        self.assertEqual(result, tokens)
        self.assertEqual(client.tokens, tokens)
        save_tokens.assert_not_called()

    @patch("urent_toolkit.client.save_tokens")
    @patch("urent_toolkit.client.UrentTransport")
    def test_refresh_matches_the_android_app_form(
        self,
        transport_class: Mock,
        save_tokens: Mock,
    ) -> None:
        settings = SimpleNamespace(
            api_base="https://example.test/gatewayclient",
            client_id="mobile.client.android",
            client_secret="mobile-secret",
            token_scope="scope-a scope-b offline_access",
            token_file=Mock(),
        )
        original = {"access_token": "old-access", "refresh_token": "old-refresh"}
        refreshed = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        response = httpx.Response(200, json=refreshed)
        transport = transport_class.return_value.__enter__.return_value
        transport.request.return_value = response
        client = UrentClient(settings, Mock(), Mock(), original)

        result = client.refresh_tokens(persist_tokens=False, output=Mock())

        self.assertEqual(result, refreshed)
        save_tokens.assert_not_called()
        request = transport.request.call_args
        self.assertEqual(
            request.args[:2], ("POST", "https://example.test/gatewayclient/api/v1/connect/token")
        )
        form = parse_qs(request.kwargs["content"].decode("utf-8"))
        self.assertEqual(
            form,
            {
                "client_id": ["mobile.client.android"],
                "client_secret": ["mobile-secret"],
                "grant_type": ["refresh_token"],
                "scope": ["scope-a scope-b offline_access"],
                "refresh_token": ["old-refresh"],
            },
        )
        self.assertEqual(request.kwargs["access_token"], "old-access")


if __name__ == "__main__":
    unittest.main()
