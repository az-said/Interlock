# Deploying the live demo

The demo server (`demo/serve.py`, which runs `backend/api.py`) binds to 127.0.0.1 and trusts its caller. To put it on the internet, run it in public mode: `INTERLOCK_PUBLIC=1`. The `Dockerfile` at the repo root does that. With public mode off, nothing below applies and the local demo behaves as before.

The standalone demo (no Temporal) is the primary public page, at `/`. The Temporal demo at `/demo` is served too when Temporal's dev server starts inside the container; if it does not, `/demo` says the Temporal demo is unavailable and `/` keeps working.

## Build and run

```
docker build -t interlock-demo .
docker run --rm -p 8080:8080 -e INTERLOCK_ALLOWED_HOSTS=localhost interlock-demo
curl http://localhost:8080/healthz          # {"ok": true}
```

With no keys, Run live is off and Run mock works (labeled MOCK). A browser on `http://localhost:8080` can load the page but cannot start runs, because public mode accepts POSTs only from an `https://` origin; test runs behind TLS, or run `python3 demo/serve.py` locally without public mode.

The image is `python:3.12-slim` with `temporalio==1.32.0` installed and the Temporal CLI 1.4.1 binary downloaded at build time to `/opt/temporal/temporal` (build arguments `TEMPORALIO_VERSION` and `TEMPORAL_CLI_VERSION`). `tini` is PID 1: on SIGTERM (`docker stop`, a revision swap) `serve.py` stops the API process group and exits, and tini reaps any leftover process. It runs as the non-root user `interlock` (uid 10001), writes run data to `/home/interlock/data`, and listens on 8080.

## Environment variables

| variable | default | meaning |
|---|---|---|
| `INTERLOCK_PUBLIC` | `1` in the image, unset otherwise | `1` turns public mode on. Any other value is off. |
| `INTERLOCK_ALLOWED_HOSTS` | none, required | Comma-separated hostnames the server answers to, exact match, case-insensitive, port ignored. Example: `interlock-demo.example.azurecontainerapps.io`. The server refuses to start in public mode without it. |
| `PORT` | `8080` in the image, else `8787` | Listening port. Under `demo/serve.py` (the image) `PORT` is used; `INTERLOCK_API_PORT` wins only when `backend/api.py` runs directly. Binds `0.0.0.0`. |
| `INTERLOCK_TRUSTED_PROXY_HOPS` | `0` | How many reverse proxies you run in front of the server. Set `1` on Azure Container Apps (its ingress appends one `X-Forwarded-For` entry). With `0` the header is ignored and the socket peer is the client. Do not set it higher than the proxies you actually have: each extra hop lets a client choose its own address. |
| `INTERLOCK_LIVE_PER_IP_HOUR` | `3` | Live runs one visitor may start in any 60 minutes. |
| `INTERLOCK_LIVE_PER_IP_DAY` | `6` | Live runs one visitor may start in one UTC day. Keep it well under `INTERLOCK_LIVE_PER_DAY`, so one visitor cannot use up the day. |
| `INTERLOCK_LIVE_PER_DAY` | `40` | Live runs all visitors together may start in one UTC day. |
| `INTERLOCK_LIVE_PER_HOUR` | `10` | Live runs all visitors together may start in any 60 minutes, so the daily budget cannot be spent in one burst. |
| `INTERLOCK_MOCK_PER_IP_HOUR` | `30` | Mock runs one visitor may start in any 60 minutes. No daily cap. |
| `INTERLOCK_MOCK_PER_HOUR` | `120` | Mock runs all visitors together may start in any 60 minutes. Mock runs share the one-run guard with live runs, so this keeps them from crowding out live runs. |
| `INTERLOCK_MAX_CONNECTIONS` | `64` | Connections handled at once. A connection past that is closed immediately. |
| `ANTHROPIC_API_KEY` | none | Needed for live runs. Set it as a platform secret. |
| `STRIPE_SECRET_KEY` | none | Needed for live runs. Must be a test-mode key (`sk_test_`); anything else is refused. Set it as a platform secret. |
| `INTERLOCK_TEMPORAL_CLI` | `/opt/temporal/temporal` in the image | Existing Temporal CLI binary for the dev server, so starting never downloads. |
| `INTERLOCK_DATA` | `/home/interlock/data` in the image | Run data (SQLite journals, leases, worker logs). Temporary; nothing needs to persist. |

