from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from urent_toolkit.auth import Authenticator, response_json
from urent_toolkit.config import Settings
from urent_toolkit.device import DeviceIdentity, create_persona
from urent_toolkit.profiles import AndroidProfile
from urent_toolkit.proxy import ProxyPool, validate_proxy
from urent_toolkit.storage import (
    deserialize_tokens,
    load_tokens,
    save_tokens,
    serialize_tokens,
    token_document,
    tokens_are_valid,
)
from urent_toolkit.transport import UrentTransport


class UrentClient:
    def __init__(
        self,
        settings: Settings,
        identity: DeviceIdentity,
        profile: AndroidProfile,
        tokens: dict[str, Any] | None = None,
        proxy: str | None = None,
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.profile = profile
        self.tokens = tokens
        self.proxy = validate_proxy(proxy) if proxy else None

    @classmethod
    def from_env(
        cls,
        *,
        data_dir: Path | None = None,
        profile: str | None = None,
        profile_file: Path | None = None,
        device_file: Path | None = None,
        proxy: str | None = None,
    ) -> UrentClient:
        settings = Settings.from_env(data_dir)
        identity, selected = create_persona(
            profile or settings.android_profile,
            profile_file or settings.profile_file,
            device_file,
        )
        if proxy:
            selected_proxy = validate_proxy(proxy)
        elif settings.proxy_file:
            selected_proxy = ProxyPool(settings.proxy_file).acquire()
        else:
            selected_proxy = None
        return cls(settings, identity, selected, proxy=selected_proxy)

    def serialize_session(self) -> str:
        """Serialize the current token session to JSON."""
        if not self.tokens:
            raise ValueError("There is no session to serialize")
        self.tokens = token_document(self.tokens)
        return serialize_tokens(self.tokens)

    def deserialize_session(self, value: str | bytes) -> dict[str, Any]:
        """Restore the current token session from JSON."""
        self.tokens = deserialize_tokens(value)
        return self.tokens

    def save_session(self, path: Path | None = None) -> dict[str, Any]:
        if not self.tokens:
            raise ValueError("There is no session to save")
        self.tokens = save_tokens(path or self.settings.token_file, self.tokens)
        return self.tokens

    def restore_tokens(self, path: Path | None = None) -> dict[str, Any] | None:
        self.tokens = load_tokens(path or self.settings.token_file)
        return self.tokens

    restore_session = restore_tokens

    def is_session_valid(self, *, leeway: float = 30) -> bool:
        """Return whether the access token is present and not about to expire."""
        return tokens_are_valid(self.tokens, leeway=leeway)

    def ensure_valid_session(
        self,
        *,
        leeway: float = 30,
        auto_refresh: bool = True,
        token_file: Path | None = None,
        persist_tokens: bool = True,
        output: Callable[[str], None] = print,
    ) -> bool:
        """Validate the session and optionally refresh an expired access token."""
        if self.is_session_valid(leeway=leeway):
            return True
        if not auto_refresh or not self.tokens or not self.tokens.get("refresh_token"):
            return False
        self.refresh_tokens(
            token_file=token_file,
            persist_tokens=persist_tokens,
            output=output,
        )
        return self.is_session_valid(leeway=leeway)

    def login(
        self,
        phone: str,
        otp_provider: Callable[[], str],
        *,
        token_file: Path | None = None,
        persist_tokens: bool = True,
        output: Callable[[str], None] = print,
        raw_output: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        authenticator = Authenticator(
            self.settings,
            self.identity,
            self.profile,
            output,
            raw_output,
            self.proxy,
        )
        self.tokens = authenticator.login(phone, otp_provider)
        if persist_tokens:
            self.tokens = save_tokens(token_file or self.settings.token_file, self.tokens)
        return self.tokens

    def refresh_tokens(
        self,
        *,
        token_file: Path | None = None,
        persist_tokens: bool = True,
        output: Callable[[str], None] = print,
    ) -> dict[str, Any]:
        if not self.tokens or not self.tokens.get("refresh_token"):
            raise ValueError("A refresh_token must be restored before refreshing")
        form = {
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "grant_type": "refresh_token",
            "scope": self.settings.token_scope,
            "refresh_token": self.tokens["refresh_token"],
        }
        token_url = f"{self.settings.api_base}/api/v1/connect/token"
        output("Refreshing tokens through Urent /connect/token")
        with UrentTransport(
            self.settings,
            self.identity,
            self.profile,
            proxy=self.proxy,
        ) as transport:
            response = transport.request(
                "POST",
                token_url,
                content=urlencode(form).encode("utf-8"),
                content_type="application/x-www-form-urlencoded; charset=UTF-8",
                access_token=self.tokens.get("access_token"),
            )
        refreshed = response_json(response, "Urent refresh /connect/token")
        self.tokens = refreshed
        if persist_tokens:
            self.tokens = save_tokens(token_file or self.settings.token_file, self.tokens)
        output("Token refresh complete")
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
        with UrentTransport(
            self.settings,
            self.identity,
            self.profile,
            proxy=self.proxy,
        ) as transport:
            return transport.request(
                method,
                url,
                content=content,
                content_type=content_type,
                access_token=token,
                params=params,
            )
