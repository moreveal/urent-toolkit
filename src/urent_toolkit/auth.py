from __future__ import annotations

import json
import re
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
RawOutput = Callable[[str, dict[str, Any]], None]

_SAFE_CALLBACK_OUTPUTS = {
    "choices",
    "defaultChoice",
    "errorCode",
    "message",
    "messageType",
    "options",
    "prompt",
}


def redact_diagnostic_text(value: Any, limit: int = 240) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\b\d{4,}\b", "<digits>", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", text)
    text = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "<secret>", text)
    return text[:limit]


def auth_response_summary(payload: dict[str, Any]) -> str:
    keys = ",".join(sorted(str(key) for key in payload)) or "<none>"
    callback_types: list[str] = []
    safe_outputs: list[str] = []
    callbacks = payload.get("callbacks")
    if isinstance(callbacks, list):
        for callback in callbacks:
            if not isinstance(callback, dict):
                continue
            callback_type = callback.get("type")
            if callback_type:
                callback_types.append(redact_diagnostic_text(callback_type, 80))
            output_fields = callback.get("output")
            if not isinstance(output_fields, list):
                continue
            for field in output_fields:
                if not isinstance(field, dict) or field.get("name") not in _SAFE_CALLBACK_OUTPUTS:
                    continue
                safe_outputs.append(
                    f"{field['name']}={redact_diagnostic_text(field.get('value', ''))}"
                )
    parts = [f"keys=[{keys}]", f"auth_id={bool(payload.get('authId'))}"]
    parts.append(f"success_url={bool(payload.get('successUrl'))}")
    if callback_types:
        parts.append(f"callbacks=[{','.join(callback_types)}]")
    if safe_outputs:
        parts.append(f"outputs=[{';'.join(safe_outputs)}]")
    return " ".join(parts)


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


