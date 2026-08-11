from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def token_document(
    tokens: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a serializable token document with stable lifetime metadata."""
    document = dict(tokens)
    if "obtained_at" in document and "expires_at" in document:
        return document

    obtained_at = now or datetime.now(UTC)
    if obtained_at.tzinfo is None:
        obtained_at = obtained_at.replace(tzinfo=UTC)
    expires_in = int(document.get("expires_in", 0))
    document.setdefault("obtained_at", obtained_at.isoformat())
    if expires_in > 0:
        document.setdefault(
            "expires_at",
            (obtained_at + timedelta(seconds=expires_in)).isoformat(),
        )
    return document


def serialize_tokens(tokens: dict[str, Any]) -> str:
    return json.dumps(token_document(tokens), ensure_ascii=False, indent=2)


def deserialize_tokens(value: str | bytes) -> dict[str, Any]:
    document = json.loads(value)
    if not isinstance(document, dict):
        raise TypeError("token document must be a JSON object")
    return document


def tokens_are_valid(
    tokens: dict[str, Any] | None,
    *,
    leeway: float = 30,
    now: datetime | None = None,
) -> bool:
    """Check access-token presence and its locally known expiration time."""
    if not tokens or not tokens.get("access_token"):
        return False
    expires_at = tokens.get("expires_at")
    expiration: datetime | None = None
    if isinstance(expires_at, str):
        try:
            expiration = datetime.fromisoformat(expires_at)
        except ValueError:
            return False
    if expiration is None:
        # Access tokens issued by Urent are JWTs. Reading ``exp`` here is only
        # lifetime inspection; signature verification remains the API's job.
        parts = str(tokens["access_token"]).split(".")
        if len(parts) == 3:
            try:
                payload = json.loads(
                    base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
                )
                expiration = datetime.fromtimestamp(float(payload["exp"]), UTC)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return False
    if expiration is None:
        return False
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return expiration > current + timedelta(seconds=leeway)


def save_tokens(path: Path, tokens: dict[str, Any]) -> dict[str, Any]:
    document = token_document(tokens)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(serialize_tokens(document), encoding="utf-8")
    temporary.replace(path)
    return document


def load_tokens(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return deserialize_tokens(path.read_text(encoding="utf-8"))
