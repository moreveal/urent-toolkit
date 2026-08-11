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
- HTTP/HTTPS/SOCKS5 proxy rotation with one stable proxy per client session

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

Refresh tokens and print the new token document to stdout. Omitting the flag
prompts without echoing the refresh token:

```bash
urent refresh
```

For scripting, pass the token directly. The optional access token reproduces the
official application's `Authorization: Bearer` header:

```bash
urent refresh --refresh-token REFRESH_TOKEN --access-token ACCESS_TOKEN
```

Passing credentials as command-line arguments can expose them through shell
history and process listings; prefer the interactive prompt for manual use.

Read both existing tokens from JSON and optionally save the refreshed document:

```bash
urent refresh --token-file tokens.json --output-file refreshed-tokens.json
```

For an in-place file update, use the shorter form:

```bash
urent refresh --filepath tokens.json
```

The refreshed JSON is always printed to stdout. `--output-file` additionally
writes it atomically; it may point to the same file as `--token-file` when an
in-place update is desired.

There is also a paste-friendly helper. It accepts a complete pretty-printed JSON
object interactively and refreshes as soon as the closing brace is entered:

```bash
uv run urent refresh
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
from pathlib import Path

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

Sessions can also be restored and refreshed without another SMS login:

```python
client.restore_session(Path("tokens.json"))
if not client.ensure_valid_session():
    raise RuntimeError("Session has expired and cannot be refreshed")
```

`is_session_valid()` performs a local expiry check with a 30-second safety
window. `ensure_valid_session()` uses the refresh token when the access token is
expired and atomically updates the token file by default. For in-memory transfer,
use `serialize_session()` and `deserialize_session()`.

To use a rotating proxy list in both CLI commands and the Python API, set:

```dotenv
URENT_PROXY_FILE=proxy.txt
```

The file contains one URL per line; blank lines and lines beginning with `#` are
ignored. Credentials may be embedded in the URL:

```text
http://user:password@127.0.0.1:8080
socks5://user:password@127.0.0.1:1080
```

Each new `UrentClient.from_env()` takes the next proxy. The choice is fixed for
the complete session (MTS login, Urent token exchange, refresh, and API calls).
The rotation cursor is stored next to the list as `proxy.txt.cursor`. Leave
`URENT_PROXY_FILE` empty to connect without a proxy.

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
| `URENT_PROXY_FILE` | none | Rotating HTTP/SOCKS5 proxy-list path |
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

## Private Telegram test bot

The test bot is a separate SDK consumer in `telegram_test_bot/`. Configure its
own `.env`, then run it with uv:

```bash
uv run --project telegram_test_bot urent-test-bot
```

Send `/login`, then the account phone number and the four-digit SMS code. The bot
returns `tokens.json` as a Telegram document. It accepts only allowlisted users in
private chats, tries to delete phone/code messages, keeps the OTP only in memory,
and does not write the returned tokens to the local filesystem. Telegram still
transports and may retain chat data, so use this only with your own test account
and delete the token document after use.
