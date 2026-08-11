# Urent Toolkit

Unofficial Python toolkit and CLI for Urent services.

Urent Toolkit provides a reusable HTTP client, request signing, Android device
personas, and a headless MTS ID SMS authentication flow. It uses direct HTTP
requests only—no browser automation or Playwright.

> [!WARNING]
> This project is experimental and targets an observed Urent 2.2.0 protocol.
> Server-side changes, CAPTCHA, seamless login, or additional MTS callbacks may
> require an update. Use it only with accounts and systems you are authorized to
> access.

## Features

- MTS ID OAuth with interactive SMS OTP
- Urent `UR-Request-Data` request signing
- Access and refresh token exchange
- A generic signed API client for future endpoints
- Coherent Android personas with matching WebView UA, screen, OS, model, and API level
- Random fresh device persona on every run by default
- Built-in, custom, or explicitly persisted device profiles
- Environment-based configuration with no secrets committed to Git

## Installation

```bash
python -m pip install -e .
```

Copy `.env.example` to `.env` when you need configuration overrides. The local
`.env` file is ignored by Git.

## CLI

Authenticate with a randomly selected Android persona and fresh identifiers:

```bash
urent auth
```

Choose a built-in phone:

```bash
urent auth --profile pixel-8
```

List available phones:

```bash
urent profiles
```

Use a fully custom profile:

```bash
urent auth --profile-file my-phone.json
```

Print a valid profile template:

```bash
urent profile-template --profile galaxy-s22 > my-phone.json
```

By default, the phone profile, device ID, AppsFlyer ID, and session ID are newly
generated for each process. To reuse one complete persona explicitly:

```bash
urent auth --profile redmi-note-12 --device-file redmi.device.json
```

On later runs, omit `--profile` and pass the same `--device-file` to restore the
saved model and identifiers.

## Custom Android profile

```json
{
  "id": "my-pixel",
  "manufacturer": "Google",
  "model": "Pixel 8",
  "device": "shiba",
  "build_id": "AP1A.240505.005",
  "android_release": "14",
  "api_level": 34,
  "chrome_version": "124.0.6367.179",
  "screen_width": 412,
  "screen_height": 915,
  "platform": "Linux armv8l"
}
```

Keep the fields coherent. The toolkit derives the WebView user agent, Urent
headers, fingerprint, and API payload from this profile.

## Python API

```python
from urent_toolkit import UrentClient

client = UrentClient.from_env(profile="pixel-8")
client.login(
    phone="79990000000",
    otp_provider=lambda: input("SMS code: "),
)

profile = client.request("GET", "/api/v1/profile")
profile.raise_for_status()
print(profile.json())
```

Pass `profile_file=Path(...)` for a custom phone or `device_file=Path(...)` to
persist the complete persona.

## Configuration

All settings use the `URENT_` prefix unless noted otherwise.

| Variable | Default | Purpose |
| --- | --- | --- |
| `URENT_API_BASE` | production gateway | Urent API base URL |
| `URENT_ANDROID_PROFILE` | random | Built-in profile id |
| `URENT_PROFILE_FILE` | none | Custom profile JSON |
| `URENT_TIMEOUT` | `30` | HTTP timeout in seconds |
| `MTS_FINGERPRINT_JSON` | generated | Full fingerprint override |

Advanced URLs, scopes, app metadata, and request version can also be overridden;
see `.env.example` and `urent_toolkit.config.Settings`.

Carrier, country, locale, time zone, and coordinates belong to `DeviceIdentity`,
not global environment configuration. They are generated with the persona and
are included in an explicitly persisted `--device-file`, where they can be edited.

The mobile OAuth client credential is intentionally embedded in the source. It is
a public credential distributed in the Android APK, not a user secret, and may be
revoked by the upstream service.

## Security

Tokens are stored as plaintext JSON by the CLI. Protect `tokens.json`, custom
device files, traffic captures, and `.env` as credentials. They are excluded by
the included `.gitignore`, but filesystem permissions remain your responsibility.

This repository is not affiliated with or endorsed by Urent or MTS.
