from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MTS_SCOPE = "info phone profile for_premium scope_list sso openid personal_data"
DEFAULT_TOKEN_SCOPE = (
    "bike.api ordering.api location.api customers.api payment.api maintenance.api "
    "notification.api log.api ordering.scooter.api driver.bike.lock.offo.api "
    "driver.scooter.ninebot.api identity.api offline_access"
)

# This is the public OAuth credential embedded in the official Android APK.
# Mobile client secrets cannot be confidential by design. It is intentionally
# versioned here so the observed protocol is reproducible; upstream may revoke it.
MOBILE_CLIENT_SECRET = (
    "95YvCeLj74Zma3SPqyH8SwgzYMtMBj5C8FxPu5xHVExwJBjMn2t7S9L4HADQaAkc"
)


def _env(name: str, default: str = "") -> str:
    return os.getenv(f"URENT_{name}", default)


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    timeout: float
    api_base: str
    client_id: str
    client_secret: str
    app_version: str
    app_build: int
    app_package: str
    app_brand: str
    request_version: str
    token_scope: str
    android_profile: str | None
    profile_file: Path | None
    mts_authorize_url: str
    mts_authenticate_url: str
    mts_client_id: str
    mts_redirect_uri: str
    mts_scope: str
    fingerprint_json: str | None

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "Settings":
        base_dir = (data_dir or Path.cwd()).resolve()
        load_dotenv(base_dir / ".env")
        profile_file = _env("PROFILE_FILE")
        return cls(
            data_dir=base_dir,
            timeout=float(_env("TIMEOUT", "30")),
            api_base=_env(
                "API_BASE", "https://app.urentbike.ru/gatewayclient"
            ).rstrip("/"),
            client_id=_env("CLIENT_ID", "mobile.client.android"),
            client_secret=MOBILE_CLIENT_SECRET,
            app_version=_env("APP_VERSION", "2.2.0"),
            app_build=int(_env("APP_BUILD", "2020")),
            app_package=_env("APP_PACKAGE", "ru.urentbike.app"),
            app_brand=_env("APP_BRAND", "URENT"),
            request_version=_env("REQUEST_VERSION", "v2"),
            token_scope=_env("TOKEN_SCOPE", DEFAULT_TOKEN_SCOPE),
            android_profile=_env("ANDROID_PROFILE") or None,
            profile_file=Path(profile_file).expanduser().resolve() if profile_file else None,
            mts_authorize_url=_env(
                "MTS_AUTHORIZE_URL", "https://login.mts.ru/amserver/oauth2/authorize"
            ),
            mts_authenticate_url=_env(
                "MTS_AUTHENTICATE_URL",
                "https://login.mts.ru/amserver/wsso/authenticate",
            ),
            mts_client_id=_env("MTS_CLIENT_ID", "Urent"),
            mts_redirect_uri=_env(
                "MTS_REDIRECT_URI",
                "https://service.urentbike.ru/gatewayclient/api/mts/authorizationcallback",
            ),
            mts_scope=_env("MTS_SCOPE", DEFAULT_MTS_SCOPE),
            fingerprint_json=os.getenv("MTS_FINGERPRINT_JSON") or None,
        )

    @property
    def token_file(self) -> Path:
        return self.data_dir / "tokens.json"