def select_callback_option(
    payload: dict[str, Any],
    callback_type: str,
    output_name: str,
    option: str,
) -> bool:
    for callback in payload.get("callbacks", []):
        if not isinstance(callback, dict) or callback.get("type") != callback_type:
            continue
        available: list[Any] | None = None
        for field in callback.get("output") or []:
            if isinstance(field, dict) and field.get("name") == output_name:
                value = field.get("value")
                if isinstance(value, list):
                    available = value
                break
        if available is None:
            continue
        selected = next(
            (
                index
                for index, value in enumerate(available)
                if str(value).casefold() == option.casefold()
            ),
            None,
        )
        inputs = callback.get("input") or []
        if selected is None or not inputs or not isinstance(inputs[0], dict):
            continue
        inputs[0]["value"] = selected
        return True
    return False


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
        raw_output: RawOutput | None = None,
        proxy: str | None = None,
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.profile = profile
        self.output = output
        self.raw_output = raw_output
        self.proxy = proxy

    def _emit_raw(self, stage: str, payload: dict[str, Any]) -> None:
        if self.raw_output is not None:
            self.raw_output(stage, payload)

    def _emit_raw_exchange(self, stage: str, response: httpx.Response) -> None:
        if self.raw_output is None:
            return
        request = response.request
        try:
            request_body = request.content.decode("utf-8")
        except (UnicodeDecodeError, httpx.RequestNotRead):
            request_body = "<non-UTF-8 request body>"
        try:
            response_body = response.content.decode("utf-8")
        except (UnicodeDecodeError, httpx.ResponseNotRead):
            response_body = "<non-UTF-8 response body>"
        self._emit_raw(
            stage,
            {
                "request": {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers.multi_items()),
                    "body": request_body,
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers.multi_items()),
                    "body": response_body,
                },
            },
        )

    def _webview_headers(
        self,
        referer: str | None,
        *,
        navigation: bool = False,
    ) -> dict[str, str]:
        headers = {
            "User-Agent": self.profile.webview_user_agent,
            "Accept-Language": (f"{self.identity.locale},{self.identity.locale[:2]};q=0.9"),
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
        with httpx.Client(
            timeout=self.settings.timeout,
            follow_redirects=False,
            proxy=self.proxy,
        ) as client:
            self.output("[1/5] Starting MTS OAuth")
            start = client.get(
                self.settings.mts_authorize_url,
                params=params,
                headers=self._webview_headers(None, navigation=True),
            )
            self._emit_raw_exchange("mts_authorize_http", start)
            if start.status_code not in {301, 302, 303, 307, 308}:
                raise AuthenticationError(
                    f"MTS authorize: expected a redirect, got HTTP {start.status_code}"
                )
            nui_url = start.headers.get("location")
            if not nui_url:
                raise AuthenticationError("MTS authorize returned a redirect without Location")

            nui = client.get(nui_url, headers=self._webview_headers(None, navigation=True))
            self._emit_raw_exchange("mts_nui_http", nui)
            if nui.status_code != 200:
                raise AuthenticationError(f"MTS NUI: HTTP {nui.status_code}")

            authenticate_url = self._authenticate_url(nui_url)
            ajax_headers = self._webview_headers(nui_url)
            initial = client.post(authenticate_url, headers=ajax_headers, content=b"")
            self._emit_raw_exchange("mts_initial_http", initial)
            callbacks = response_json(initial, "MTS initial callbacks")
            self._emit_raw("mts_initial", callbacks)
            self.output(f"[MTS] initial response HTTP 200: {auth_response_summary(callbacks)}")
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
            self._emit_raw_exchange("mts_otp_challenge_http", challenge_response)
            challenge = response_json(challenge_response, "MTS OTP challenge")
            self._emit_raw("mts_otp_challenge", challenge)
            self.output(f"[MTS] OTP challenge HTTP 200: {auth_response_summary(challenge)}")
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
            self._emit_raw_exchange("mts_otp_submit_http", completed_response)
            completed = response_json(completed_response, "MTS OTP submit")
            self._emit_raw("mts_otp_result", completed)
            completed_summary = auth_response_summary(completed)
            self.output(f"[MTS] OTP result HTTP 200: {completed_summary}")

            follow_up = 0
            while not completed.get("successUrl") and follow_up < 3:
                chose_sms = select_callback_option(
                    completed,
                    "ChoiceCallback",
                    "choices",
                    "SMS",
                )
                confirmed = select_callback_option(
                    completed,
                    "ConfirmationCallback",
                    "options",
                    "OK",
                )
                if not chose_sms:
                    break
                follow_up += 1
                set_callback_input(completed, "cid", str(int(time.time() * 1000)))
                set_callback_input(completed, "Language", self.identity.locale[:2])
                self.output(
                    f"[MTS] Follow-up {follow_up}: selected SMS" + (" and OK" if confirmed else "")
                )
                follow_up_response = client.post(
                    authenticate_url,
                    headers=ajax_headers,
                    content=compact_json(completed),
                )
                self._emit_raw_exchange(
                    f"mts_followup_{follow_up}_http",
                    follow_up_response,
                )
                completed = response_json(
                    follow_up_response,
                    f"MTS follow-up {follow_up}",
                )
                self._emit_raw(f"mts_followup_{follow_up}", completed)
                completed_summary = auth_response_summary(completed)
                self.output(f"[MTS] Follow-up {follow_up} HTTP 200: {completed_summary}")

            success_url = completed.get("successUrl")
            if not success_url:
                detail = completed.get("message") or completed.get("code") or "unknown response"
                raise AuthenticationError(
                    "MTS did not complete authentication: "
                    f"{redact_diagnostic_text(detail)} ({completed_summary})"
                )

            oauth_result = client.get(
                success_url,
                headers=self._webview_headers(nui_url, navigation=True),
            )
            self._emit_raw_exchange("mts_oauth_completion_http", oauth_result)
            self.output(f"[MTS] OAuth completion HTTP {oauth_result.status_code}")
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
        with UrentTransport(
            self.settings,
            self.identity,
            self.profile,
            proxy=self.proxy,
        ) as transport:
            self.output("[4/5] Exchanging the MTS authorization code")
            social_response = transport.request(
                "POST",
                mtsid_url,
                content=compact_json(payload),
                content_type="application/json",
            )
            self._emit_raw_exchange("urent_mtsid_http", social_response)
            social = response_json(social_response, "Urent /mobile/mtsid")
            self.output(
                "[Urent] /mobile/mtsid response: "
                f"keys=[{','.join(sorted(str(key) for key in social))}] "
                f"succeeded={social.get('succeeded', True)}"
            )
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
            self._emit_raw_exchange("urent_token_http", token_response)
            tokens = response_json(token_response, "Urent /connect/token")
            self.output(
                "[Urent] /connect/token response: "
                f"keys=[{','.join(sorted(str(key) for key in tokens))}]"
            )
            return tokens

    def login(self, phone: str, otp_provider: OtpProvider) -> dict[str, Any]:
        return self.exchange_code(self.authorize_mts(phone, otp_provider))
