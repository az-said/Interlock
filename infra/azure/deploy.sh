#!/usr/bin/env bash
# Deploy the public Interlock demo to Azure Container Apps. Run from the repo root.
#   ANTHROPIC_API_KEY=... STRIPE_SECRET_KEY=sk_test_... infra/azure/deploy.sh [--dry-run]
# See infra/azure/README.md for every override.
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

SUBSCRIPTION="${AZURE_SUBSCRIPTION:-Azure subscription 1}"
LOCATION="${AZURE_LOCATION:-eastus}"
RG="${AZURE_RESOURCE_GROUP:-interlock-demo-rg}"
APP="${AZURE_APP_NAME:-interlock-demo}"
ENV_NAME="${AZURE_CONTAINERAPPS_ENV:-interlock-demo-env}"
LOGS="${AZURE_LOG_WORKSPACE:-interlock-demo-logs}"
IDENTITY="${AZURE_PULL_IDENTITY:-interlock-demo-pull}"
# Fixed, not overridable: ingress, probes and the container PORT env must agree with what demo/serve.py listens on.
PORT=8787
IMAGE_REPO="interlock-demo"

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set in the environment}"
: "${STRIPE_SECRET_KEY:?STRIPE_SECRET_KEY must be set in the environment}"
case "$STRIPE_SECRET_KEY" in
  sk_test_*) ;;
  *) echo "refusing: STRIPE_SECRET_KEY is not a test mode key (must start with sk_test_)" >&2; exit 1 ;;
esac

SECRETS=("$ANTHROPIC_API_KEY" "$STRIPE_SECRET_KEY")
redact() {
  local s="$1" v
  for v in "${SECRETS[@]}"; do [ -n "$v" ] && s="${s//"$v"/<redacted>}"; done
  printf '%s\n' "$s"
}
# Mutating az call: printed (redacted) in dry run, executed otherwise. Output goes to /dev/null so
# nothing az echoes back (secrets, keys) reaches the terminal.
run() {
  if [ "$DRY_RUN" = 1 ]; then redact "+ $*"; else "$@" >/dev/null; fi
}
# Read-only az query. In dry run it prints the command and returns the placeholder in $1.
query() {
  local placeholder="$1"; shift
  if [ "$DRY_RUN" = 1 ]; then redact "+ $*" >&2; printf '%s\n' "$placeholder"; else "$@"; fi
}
exists() { [ "$DRY_RUN" = 0 ] && "$@" >/dev/null 2>&1; }

# Build context: committed files only (git archive HEAD), so ignored local secrets and demo state never reach ACR.
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(pwd -P)" ] || { echo "run from the repo root" >&2; exit 1; }
CTX="$(mktemp -d)"
BODY="$(mktemp)"
chmod 600 "$BODY"
trap 'rm -rf "$CTX" "$BODY"' EXIT
git archive HEAD | tar -x -C "$CTX"
[ -f "$CTX/Dockerfile" ] || [ "$DRY_RUN" = 1 ] || { echo "no committed Dockerfile at the repo root" >&2; exit 1; }

# Rate limits: the exact names public mode reads in backend/api.py. Unset ones are not sent, so the server's own
# defaults apply; set any of them in your environment to override.
LIMIT_NAMES="INTERLOCK_LIVE_PER_IP_HOUR INTERLOCK_LIVE_PER_DAY INTERLOCK_MOCK_PER_IP_HOUR"
RATE_NAMES=""
for name in $LIMIT_NAMES; do if [ -n "${!name:-}" ]; then RATE_NAMES="$RATE_NAMES$name"$'\n'; fi; done

# Every INTERLOCK_* name the app gets or relies on must appear as a quoted string literal in committed .py code under
# backend/ or demo/. Whole names only, so a comment, README or a longer name does not count; a misspelled name would
# otherwise silently leave the public demo without its host check or rate limits.
MISSING=""
for name in INTERLOCK_PUBLIC INTERLOCK_ALLOWED_HOSTS INTERLOCK_TRUSTED_PROXY_HOPS $LIMIT_NAMES; do
  grep -rqE --include='*.py' "[\"']${name}[\"']" "$CTX/backend" "$CTX/demo" 2>/dev/null || MISSING="$MISSING $name"
