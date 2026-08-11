from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from urent_toolkit.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class AndroidProfile:
    id: str
    manufacturer: str
    model: str
    device: str
    build_id: str
    android_release: str
    api_level: int
    chrome_version: str
    screen_width: int
    screen_height: int
    platform: str = "Linux armv8l"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AndroidProfile":
        try:
            return cls(**value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid Android profile: {exc}") from exc

    @property
    def device_model(self) -> str:
        return f"{self.manufacturer.lower()} {self.model.lower()} {self.device.lower()}"

    @property
    def webview_user_agent(self) -> str:
        return (
            f"Mozilla/5.0 (Linux; Android {self.android_release}; {self.model} "
            f"Build/{self.build_id}; wv) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Version/4.0 Chrome/{self.chrome_version} Mobile Safari/537.36"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ANDROID_PROFILES = (
    AndroidProfile("pixel-7", "Google", "Pixel 7", "panther", "TQ3A.230805.001", "13", 33, "120.0.6099.230", 412, 915),
    AndroidProfile("pixel-8", "Google", "Pixel 8", "shiba", "AP1A.240505.005", "14", 34, "124.0.6367.179", 412, 915),
    AndroidProfile("galaxy-s22", "Samsung", "SM-S901B", "r0s", "UP1A.231005.007", "14", 34, "122.0.6261.119", 360, 780),
    AndroidProfile("galaxy-a54", "Samsung", "SM-A546B", "a54x", "UP1A.231005.007", "14", 34, "123.0.6312.120", 384, 854),
    AndroidProfile("redmi-note-11", "Xiaomi", "2201117TG", "spes", "TKQ1.221114.001", "13", 33, "119.0.6045.193", 393, 873),
    AndroidProfile("redmi-note-12", "Xiaomi", "23021RAAEG", "ruby", "UP1A.231005.007", "14", 34, "123.0.6312.120", 393, 873),
    AndroidProfile("oneplus-9", "OnePlus", "LE2113", "lemonade", "TP1A.220905.001", "13", 33, "121.0.6167.164", 412, 919),
    AndroidProfile("nothing-phone-2", "Nothing", "A065", "pong", "UP1A.231005.007", "14", 34, "124.0.6367.179", 412, 915),
)


def load_profile(path: Path) -> AndroidProfile:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read Android profile {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("A custom Android profile must be a JSON object")
    return AndroidProfile.from_dict(value)


def choose_profile(
    requested: str | None = None,
    profile_file: Path | None = None,
    rng: random.Random | random.SystemRandom | None = None,
) -> AndroidProfile:
    if profile_file:
        return load_profile(profile_file)
    if requested:
        for profile in ANDROID_PROFILES:
            if profile.id == requested:
                return profile
        valid = ", ".join(profile.id for profile in ANDROID_PROFILES)
        raise ConfigurationError(f"Unknown Android profile '{requested}'. Available: {valid}")
    return (rng or random.SystemRandom()).choice(ANDROID_PROFILES)


def webview_fingerprint(
    profile: AndroidProfile,
    locale: str,
    time_zone: str,
    override: str | None = None,
) -> str:
    if override:
        parsed = json.loads(override)
        if not isinstance(parsed, dict):
            raise ConfigurationError("MTS_FINGERPRINT_JSON must contain a JSON object")
        return override
    language = locale.split("-", 1)[0]
    match = re.fullmatch(r"GMT(?P<sign>[+-])(?P<hours>\d{1,2})", time_zone)
    offset = 0
    if match:
        direction = -1 if match.group("sign") == "+" else 1
        offset = direction * int(match.group("hours")) * 60
    value = {
        "screen": {
            "screenWidth": profile.screen_width,
            "screenHeight": profile.screen_height,
            "screenColourDepth": 24,
        },
        "userAgent": profile.webview_user_agent,
        "platform": profile.platform,
        "language": language,
        "timezone": {"timezone": offset},
        "plugins": {"installedPlugins": ""},
        "fonts": {
            "installedFonts": (
                "cursive;monospace;serif;sans-serif;fantasy;default;Arial;Courier;"
                "Courier New;Georgia;Tahoma;Times;Times New Roman;Verdana;"
            )
        },
        "appName": "Netscape",
        "appCodeName": "Mozilla",
        "appVersion": profile.webview_user_agent.removeprefix("Mozilla/"),
        "product": "Gecko",
        "productSub": "20030107",
        "vendor": "Google Inc.",
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
