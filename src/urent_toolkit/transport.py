from __future__ import annotations

import secrets
from typing import Any

import httpx

from urent_toolkit.config import Settings
from urent_toolkit.device import DeviceIdentity
from urent_toolkit.profiles import AndroidProfile
from urent_toolkit.signing import request_signature


def new_traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


class UrentTransport:
    def __init__(
        self,
        settings: Settings,
        identity: DeviceIdentity,
        profile: AndroidProfile,
        client: httpx.Client | None = None,
        proxy: str | None = None,
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.profile = profile
        self.client = client or httpx.Client(
            timeout=settings.timeout,
            follow_redirects=False,
            proxy=proxy,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "UrentTransport":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def base_headers(self) -> dict[str, str]:
        app = self.settings
        profile = self.profile
        return {
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Environment-Info": (
                f"plt:android,{app.app_version}({app.app_build}),"
                f"mod:{profile.device_model},os:{profile.android_release},phone:"
            ),
            "UR-Carrier-Country": self.identity.carrier_country,
            "UR-Country-Code": self.identity.country_code,
            "UR-Device-Model": profile.device_model,
            "UR-Device-Id": self.identity.device_id,
            "UR-Latitude": self.identity.latitude,
            "UR-Longitude": self.identity.longitude,
            "UR-OS": profile.android_release,
            "UR-Platform": "Android",
            "UR-Session": self.identity.session_id,
            "UR-Time-Zone": self.identity.time_zone,
            "UR-User-Id": "",
            "UR-Version": app.app_version,
            "UR-Client-Id": app.client_id,
            "UR-Mobile-Store-Name": "",
            "User-Agent": (
                f"Urent/{app.app_version} ({app.app_package}; build:{app.app_build}; "
                f"Android {profile.android_release}) okhttp/5.2.1"
            ),
            "X-Appsflyer-Id": self.identity.appsflyer_id,
            "Accept-Language": self.identity.locale,
            "UR-Brand": app.app_brand,
            "UR-Request-Version": app.request_version,
            "Traceparent": new_traceparent(),
        }

    def request(
        self,
        method: str,
        url: str,
        *,
        content: bytes = b"",
        content_type: str | None = None,
        access_token: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request = self.client.build_request(method, url, params=params, content=content)
        final_url = str(request.url)
        final_headers = self.base_headers()
        if headers:
            final_headers.update(headers)
        if content_type:
            final_headers["Content-Type"] = content_type
        if access_token:
            final_headers["Authorization"] = f"Bearer {access_token}"
        final_headers["UR-Request-Data"] = request_signature(
            content,
            final_headers,
            final_url,
            self.settings.client_id,
        )
        request.headers.update(final_headers)
        return self.client.send(request)
