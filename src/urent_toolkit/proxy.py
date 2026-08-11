from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import urlparse

from urent_toolkit.errors import ConfigurationError

_lock = threading.Lock()


def validate_proxy(proxy: str) -> str:
    value = proxy.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https", "socks5"}:
        raise ConfigurationError("proxy URL must use http://, https://, or socks5://")
    if not parsed.hostname:
        raise ConfigurationError("proxy URL must contain a host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("proxy URL contains an invalid port") from exc
    if port is None:
        raise ConfigurationError("proxy URL must contain a port")
    return value


class ProxyPool:
    """A file-backed round-robin pool that leases one proxy per client session."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[str]:
        try:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError as exc:
            raise ConfigurationError(f"proxy file does not exist: {self.path}") from exc
        proxies = [
            validate_proxy(line)
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not proxies:
            raise ConfigurationError(f"proxy file contains no proxies: {self.path}")
        return proxies

    def acquire(self) -> str:
        """Lease the next proxy and persist the cursor for the next process."""
        with _lock:
            proxies = self._read()
            cursor_path = self.path.with_suffix(self.path.suffix + ".cursor")
            try:
                cursor = int(cursor_path.read_text(encoding="ascii").strip())
            except (FileNotFoundError, ValueError):
                cursor = 0
            selected = proxies[cursor % len(proxies)]
            temporary = cursor_path.with_suffix(cursor_path.suffix + ".part")
            try:
                temporary.write_text(str((cursor + 1) % len(proxies)), encoding="ascii")
                temporary.replace(cursor_path)
            except OSError as exc:
                raise ConfigurationError(
                    f"cannot update proxy rotation cursor: {cursor_path}"
                ) from exc
            return selected
