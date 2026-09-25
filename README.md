# Soft Floyd

Soft Floyd is a sensor-aware AI cycling coach. It reads recorded Garmin
rides, keeps an honest account of the sensors available on each ride, and
uses your goals to shape the advice. Multiple riders can sign in with Google;
each rider's data is private to their account. The app currently runs locally.

## Local setup

```bash
make setup
```

Create Google OAuth credentials for a **Web application** and register
`http://localhost:5173/api/auth/google/callback` as an authorized redirect
URI. Add `SOFT_FLOYD_GOOGLE_CLIENT_ID`,
`SOFT_FLOYD_GOOGLE_CLIENT_SECRET`, and a random
`SOFT_FLOYD_JWT_SECRET` of at least 32 characters to your local `.env` or
`~/.soft-floyd/config.toml`. See `.env.example`. Google sign-in requires
internet access even though the app server runs locally.

To keep previously imported training books while starting rider accounts
from empty tables, run once:

```bash
uv run soft-floyd prepare-account-db \
  --source data/soft-floyd.db \
  --target data/soft-floyd-accounts.db
```

The command accepts an already-created **empty** account-era target and
refuses to change one containing data. It never modifies the old database.

Start the backend and web app in separate terminals:

```bash
make dev-server  # 127.0.0.1:8000
make dev-web     # http://localhost:5173
```

Open `http://localhost:5173`, continue with Google, then complete rider
onboarding. Profile shows your account identity and sign-out; Settings holds
training details and the Garmin connection.

## Garmin and coach

Garmin can connect from onboarding or Settings. The CLI is also available
with your local account ID shown in Profile:

```bash
uv run soft-floyd garmin-login --account-id 1
uv run soft-floyd garmin-sync --account-id 1
```

The web coach calls Soft Floyd's protected `/mcp` endpoint for context and
data tools. `/mcp` rejects requests without a short-lived account token.
External MCP client token setup is deferred, so Claude Desktop/Code cannot
connect directly in this release. OpenAI calls use the configured API key
and the existing server-wide monthly spending cap.

## Checks and project docs

```bash
make check
make docs-schema
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [AGENTS.md](AGENTS.md),
[docs/SECURITY.md](docs/SECURITY.md), and the
[Google accounts spec](docs/product-specs/google-accounts.md).
