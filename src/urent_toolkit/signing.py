from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlparse


_MASKED_KEY_HEX = (
    "4a71555967454c560d5d746d756c736d7106667e66735e09550c745d0b6a75560d"
    "0e776a0c770a6a7b6b540e4e096f075b6d725766667e776b7556774f584d6700"
)


def signing_key(client_id: str) -> bytes:
    decoded = bytes(byte ^ 0x3F for byte in bytes.fromhex(_MASKED_KEY_HEX))
    key = bytearray(64)
    key[: min(64, len(decoded))] = decoded[:64]
    client = client_id.encode("utf-8")
    if client:
        start = max(32, 64 - len(client))
        key[start : start + min(32, len(client))] = client[:32]
    return bytes(key)


def request_signature(body: bytes, headers: dict[str, str], url: str, client_id: str) -> str:
    signed_headers = sorted(
        (
            (name.lower(), value)
            for name, value in headers.items()
            if name.lower().startswith("ur-") and name.lower() != "ur-request-data"
        ),
        key=lambda item: item[0],
    )
    query = parse_qs(urlparse(url).query, keep_blank_values=True)
    text = "".join(value for _, value in signed_headers)
    text += "".join(key + values[0] for key, values in sorted(query.items()))
    return hmac.new(
        signing_key(client_id),
        text.encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest().upper()