`INTERLOCK_CLAIM_TTL` and `INTERLOCK_STRIPE_TIMEOUT` keep their demo defaults (15s and 10s) from `demo/serve.py`.

## Limits

- One run at a time across both demos, live or mock. A start while one is going gets HTTP 409: "a run is in progress, try again in about 30 seconds".
- A visitor is one IPv4 address, or one IPv6 /64 (a single subscriber usually holds a whole /64).
- Starting a live run counts against the visitor's hourly and daily limits and the global hourly and daily limits. Starting a mock run counts against the visitor's hourly mock limit and the global hourly mock limit. Over any of them, HTTP 429 with a message naming the limit. The page shows it in its notice area.
- The global caps can be used up on purpose: a handful of addresses (or IPv6 /64s) can take the live runs for an hour, and by repeating that, for the UTC day. Spend stays capped, and mock runs keep working. The global hourly cap spreads the damage out; it does not prevent it.
- The server keeps the last 50 runs in memory and drops older finished ones; polling a dropped run answers 404.
- A start that fails (bad request, busy, missing keys) does not use up a slot.
- Counts live in the server's memory: a restart resets them, and each replica counts on its own. Run one replica so the one-run guard and the daily cap mean what they say.
- Polling a run and loading pages are not limited. A connection that sends nothing for 30 seconds is dropped, and at most `INTERLOCK_MAX_CONNECTIONS` are handled at once. There is no deadline for a whole request, so a client that trickles bytes can hold a connection; run behind an ingress that buffers requests (Azure Container Apps' does).

## What is public and what stays on the server

Public (anyone who can reach the host):

- `GET /`, `/demo/standalone`, `/demo`: the pages.
- `GET /demo/standalone/info`, `/demo/info`: scenarios, the model name, timing settings, whether live runs are available, and the names (never values) of missing settings.
- `POST /demo/standalone/runs`, `/demo/runs`: start a run, rate-limited as above.
- `GET /demo/standalone/runs/{id}/{n}`, `/demo/runs/{id}/{n}`: a run's events. These include Stripe test-mode object ids (`pi_`, `re_`) and receipts.
- `GET /health`: whether Temporal is connected.
- `GET /healthz`: `{"ok": true}`, for platform probes. Answers any Host header and touches neither Stripe nor the model.

Off in public mode: `/cases` and everything under it (they create Stripe test payments with no limit). Demo runs call that code in-process, not over HTTP.

Server-side only: `ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`, the Temporal dev server and its UI (not started in public mode), worker processes and their logs, and run data under `INTERLOCK_DATA`.

## Request checks and headers in public mode

- `Host` must be in `INTERLOCK_ALLOWED_HOSTS`, else 403 (except `/healthz`).
- A POST needs `Content-Type: application/json`, and if the browser sends `Origin` it must be `https://` plus that host, else 403.
- Errors never carry exception text or secrets: an unexpected failure answers `{"error": "internal error"}`, a Stripe failure `{"error": "Stripe test mode returned an error"}`, a failed column in a run names only the exception type, and a failed Temporal workflow or refund attempt shows as "an error (details are in the server log)". Details go to the server log.
- Every response has `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. Pages have a `Content-Security-Policy` of `default-src 'self'`, the page's one inline script allowed by its SHA-256 hash, inline styles allowed, `connect-src 'self'`, `frame-ancestors 'none'`. Links out to the Stripe dashboard and GitHub are ordinary navigation, which CSP does not restrict. JSON responses have `default-src 'none'`.

## Azure Container Apps

- Ingress: external, target port 8080, HTTPS only.
- Environment: `INTERLOCK_ALLOWED_HOSTS` set to the app's hostname (and any custom domain), `INTERLOCK_TRUSTED_PROXY_HOPS=1`.
- Secrets: `ANTHROPIC_API_KEY` and `STRIPE_SECRET_KEY` as Container Apps secrets referenced by environment variables. Never bake them into the image.
- Health probe: HTTP GET `/healthz` on 8080.
- Scale: minimum and maximum 1 replica.
