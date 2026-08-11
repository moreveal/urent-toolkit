# Security

Do not include access tokens, refresh tokens, SMS codes, cookies, traffic captures,
phone numbers, or populated `.env` files in issues or pull requests.

The CLI stores tokens as plaintext JSON. Keep token and device files outside shared
directories and apply appropriate filesystem permissions.

Please report security-sensitive findings privately to the repository owner rather
than opening a public issue.
