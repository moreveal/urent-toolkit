from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from urent_toolkit import AuthenticationError, UrentClient, UrentError

OTP_TIMEOUT_SECONDS = 180
_CANCEL = object()
LOGGER_NAME = "urent_test_bot"
RAW_LOGGER_NAME = "urent_test_bot.raw_auth"


def redact_error_text(value: object, limit: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(https?://[^\s?]+)\?\S+", r"\1?<redacted>", text)
    text = re.sub(r"\b\d{4,}\b", "<digits>", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", text)
    text = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "<secret>", text)
    return text[:limit]


def configure_logging(data_dir: Path) -> logging.Logger:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    return logger


def configure_raw_auth_logging(data_dir: Path) -> logging.Logger:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(RAW_LOGGER_NAME)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_dir / "raw-auth.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


def parse_allowed_user_ids(value: str) -> frozenset[int]:
    try:
        result = frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError("TELEGRAM_ALLOWED_USER_IDS must contain comma-separated integers") from exc
    if not result:
        raise ValueError("TELEGRAM_ALLOWED_USER_IDS must contain at least one Telegram user ID")
    return result


def normalize_phone_input(value: str) -> str:
    phone = "".join(character for character in value if character.isdigit())
    if len(phone) == 10 and phone.startswith("9"):
        phone = "7" + phone
    elif len(phone) == 11 and phone.startswith("8"):
        phone = "7" + phone[1:]
    if len(phone) != 11 or not phone.startswith("7"):
        raise ValueError("Нужен российский номер из 11 цифр, начинающийся с 7.")
    return phone


def token_document(tokens: dict[str, Any]) -> io.BytesIO:
    payload = json.dumps(tokens, ensure_ascii=False, indent=2).encode("utf-8")
    document = io.BytesIO(payload)
    document.name = "tokens.json"
    return document


@dataclass(slots=True)
class LoginSession:
    attempt_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: float = field(default_factory=time.monotonic)
    stage: str = "phone"
    otp: queue.Queue[object] = field(default_factory=lambda: queue.Queue(maxsize=1))
    cancelled: threading.Event = field(default_factory=threading.Event)
    task: asyncio.Task[None] | None = None

    def provide_otp(self, value: str) -> None:
        self.otp.put_nowait(value)

    def cancel(self) -> None:
        self.cancelled.set()
        try:
            self.otp.put_nowait(_CANCEL)
        except queue.Full:
            pass

    def wait_for_otp(self) -> str:
        value = self.otp.get(timeout=OTP_TIMEOUT_SECONDS)
        if value is _CANCEL or self.cancelled.is_set():
            raise AuthenticationError("Authentication cancelled")
        return str(value)


class TestAuthBot:
    def __init__(
        self,
        token: str,
        allowed_user_ids: frozenset[int],
        data_dir: Path,
        logger: logging.Logger,
        raw_auth_logger: logging.Logger | None = None,
    ) -> None:
        self.token = token
        self.allowed_user_ids = allowed_user_ids
        self.data_dir = data_dir
        self.logger = logger
        self.raw_auth_logger = raw_auth_logger
        self.sessions: dict[int, LoginSession] = {}

    def build_application(self) -> Application:
        application = Application.builder().token(self.token).build()
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("login", self.login))
        application.add_handler(CommandHandler("cancel", self.cancel))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_text))
        application.add_error_handler(self.handle_error)
        return application

    async def handle_error(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del update
        error = context.error
        self.logger.error(
            "telegram_handler_failed error_type=%s error=%s",
            type(error).__name__,
            redact_error_text(error),
        )

    def _authorized(self, update: Update) -> bool:
        user = update.effective_user
        chat = update.effective_chat
        return bool(user and chat and chat.type == "private" and user.id in self.allowed_user_ids)

    async def _require_authorized(self, update: Update) -> bool:
        if self._authorized(update):
            return True
        self.logger.warning("access_denied")
        if update.effective_message:
            await update.effective_message.reply_text("Доступ запрещён.")
        return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_authorized(update):
            return
        await update.effective_message.reply_text(
            "Тестовая авторизация Urent. Команда /login начинает вход, /cancel отменяет его."
        )

    async def login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_authorized(update):
            return
        user_id = update.effective_user.id
        previous = self.sessions.pop(user_id, None)
        if previous:
            self.logger.info("attempt=%s superseded_by_new_login", previous.attempt_id)
            previous.cancel()
        session = LoginSession()
        self.sessions[user_id] = session
        self.logger.info("attempt=%s login_started", session.attempt_id)
        await update.effective_message.reply_text("Отправьте номер телефона аккаунта.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_authorized(update):
            return
        session = self.sessions.pop(update.effective_user.id, None)
        if session:
            self.logger.info("attempt=%s cancelled", session.attempt_id)
            session.cancel()
            await update.effective_message.reply_text("Авторизация отменена.")
        else:
            await update.effective_message.reply_text("Активной авторизации нет.")

    async def receive_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_authorized(update):
            return
        message = update.effective_message
        user_id = update.effective_user.id
        session = self.sessions.get(user_id)
        if not session:
            await message.reply_text("Сначала отправьте /login.")
            return

        text = message.text.strip()
        try:
            await message.delete()
        except TelegramError as exc:
            self.logger.info(
                "attempt=%s sensitive_message_delete_failed error_type=%s",
                session.attempt_id,
                type(exc).__name__,
            )

        if session.stage == "phone":
            try:
                phone = normalize_phone_input(text)
            except ValueError as exc:
                self.logger.info("attempt=%s invalid_phone", session.attempt_id)
                await message.reply_text(str(exc))
                return
            session.stage = "starting"
            self.logger.info("attempt=%s phone_accepted", session.attempt_id)
            await message.reply_text("Запрашиваю SMS-код…")
            session.task = asyncio.create_task(self._authenticate(user_id, message.chat_id, phone))
            return

        if session.stage == "otp":
            if not text.isdigit() or len(text) != 4:
                self.logger.info("attempt=%s invalid_otp_format", session.attempt_id)
                await message.reply_text("Нужен четырёхзначный код из SMS.")
                return
            session.stage = "finishing"
            self.logger.info("attempt=%s otp_received", session.attempt_id)
            try:
                session.provide_otp(text)
            except queue.Full:
                await message.reply_text("Код уже принят, подождите завершения.")
                return
            await message.reply_text("Проверяю код и получаю токены…")
            return

        await message.reply_text("Запрос уже выполняется. Для отмены отправьте /cancel.")

    async def _authenticate(self, user_id: int, chat_id: int, phone: str) -> None:
        session = self.sessions[user_id]
        loop = asyncio.get_running_loop()

        def otp_provider() -> str:
            if session.cancelled.is_set():
                raise AuthenticationError("Authentication cancelled")
            session.stage = "otp"
            self.logger.info("attempt=%s waiting_for_otp", session.attempt_id)
            asyncio.run_coroutine_threadsafe(
                self._send_message(chat_id, "SMS отправлено. Пришлите четырёхзначный код."),
                loop,
            )
            try:
                return session.wait_for_otp()
            except queue.Empty as exc:
                self.logger.warning("attempt=%s otp_timeout", session.attempt_id)
                raise AuthenticationError("SMS code timed out") from exc

        try:
            client = UrentClient.from_env(data_dir=self.data_dir)

            def raw_output(stage: str, payload: dict[str, Any]) -> None:
                if self.raw_auth_logger is None:
                    return
                self.raw_auth_logger.info(
                    "attempt=%s stage=%s payload=%s",
                    session.attempt_id,
                    stage,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                )

            tokens = await asyncio.to_thread(
                client.login,
                phone,
                otp_provider,
                persist_tokens=False,
                output=lambda message: self.logger.info(
                    "attempt=%s sdk=%s", session.attempt_id, message
                ),
                raw_output=raw_output,
            )
            if session.cancelled.is_set():
                return
            await self._send_document(chat_id, token_document(tokens))
            self.logger.info(
                "attempt=%s completed elapsed_seconds=%.3f token_fields=%s",
                session.attempt_id,
                time.monotonic() - session.started_at,
                ",".join(sorted(str(key) for key in tokens)),
            )
        except TelegramError as exc:
            self.logger.warning(
                "attempt=%s telegram_delivery_failed elapsed_seconds=%.3f error_type=%s error=%s",
                session.attempt_id,
                time.monotonic() - session.started_at,
                type(exc).__name__,
                redact_error_text(exc),
            )
        except (UrentError, httpx.HTTPError, OSError, ValueError) as exc:
            if not session.cancelled.is_set():
                safe_error = redact_error_text(exc)
                self.logger.warning(
                    "attempt=%s failed elapsed_seconds=%.3f error_type=%s error=%s",
                    session.attempt_id,
                    time.monotonic() - session.started_at,
                    type(exc).__name__,
                    safe_error,
                )
                await self._send_message(chat_id, f"Авторизация не удалась: {safe_error}")
        finally:
            if self.sessions.get(user_id) is session:
                self.sessions.pop(user_id, None)

    async def _send_message(self, chat_id: int, text: str) -> None:
        await self.application.bot.send_message(chat_id=chat_id, text=text)

    async def _send_document(self, chat_id: int, document: io.BytesIO) -> None:
        await self.application.bot.send_document(
            chat_id=chat_id,
            document=document,
            filename="tokens.json",
            caption="Токены получены. Не пересылайте этот файл и удалите его после теста.",
        )

    def run(self) -> None:
        self.application = self.build_application()
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    data_dir = Path(__file__).resolve().parents[2]
    load_dotenv(data_dir / ".env")
    logger = configure_logging(data_dir)
    raw_auth_enabled = os.getenv("TELEGRAM_RAW_AUTH_LOG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    raw_auth_logger = configure_raw_auth_logging(data_dir) if raw_auth_enabled else None
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")
    try:
        allowed = parse_allowed_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    logger.info(
        "bot_start allowed_user_count=%d raw_auth_log=%s",
        len(allowed),
        raw_auth_enabled,
    )
    TestAuthBot(token, allowed, data_dir, logger, raw_auth_logger).run()


if __name__ == "__main__":
    main()
