from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from urent_toolkit.errors import ConfigurationError
from urent_toolkit.profiles import AndroidProfile, choose_profile


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    device_id: str
    appsflyer_id: str
    session_id: str
    carrier_country: str
    country_code: str
    time_zone: str
    latitude: str
    longitude: str
    locale: str

    @classmethod
    def fresh(cls) -> "DeviceIdentity":
        now_ms = int(time.time() * 1000)
        return cls(
            device_id=secrets.token_hex(8),
            appsflyer_id=f"{now_ms}-{secrets.randbelow(10**18):018d}",
            session_id=str(uuid.uuid4()),
            carrier_country="DE",
            country_code="",
            time_zone="GMT+3",
            latitude="55.7569621",
            longitude="37.61501",
            locale="ru-RU",
        )

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DeviceIdentity":
        return cls(
            device_id=str(value["device_id"]),
            appsflyer_id=str(value["appsflyer_id"]),
            session_id=str(uuid.uuid4()),
            carrier_country=str(value.get("carrier_country", "DE")),
            country_code=str(value.get("country_code", "")),
            time_zone=str(value.get("time_zone", "GMT+3")),
            latitude=str(value.get("latitude", "55.7569621")),
            longitude=str(value.get("longitude", "37.61501")),
            locale=str(value.get("locale", "ru-RU")),
        )


def new_device() -> DeviceIdentity:
    return DeviceIdentity.fresh()


def create_persona(
    requested_profile: str | None = None,
    profile_file: Path | None = None,
    device_file: Path | None = None,
) -> tuple[DeviceIdentity, AndroidProfile]:
    if not device_file:
        return new_device(), choose_profile(requested_profile, profile_file)

    if device_file.exists():
        try:
            value = json.loads(device_file.read_text(encoding="utf-8"))
            identity = DeviceIdentity.from_dict(value)
            saved_profile = AndroidProfile.from_dict(value["profile"])
        except (KeyError, OSError, json.JSONDecodeError, TypeError) as exc:
            raise ConfigurationError(f"Invalid device file {device_file}: {exc}") from exc
        profile = (
            choose_profile(requested_profile, profile_file)
            if requested_profile or profile_file
            else saved_profile
        )
    else:
        identity = new_device()
        profile = choose_profile(requested_profile, profile_file)

    stored = {
        "device_id": identity.device_id,
        "appsflyer_id": identity.appsflyer_id,
        "carrier_country": identity.carrier_country,
        "country_code": identity.country_code,
        "time_zone": identity.time_zone,
        "latitude": identity.latitude,
        "longitude": identity.longitude,
        "locale": identity.locale,
        "profile": profile.to_dict(),
    }
    temporary = device_file.with_suffix(device_file.suffix + ".part")
    temporary.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    temporary.replace(device_file)
    return identity, profile