done
if [ -n "$MISSING" ]; then
  if [ "$DRY_RUN" = 1 ]; then echo "warning: not read by backend/ or demo/:$MISSING (a real run refuses)" >&2
  else echo "refusing: not read by backend/ or demo/:$MISSING" >&2; exit 1; fi
fi

status() { echo "== $*" >&2; }

run az account set --subscription "$SUBSCRIPTION"
SUB_ID="$(query 00000000-0000-0000-0000-000000000000 az account show --query id -o tsv)"
# ACR names are global: derive one from the subscription id so reruns reuse the same registry.
ACR="${AZURE_ACR_NAME:-interlockdemo$(printf '%s' "$SUB_ID" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-10)}"
# Unique per run: a rerun from the same commit still changes the template, so Container Apps makes a new revision.
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M%S)}"

status "resource group $RG in $LOCATION"
# An existing group keeps its region; resources below still go to $LOCATION (az group create errors on a mismatch).
exists az group show -n "$RG" || run az group create -n "$RG" -l "$LOCATION"

status "container registry $ACR"
exists az acr show -n "$ACR" -g "$RG" || run az acr create -n "$ACR" -g "$RG" -l "$LOCATION" --sku Basic --admin-enabled false
ACR_ID="$(query "/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.ContainerRegistry/registries/$ACR" \
  az acr show -n "$ACR" -g "$RG" --query id -o tsv)"

status "pull identity $IDENTITY"
exists az identity show -n "$IDENTITY" -g "$RG" || run az identity create -n "$IDENTITY" -g "$RG" -l "$LOCATION"
IDENTITY_ID="$(query "/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.ManagedIdentity/userAssignedIdentities/$IDENTITY" \
  az identity show -n "$IDENTITY" -g "$RG" --query id -o tsv)"
PRINCIPAL_ID="$(query 00000000-0000-0000-0000-000000000001 az identity show -n "$IDENTITY" -g "$RG" --query principalId -o tsv)"
if [ "$DRY_RUN" = 1 ] || [ -z "$(az role assignment list --assignee "$PRINCIPAL_ID" --scope "$ACR_ID" --role AcrPull --query '[0].id' -o tsv)" ]; then
  run az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
    --role AcrPull --scope "$ACR_ID"
fi

status "image $ACR.azurecr.io/$IMAGE_REPO:$TAG (remote build)"
if [ "$DRY_RUN" = 1 ]; then redact "+ az acr build -r $ACR -t $IMAGE_REPO:$TAG -f Dockerfile <git archive HEAD>"
else az acr build -r "$ACR" -t "$IMAGE_REPO:$TAG" -f Dockerfile "$CTX" --no-logs -o none; fi
IMAGE="$ACR.azurecr.io/$IMAGE_REPO:$TAG"

status "log analytics workspace $LOGS"
exists az monitor log-analytics workspace show -n "$LOGS" -g "$RG" ||
  run az monitor log-analytics workspace create -n "$LOGS" -g "$RG" -l "$LOCATION"

status "container apps environment $ENV_NAME"
# A failed create (for example regional capacity) leaves an environment that exists but cannot host apps: replace it.
if exists az containerapp env show -n "$ENV_NAME" -g "$RG" &&
   [ "$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.provisioningState -o tsv)" != Succeeded ]; then
  status "environment $ENV_NAME is not Succeeded, deleting it"
  run az containerapp env delete -n "$ENV_NAME" -g "$RG" --yes
fi
if ! exists az containerapp env show -n "$ENV_NAME" -g "$RG"; then
  LOGS_ID="$(query "<workspace-customer-id>" az monitor log-analytics workspace show -n "$LOGS" -g "$RG" --query customerId -o tsv)"
  LOGS_KEY="$(query "<workspace-shared-key>" az monitor log-analytics workspace get-shared-keys -n "$LOGS" -g "$RG" --query primarySharedKey -o tsv)"
  SECRETS+=("$LOGS_KEY")
  [ "$DRY_RUN" = 1 ] && LOGS_KEY="<redacted>"
  run az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" --logs-workspace-id "$LOGS_ID" --logs-workspace-key "$LOGS_KEY"
fi
ENV_ID="$(query "/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.App/managedEnvironments/$ENV_NAME" \
  az containerapp env show -n "$ENV_NAME" -g "$RG" --query id -o tsv)"
DOMAIN="$(query "<env-default-domain>" az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.defaultDomain -o tsv)"

