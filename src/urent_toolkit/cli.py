from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from urent_toolkit import __version__
from urent_toolkit.client import UrentClient
from urent_toolkit.errors import UrentError
from urent_toolkit.profiles import ANDROID_PROFILES


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
