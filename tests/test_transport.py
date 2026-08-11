from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from urent_toolkit.transport import UrentTransport


class TransportProxyTest(unittest.TestCase):
    @patch("urent_toolkit.transport.httpx.Client")
    def test_http_proxy_is_applied_to_owned_client(self, client_class: Mock) -> None:
        UrentTransport(Mock(timeout=10), Mock(), Mock(), proxy="http://user:pass@proxy:8080")

        client_class.assert_called_once_with(
            timeout=10,
            follow_redirects=False,
            proxy="http://user:pass@proxy:8080",
        )

    @patch("urent_toolkit.transport.httpx.Client")
    def test_socks5_proxy_is_applied_to_owned_client(self, client_class: Mock) -> None:
        UrentTransport(Mock(timeout=10), Mock(), Mock(), proxy="socks5://proxy:1080")

        self.assertEqual(client_class.call_args.kwargs["proxy"], "socks5://proxy:1080")

    @patch("urent_toolkit.transport.httpx.Client")
    def test_injected_client_is_not_replaced(self, client_class: Mock) -> None:
        injected = Mock()
        transport = UrentTransport(Mock(), Mock(), Mock(), injected, proxy="socks5://proxy:1080")

        self.assertIs(transport.client, injected)
        client_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
