from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def save_tokens(path: Path, tokens: dict[str, Any]) -> None:
    expires_in = int(tokens.get("expires_in", 0))
    now = datetime.now(timezone.utc)
    document = {
        **tokens,
        "obtained_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
    }
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_tokens(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None
