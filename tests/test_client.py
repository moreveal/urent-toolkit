from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import httpx

from urent_toolkit.client import UrentClient


class UrentClientTest(unittest.TestCase):
    @patch("urent_toolkit.client.create_persona", return_value=(Mock(), Mock()))
    @patch("urent_toolkit.client.ProxyPool")
    @patch("urent_toolkit.client.Settings.from_env")
    def test_from_env_leases_one_proxy_for_the_session(
        self,
        settings_from_env: Mock,
        proxy_pool: Mock,
        _create_persona: Mock,
    ) -> None:
        proxy_file = Mock()
        settings_from_env.return_value = SimpleNamespace(
            android_profile=None,
            profile_file=None,
            proxy_file=proxy_file,
        )
        proxy_pool.return_value.acquire.return_value = "socks5://proxy.test:1080"

        client = UrentClient.from_env()

        self.assertEqual(client.proxy, "socks5://proxy.test:1080")
        proxy_pool.assert_called_once_with(proxy_file)
        proxy_pool.return_value.acquire.assert_called_once_with()

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

    def test_create_card_binding_url_uses_observed_urent_endpoint(self) -> None:
        client = UrentClient(Mock(), Mock(), Mock(), {"access_token": "access"})
        client.ensure_valid_session = Mock(return_value=True)
        client.request = Mock(
            return_value=httpx.Response(
                200,
                json={"confirmationUrl": "https://yoomoney.ru/checkout/example"},
            )
        )
        token_file = Mock()

        result = client.create_card_binding_url(token_file=token_file)

        self.assertEqual(result, "https://yoomoney.ru/checkout/example")
        client.ensure_valid_session.assert_called_once_with(
            auto_refresh=True,
            token_file=token_file,
        )
        client.request.assert_called_once_with(
            "POST",
            "/api/v1/yookassa/addcard/webview",
            params={"cardPayType": "bank_card"},
        )

    def test_create_card_binding_url_rejects_missing_url(self) -> None:
        client = UrentClient(Mock(), Mock(), Mock(), {"access_token": "access"})
        client.ensure_valid_session = Mock(return_value=True)
        client.request = Mock(return_value=httpx.Response(200, json={}))

        with self.assertRaisesRegex(RuntimeError, "no confirmationUrl"):
            client.create_card_binding_url()


if __name__ == "__main__":
    unittest.main()
