# Deploying to Fly.io

The app ships as a `Dockerfile` (multi-stage, non-root, port 8000) with a `fly.toml`. The
database is **external managed Neon Postgres** (not a Fly Postgres). Fly terminates TLS at the
edge, which gives the PWA + the Secure auth cookie the HTTPS they need.

## One-time prerequisites

1. Install `flyctl` and sign in:
   ```powershell
   iwr https://fly.io/install.ps1 -useb | iex   # (or: curl -L https://fly.io/install.sh | sh)
   fly auth login
   ```
2. **Enable PostGIS on Neon once** (migration `0001` uses spatial types). In the Neon SQL editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

## First deploy

1. **Generate the app** without deploying (declines Fly Postgres — the DB is external Neon):
   ```powershell
   fly launch --no-deploy --dockerfile Dockerfile
   ```
   Keep the committed `fly.toml` (replace what `launch` writes if needed). Note the hostname it
   assigns: `https://<app>.fly.dev`.

2. **Pin CORS** to that origin so the cross-origin auth cookie is allowed. Edit `CORS_ORIGINS`
   in `fly.toml` `[env]` to `https://<app>.fly.dev` (do **not** leave `*` — the app disables
   credentials when origins is `*`, which silently breaks the cookie).

3. **Set the secrets** (encrypted; never baked into the image):
   ```powershell
   fly secrets set `
     DATABASE_URL='postgresql+asyncpg://USER:PASS@ep-xxxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require' `
     APP_SECRET='<a-strong-shared-password>' `
     ANTHROPIC_API_KEY='sk-ant-...' `
     GOOGLE_MAPS_API_KEY='...'
   ```
   - `DATABASE_URL` — paste Neon's string verbatim; the app auto-upgrades `postgresql://` →
     `+asyncpg` and translates `sslmode=require` into the asyncpg SSL arg.
   - `APP_SECRET` — **required in prod** or the app is fully open; enables `/login` + the
     HttpOnly Secure cookie.
   - `ANTHROPIC_API_KEY` — used by the hotel/transport/budget specialist experts.

4. **Chat (optional) — the Ollama gotcha.** The chat agent defaults to
   `QWEN_BASE_URL=http://localhost:11434/v1` (local Ollama). **There is no Ollama inside the Fly
   Machine**, so with the default, every `/chat` request fails (the route returns a friendly
   error, not a 500). The plan viewer, map, task board, login, and PWA offline view all work
   regardless — only the chat box is affected. To enable chat, point it at a hosted
   OpenAI-compatible Qwen:
   ```powershell
   # DashScope:
   fly secrets set QWEN_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1' `
                   QWEN_MODEL='qwen-plus' QWEN_API_KEY='<dashscope-key>'
   # OpenRouter alternative:
   #   QWEN_BASE_URL=https://openrouter.ai/api/v1  QWEN_MODEL=qwen/qwen3-235b-a22b  QWEN_API_KEY=<key>
   ```
   (Web search inside chat uses keyless DuckDuckGo, so no search key is ever needed.)

5. **Deploy:**
   ```powershell
   fly deploy
   ```
   Fly builds the image, then runs the `[deploy] release_command` — `alembic upgrade head` — in a
   throwaway Machine against Neon **before** the new version goes live. A failed migration aborts
   the deploy before any traffic shifts.

6. **Verify:** `fly logs` (watch the release command apply migrations), then visit
   `https://<app>.fly.dev/health/db` (DB connectivity) and `/plan` (login flow over HTTPS).

## Day-to-day

- **Re-deploy:** `fly deploy` after each change — it rebuilds and re-runs `alembic upgrade head`
  automatically, so new migrations apply every deploy.
- **Update a secret:** `fly secrets set KEY=value` (restarts Machines with the new value).
- **Run a migration by hand** (instead of the release command): `fly ssh console -C 'alembic upgrade head'`.
- **Scale:** `fly scale count 1` (exactly one Machine) / `fly scale memory 1024` (if migrations or
  chat OOM). With `min_machines_running = 0` the first request after idle has a ~1–2 s cold start.

## Notes

- **`DEBUG` must stay `"false"`** in prod: the auth cookie is set `secure=(not DEBUG)`, so a truthy
  DEBUG would emit a non-Secure cookie over the HTTPS-only edge and break login. Never set DEBUG
  truthy via a secret either.
- The image installs only the `llm` extra (chat deps). The `ingest`/`geo`/`graph` extras are for
  offline data-prep scripts and are intentionally excluded to keep the image small.
