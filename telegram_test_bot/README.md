# Urent Telegram test bot

This directory is a standalone application that consumes `urent-toolkit` as an
editable SDK dependency through uv.

Copy `.env.example` to `.env`, set `TELEGRAM_BOT_TOKEN` and your numeric Telegram
ID in `TELEGRAM_ALLOWED_USER_IDS`, then run from the repository root:

```bash
uv run --project telegram_test_bot urent-test-bot
```

In a private chat, send `/login`, your own account phone number, and the SMS code.
The bot responds with an in-memory `tokens.json` document. Use `/cancel` to stop a
pending flow.

Diagnostic logs are written to `telegram_test_bot/logs/bot.log` and rotated at
5 MiB (three backups). Each login receives a random `attempt` ID. Logs contain
authentication stages, HTTP result stages, response key names, callback types,
and redacted server messages; phone numbers, OTPs, cookies, authorization codes,
and token values are not logged.

For protocol debugging only, raw MTS callback responses can be written to a
separate file by setting `TELEGRAM_RAW_AUTH_LOG=true`. The output is stored in
`telegram_test_bot/logs/raw-auth.log` and is never printed to Telegram or the
console. Raw mode records the actual request and response URL, headers, and body
for every MTS and Urent authentication exchange. Treat this file as a credential:
it contains phone/account data, OTPs, cookies, authorization codes, client
credentials, and token values. Disable the option and delete the file after
debugging.

The allowlist is mandatory. Phone and OTP messages are deleted on a best-effort
basis, token persistence in the SDK is disabled, and one login session is kept per
allowed Telegram user. Telegram still transports the submitted secrets; use only
test accounts you control and delete the returned document when finished.
