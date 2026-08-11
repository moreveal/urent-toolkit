from __future__ import annotations

import unittest

from urent_toolkit.signing import request_signature, signing_key


class SigningTest(unittest.TestCase):
    def test_key_has_hmac_sha256_block_size(self) -> None:
        self.assertEqual(len(signing_key("mobile.client.android")), 64)

    def test_signature_is_stable(self) -> None:
        headers = {
            "UR-Client-Id": "mobile.client.android",
            "UR-Device-Id": "0123456789abcdef",
            "UR-Platform": "Android",
            "UR-Request-Version": "v2",
        }
        value = request_signature(
            b'{"hello":"world"}',
            headers,
            "https://example.test/api?b=2&a=1",
            "mobile.client.android",
        )
        self.assertEqual(
            value,
            "7FEDED2D75C83C7FE7877B966AAF84FDC89285017A86B46D393B67C57100B61F",
        )


if __name__ == "__main__":
    unittest.main()
