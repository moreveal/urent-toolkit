from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from urent_toolkit.auth import Authenticator
from urent_toolkit.config import Settings
from urent_toolkit.device import DeviceIdentity, create_persona
from urent_toolkit.profiles import AndroidProfile
from urent_toolkit.storage import load_tokens, save_tokens
from urent_toolkit.transport import UrentTransport


class UrentClient:
    def __init__(
        self,
        settings: Settings,
        identity: DeviceIdentity,
        profile: AndroidProfile,
        tokens: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.profile = profile
        self.tokens = tokens

    @classmethod
    def from_env(
        cls,
        *,
        data_dir: Path | None = None,
        profile: str | None = None,
        profile_file: Path | None = None,
        device_file: Path | None = None,
    ) -> "UrentClient":
        settings = Settings.from_env(data_dir)
        identity, selected = create_persona(
            profile or settings.android_profile,
            profile_file or settings.profile_file,
            device_file,
        )
        return cls(settings, identity, selected)

    def restore_tokens(self, path: Path | None = None) -> dict[str, Any] | None:
        self.tokens = load_tokens(path or self.settings.token_file)
        return self.tokens

    def login(
        self,
        phone: str,
        otp_provider: Callable[[], str],
        *,
        token_file: Path | None = None,
        output: Callable[[str], None] = print,
    ) -> dict[str, Any]:
        authenticator = Authenticator(self.settings, self.identity, self.profile, output)
        self.tokens = authenticator.login(phone, otp_provider)
        save_tokens(token_file or self.settings.token_file, self.tokens)
        return self.tokens

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        content: bytes = b"",
        content_type: str | None = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> httpx.Response:
        if json_body is not None:
            content = json.dumps(
                json_body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            content_type = "application/json"
        token = self.tokens.get("access_token") if authenticated and self.tokens else None
        url = path if path.startswith("http") else f"{self.settings.api_base}/{path.lstrip('/')}"
        with UrentTransport(self.settings, self.identity, self.profile) as transport:
            return transport.request(
                method,
                url,
                content=content,
                content_type=content_type,
                access_token=token,
                params=params,
            )
