from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx

from urent_toolkit.config import Settings
from urent_toolkit.device import DeviceIdentity
from urent_toolkit.errors import AuthenticationError, ConfigurationError
from urent_toolkit.profiles import AndroidProfile, webview_fingerprint
from urent_toolkit.transport import UrentTransport


OtpProvider = Callable[[], str]
Output = Callable[[str], None]


def compact_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def normalize_phone(value: str) -> str:
    phone = "".join(character for character in value if character.isdigit())
    if len(phone) == 10 and phone.startswith("9"):
        phone = "7" + phone
    elif len(phone) == 11 and phone.startswith("8"):
        phone = "7" + phone[1:]
    if len(phone) != 11 or not phone.startswith("7"):
        raise AuthenticationError("Expected an 11-digit Russian phone number starting with 7")
    return phone


def set_callback_input(payload: dict[str, Any], name: str, value: Any) -> bool:
    changed = False
    for callback in payload.get("callbacks", []):
        for field in callback.get("input") or []:
            if field.get("name") == name:
                field["value"] = value
                changed = True
    return changed


def response_json(response: httpx.Response, stage: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise AuthenticationError(f"{stage}: HTTP {response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise AuthenticationError(f"{stage}: the server returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise AuthenticationError(f"{stage}: expected a JSON object")
    return value


class Authenticator:
    def __init__(
        self,
        settings: Settings,
        identity: DeviceIdentity,
        profile: AndroidProfile,
        output: Output = print,
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.profile = profile
        self.output = output

    def _webview_headers(
        self,
        referer: str | None,
        *,
        navigation: bool = False,
    ) -> dict[str, str]:
        headers = {
            "User-Agent": self.profile.webview_user_agent,
            "Accept-Language": (
                f"{self.identity.locale},{self.identity.locale[:2]};q=0.9"
            ),
            "X-Requested-With": self.settings.app_package,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if referer:
            headers["Referer"] = referer
        if navigation:
            headers.update(
                {
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document",
                }
            )
        else:
            headers.update(
                {
                    "Accept": "*/*",
                    "Accept-API-Version": "resource=4.0, protocol=1.0",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Origin": "https://login.mts.ru",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                }
            )
        return headers

    def _authenticate_url(self, nui_url: str) -> str:
        query = parse_qs(urlparse(nui_url).query, keep_blank_values=True)

        def one(name: str) -> str:
            values = query.get(name)
            if not values:
                raise AuthenticationError(f"MTS redirect is missing '{name}'")
            return values[0]

        params = {
            "client_id": one("client_id"),
            "scope": one("scope"),
            "redirect_uri": one("redirect_uri"),
            "authIndexType": "service",
            "authIndexValue": "login-spa",
            "goto": one("goto"),
            "login_hint": one("login_hint"),
            "response_type": one("response_type"),
            "statetrace": one("statetrace"),
        }
        return self.settings.mts_authenticate_url + "?" + urlencode(params, quote_via=quote)

    def authorize_mts(self, phone: str, otp_provider: OtpProvider) -> str:
        state = str(uuid.uuid4())
        params = {
            "client_id": self.settings.mts_client_id,
            "scope": self.settings.mts_scope,
            "state": state,
            "nonce": str(uuid.uuid4()),
            "redirect_uri": self.settings.mts_redirect_uri,
            "login_hint": normalize_phone(phone),
            "response_type": "code",
        }
        with httpx.Client(timeout=self.settings.timeout, follow_redirects=False) as client:
            self.output("[1/5] Starting MTS OAuth")
            start = client.get(
                self.settings.mts_authorize_url,
                params=params,
                headers=self._webview_headers(None, navigation=True),
            )
            if start.status_code not in {301, 302, 303, 307, 308}:
                raise AuthenticationError(
                    f"MTS authorize: expected a redirect, got HTTP {start.status_code}"
                )
            nui_url = start.headers.get("location")
            if not nui_url:
                raise AuthenticationError("MTS authorize returned a redirect without Location")

            nui = client.get(nui_url, headers=self._webview_headers(None, navigation=True))
            if nui.status_code != 200:
                raise AuthenticationError(f"MTS NUI: HTTP {nui.status_code}")

            authenticate_url = self._authenticate_url(nui_url)
            ajax_headers = self._webview_headers(nui_url)
            initial = client.post(authenticate_url, headers=ajax_headers, content=b"")
            callbacks = response_json(initial, "MTS initial callbacks")
            initial_values = {
                "IDToken1": webview_fingerprint(
                    self.profile,
                    self.identity.locale,
                    self.identity.time_zone,
                    self.settings.fingerprint_json,
                ),
                "IDToken2": "",
                "IDToken3": "false",
                "IDToken4": "android",
                "IDToken5": "",
                "IDToken7": str(uuid.uuid4()),
                "IDToken8": "",
                "referrer": "",
                "IDToken9": "Chrome WebView",
                "IDToken10": "true",
                "IDToken6": 0,
                "cid": str(int(time.time() * 1000)),
                "Language": self.identity.locale[:2],
            }
            for name, value in initial_values.items():
                set_callback_input(callbacks, name, value)

            self.output("[2/5] Requesting an SMS code")
            challenge_response = client.post(
                authenticate_url,
                headers=ajax_headers,
                content=compact_json(callbacks),
            )
            challenge = response_json(challenge_response, "MTS OTP challenge")
            if not challenge.get("authId"):
                raise AuthenticationError(
                    "MTS did not return an OTP authId; the account may require another flow"
                )

            otp = otp_provider().strip()
            if not otp.isdigit() or len(otp) != 4:
                raise AuthenticationError("MTS expects a four-digit SMS code in this flow")
            set_callback_input(challenge, "IDToken1", otp)
            set_callback_input(challenge, "IDToken4", "true")
            set_callback_input(challenge, "IDToken2", 1)
            set_callback_input(challenge, "cid", str(int(time.time() * 1000)))
            set_callback_input(challenge, "Language", self.identity.locale[:2])

            self.output("[3/5] Submitting the SMS code")
            completed_response = client.post(
                authenticate_url,
                headers=ajax_headers,
                content=compact_json(challenge),
            )
            completed = response_json(completed_response, "MTS OTP submit")
            success_url = completed.get("successUrl")
            if not success_url:
                detail = completed.get("message") or completed.get("code") or "unknown response"
                raise AuthenticationError(f"MTS did not complete authentication: {detail}")

            oauth_result = client.get(
                success_url,
                headers=self._webview_headers(nui_url, navigation=True),
            )
            if oauth_result.status_code not in {301, 302, 303, 307, 308}:
                raise AuthenticationError(
                    f"MTS OAuth completion: expected a redirect, got HTTP {oauth_result.status_code}"
                )
            callback_url = oauth_result.headers.get("location", "")
            actual = urlparse(callback_url)
            expected = urlparse(self.settings.mts_redirect_uri)
            if (actual.scheme, actual.netloc, actual.path) != (
                expected.scheme,
                expected.netloc,
                expected.path,
            ):
                raise AuthenticationError("MTS returned an unexpected callback URL")
            callback = parse_qs(actual.query)
            if callback.get("state", [None])[0] != state:
                raise AuthenticationError("OAuth state mismatch")
            code = callback.get("code", [None])[0]
            if not code:
                raise AuthenticationError("MTS callback does not contain an authorization code")
            return code

    def exchange_code(self, code: str) -> dict[str, Any]:
        if not self.settings.client_secret:
            raise ConfigurationError("URENT_CLIENT_SECRET is not configured")
        mtsid_url = f"{self.settings.api_base}/api/v1/mobile/mtsid"
        token_url = f"{self.settings.api_base}/api/v1/connect/token"
        payload = {
            "authorizationCode": code,
            "osVersion": str(self.profile.api_level),
            "phoneModel": self.profile.device_model,
            "phoneModelType": "Android",
            "uniqueId": self.identity.device_id,
        }
        with UrentTransport(self.settings, self.identity, self.profile) as transport:
            self.output("[4/5] Exchanging the MTS authorization code")
            social_response = transport.request(
                "POST",
                mtsid_url,
                content=compact_json(payload),
                content_type="application/json",
            )
            social = response_json(social_response, "Urent /mobile/mtsid")
            if not social.get("succeeded", True):
                raise AuthenticationError(f"Urent rejected MTS login: {social.get('errors')}")
            phone_number = social.get("phoneNumber")
            sms_auto_code = social.get("smsAutoCode")
            if not phone_number or not sms_auto_code:
                raise AuthenticationError(
                    "Urent /mobile/mtsid did not return phoneNumber and smsAutoCode"
                )
            form = {
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "username": phone_number,
                "password": sms_auto_code,
                "scope": self.settings.token_scope,
                "grant_type": "password",
            }
            self.output("[5/5] Requesting access and refresh tokens")
            token_response = transport.request(
                "POST",
                token_url,
                content=urlencode(form).encode("utf-8"),
                content_type="application/x-www-form-urlencoded; charset=UTF-8",
            )
            return response_json(token_response, "Urent /connect/token")

    def login(self, phone: str, otp_provider: OtpProvider) -> dict[str, Any]:
        return self.exchange_code(self.authorize_mts(phone, otp_provider))
