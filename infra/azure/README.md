# Azure deployment for the public demo

`deploy.sh` puts the standalone demo on Azure Container Apps. It creates what is missing and reuses what exists, so
running it again rolls out a new image.

## Before you run it

- `az login`, with access to the subscription named `Azure subscription 1` (override with `AZURE_SUBSCRIPTION`).
- The `containerapp` az extension installed and the `Microsoft.App` provider registered.
- A `Dockerfile` at the repo root. The image is built remotely with `az acr build`; local Docker is not needed.
- `ANTHROPIC_API_KEY` and `STRIPE_SECRET_KEY` in your shell environment. The Stripe key must start with `sk_test_`;
  the script refuses anything else.

## Run

```bash
infra/azure/deploy.sh --dry-run   # print the az commands and app YAML, secrets redacted; creates nothing
infra/azure/deploy.sh             # deploy; prints status lines and the public URL
```

The dry run makes no az calls, so it works without az installed or logged in. IDs and the environment domain show as
placeholders.

## What it creates

| Resource | Default name | Override |
| --- | --- | --- |
| Resource group | `interlock-demo-rg` | `AZURE_RESOURCE_GROUP` |
| Container registry (Basic) | `interlockdemo` + first 10 hex of sha256(subscription id) | `AZURE_ACR_NAME` |
| User-assigned identity with AcrPull on the registry | `interlock-demo-pull` | `AZURE_PULL_IDENTITY` |
| Log Analytics workspace | `interlock-demo-logs` | `AZURE_LOG_WORKSPACE` |
| Container Apps environment | `interlock-demo-env` | `AZURE_CONTAINERAPPS_ENV` |
| Container app | `interlock-demo` | `AZURE_APP_NAME` |

Region is `eastus` unless `AZURE_LOCATION` is set. The image tag is the short git commit unless `IMAGE_TAG` is set.

## The container app

- External ingress on the container port (`INTERLOCK_PORT`, default 8787).
- Exactly one replica (min 1, max 1). The demo keeps its state on local disk, so it must not scale out.
- 2 vCPU and 4 GiB.
- Liveness and readiness probes on `GET /healthz`.
- Pulls from the registry with the user-assigned identity; the registry admin account stays off.
- `ANTHROPIC_API_KEY` and `STRIPE_SECRET_KEY` are Container Apps secrets, exposed to the container only through
  `secretRef`. The app spec is written to a mode 600 temp file that is deleted on exit, and az output is discarded
  so nothing it echoes back reaches the terminal.
- `INTERLOCK_PUBLIC=1`, `INTERLOCK_TRUSTED_PROXY_HOPS=1`, and `INTERLOCK_ALLOWED_HOSTS` set to the app's FQDN. The
  script predicts the FQDN from the environment domain, reads the real one after the app is created, and applies the
  spec again if they differ.
- Rate-limit defaults are set in the script. Any `INTERLOCK_RATE_*` variable in your environment is passed through to
  the container, so the names must match what the server reads.

## Tearing it down

```bash
az group delete -n interlock-demo-rg
```
