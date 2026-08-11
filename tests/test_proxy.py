from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from urent_toolkit.errors import ConfigurationError
from urent_toolkit.proxy import ProxyPool, validate_proxy


class ProxyPoolTest(unittest.TestCase):
    def test_rotates_and_persists_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proxy.txt"
            path.write_text(
                "# proxies\nhttp://one.test:8080\n\nsocks5://two.test:1080\n",
                encoding="utf-8",
            )

            self.assertEqual(ProxyPool(path).acquire(), "http://one.test:8080")
            self.assertEqual(ProxyPool(path).acquire(), "socks5://two.test:1080")
            self.assertEqual(ProxyPool(path).acquire(), "http://one.test:8080")

    def test_rejects_unsupported_scheme(self) -> None:
        with self.assertRaises(ConfigurationError):
            validate_proxy("ftp://proxy.test:21")

    def test_empty_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proxy.txt"
            path.write_text("# empty\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                ProxyPool(path).acquire()


if __name__ == "__main__":
    unittest.main()
