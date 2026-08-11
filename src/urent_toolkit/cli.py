from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from urent_toolkit import __version__
from urent_toolkit.client import UrentClient
from urent_toolkit.errors import UrentError
from urent_toolkit.profiles import ANDROID_PROFILES
from urent_toolkit.storage import load_tokens


def prompt_token_document() -> dict[str, object]:
    print("Paste the token JSON containing access_token and refresh_token:")
    lines: list[str] = []
    while True:
        try:
            lines.append(input())
        except EOFError as exc:
            raise ValueError("incomplete token JSON") from exc
        try:
            value = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            raise TypeError("token JSON must be an object")
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urent",
        description="Unofficial CLI for Urent services",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    auth = commands.add_parser("auth", help="Authenticate through MTS ID SMS OTP")
    auth.add_argument("--phone", help="Phone number; prompted when omitted")
    auth.add_argument("--profile", help="Built-in Android profile id")
    auth.add_argument("--profile-file", type=Path, help="Custom Android profile JSON")
    auth.add_argument(
        "--device-file",
        type=Path,
        help="Persist and reuse a complete device persona instead of generating a new one",
    )
    auth.add_argument("--token-file", type=Path, default=Path("tokens.json"))

    refresh = commands.add_parser(
        "refresh",
        help="Exchange a refresh token and print the new tokens as JSON",
    )
    refresh.add_argument(
        "--refresh-token",
        help="Refresh token; a complete token JSON is prompted when omitted",
    )
    refresh.add_argument(
        "--access-token",
        help="Current access token for the app-compatible Authorization header",
    )
    refresh.add_argument(
        "--token-file",
        type=Path,
        help="Read access_token and refresh_token from a JSON token document",
    )
    refresh.add_argument(
        "--filepath",
        type=Path,
        help="Read tokens from this JSON file and update the same file in place",
    )
    refresh.add_argument(
        "--output-file",
        type=Path,
        help="Also save the refreshed token document to this path",
    )
    refresh.add_argument("--profile", help="Built-in Android profile id")
    refresh.add_argument("--profile-file", type=Path, help="Custom Android profile JSON")
    refresh.add_argument("--device-file", type=Path, help="Persisted device persona")

    commands.add_parser("profiles", help="List built-in Android profiles")
    template = commands.add_parser("profile-template", help="Print a custom profile JSON template")
    template.add_argument("--profile", default="pixel-8")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "profiles":
        for profile in ANDROID_PROFILES:
            print(
                f"{profile.id:18} Android {profile.android_release:<2} "
                f"Chrome {profile.chrome_version:<18} {profile.model}"
            )
        return 0

    if args.command == "profile-template":
        profile = next((item for item in ANDROID_PROFILES if item.id == args.profile), None)
        if profile is None:
            print(f"Unknown profile: {args.profile}")
            return 2
        print(json.dumps(profile.to_dict(), indent=2))
        return 0

    if args.command == "refresh":
        try:
            if args.filepath and (args.token_file or args.output_file):
                print("Error: --filepath cannot be combined with --token-file or --output-file")
                return 2
            input_file = args.filepath or args.token_file
            output_file = args.filepath or args.output_file
            restored = load_tokens(input_file) if input_file else None
            if input_file and restored is None:
                print(f"Error: token file not found or invalid: {input_file}")
                return 2
            if restored is None and args.refresh_token is None:
                restored = prompt_token_document()
            restored = restored or {}
            refresh_token = args.refresh_token or restored.get("refresh_token")
            if not refresh_token:
                print("Error: refresh token is empty")
                return 2
            access_token = args.access_token or restored.get("access_token")
            client = UrentClient.from_env(
                profile=args.profile,
                profile_file=args.profile_file,
                device_file=args.device_file,
            )
            client.tokens = {
                "refresh_token": refresh_token,
                **({"access_token": access_token} if access_token else {}),
            }
            tokens = client.refresh_tokens(
                token_file=output_file,
                persist_tokens=output_file is not None,
                output=lambda _message: None,
            )
        except (
            UrentError,
            httpx.HTTPError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            print(f"Error: {exc}")
            return 1
        print("Refreshed tokens:")
        print(json.dumps(tokens, ensure_ascii=False, indent=2))
        return 0

    try:
        client = UrentClient.from_env(
            profile=args.profile,
            profile_file=args.profile_file,
            device_file=args.device_file,
        )
        phone = args.phone or input("Phone number: ").strip()
        print(
            f"Device: {client.profile.manufacturer} {client.profile.model} "
            f"(Android {client.profile.android_release})"
        )
        client.login(
            phone,
            lambda: input("SMS code: "),
            token_file=args.token_file,
        )
    except (UrentError, httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Authentication complete. Tokens saved to {args.token_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