# The app goes in the environment's region, whatever AZURE_LOCATION says on this run.
ENV_LOCATION="$(query "$LOCATION" az containerapp env show -n "$ENV_NAME" -g "$RG" --query location -o tsv)"

render() {  # $1 = allowed host. JSON app spec; secrets and rate limits are read from the environment, never argv.
  ALLOWED_HOST="$1" ENV_LOCATION="$ENV_LOCATION" IDENTITY_ID="$IDENTITY_ID" ENV_ID="$ENV_ID" ACR="$ACR" APP="$APP" \
  IMAGE="$IMAGE" PORT="$PORT" RATE_NAMES="$RATE_NAMES" \
  ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" STRIPE_SECRET_KEY="$STRIPE_SECRET_KEY" python3 - <<'PY'
import json, os
e = os.environ
port = int(e["PORT"])
env = [{"name": "ANTHROPIC_API_KEY", "secretRef": "anthropic-api-key"},
       {"name": "STRIPE_SECRET_KEY", "secretRef": "stripe-secret-key"},
       {"name": "PORT", "value": str(port)},
       {"name": "INTERLOCK_PUBLIC", "value": "1"},
       {"name": "INTERLOCK_ALLOWED_HOSTS", "value": e["ALLOWED_HOST"]},
       {"name": "INTERLOCK_TRUSTED_PROXY_HOPS", "value": "1"}]
env += [{"name": n, "value": e[n]} for n in e["RATE_NAMES"].split()]
print(json.dumps({
    "location": e["ENV_LOCATION"].replace(" ", "").lower(),
    "identity": {"type": "UserAssigned", "userAssignedIdentities": {e["IDENTITY_ID"]: {}}},
    "properties": {
        "managedEnvironmentId": e["ENV_ID"],
        "configuration": {
            "activeRevisionsMode": "Single",
            "ingress": {"external": True, "targetPort": port, "transport": "auto"},
            "registries": [{"server": e["ACR"] + ".azurecr.io", "identity": e["IDENTITY_ID"]}],
            "secrets": [{"name": "anthropic-api-key", "value": e["ANTHROPIC_API_KEY"]},
                        {"name": "stripe-secret-key", "value": e["STRIPE_SECRET_KEY"]}]},
        "template": {
            "scale": {"minReplicas": 1, "maxReplicas": 1},
            "containers": [{
                "name": e["APP"], "image": e["IMAGE"], "resources": {"cpu": 2.0, "memory": "4Gi"}, "env": env,
                "probes": [{"type": t, "httpGet": {"path": "/healthz", "port": port}, "periodSeconds": 10}
                           for t in ("Liveness", "Readiness")]}]}}}, indent=2))
PY
}

# Plain ARM PUT (create or replace) at a stable API version. az containerapp create/update --yaml goes through the
# extension's preview API, which rejected this spec with a 400 on the first live deploy.
APP_URL="https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.App/containerApps/$APP?api-version=2024-03-01"
apply() {  # $1 = allowed host
  render "$1" > "$BODY"
  if [ "$DRY_RUN" = 1 ]; then
    redact "$(printf '+ az rest --method put --url %s --body @<file>:\n%s' "$APP_URL" "$(cat "$BODY")")"
    return
  fi
  az rest --method put --url "$APP_URL" --body "@$BODY" -o none
  local state="" i
  for i in $(seq 120); do  # the PUT returns before provisioning ends; wait up to 10 minutes
    state="$(az containerapp show -n "$APP" -g "$RG" --query properties.provisioningState -o tsv)"
    case "$state" in
      Succeeded) return ;;
      Failed|Canceled) echo "container app provisioning ended $state" >&2; exit 1 ;;
    esac
    sleep 5
  done
  echo "container app provisioning still ${state:-unknown} after 10 minutes" >&2; exit 1
}

status "container app $APP"
EXPECTED="$APP.$DOMAIN"
apply "$EXPECTED"
FQDN="$(query "$EXPECTED" az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
[ -n "$FQDN" ] || { echo "ingress FQDN is empty; not updating INTERLOCK_ALLOWED_HOSTS" >&2; exit 1; }
if [ "$FQDN" != "$EXPECTED" ]; then
  status "ingress FQDN is $FQDN, updating INTERLOCK_ALLOWED_HOSTS"
  apply "$FQDN"
fi

REVISION="$(query "<revision>" az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)"
status "done: image $IMAGE, revision $REVISION, 1 replica"
echo "https://$FQDN"
