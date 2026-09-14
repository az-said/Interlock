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
PORT="${INTERLOCK_PORT:-8787}"
IMAGE_REPO="interlock-demo"

[ -f Dockerfile ] || [ "$DRY_RUN" = 1 ] || { echo "run from the repo root (no Dockerfile here)" >&2; exit 1; }
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

status() { echo "== $*" >&2; }

run az account set --subscription "$SUBSCRIPTION"
SUB_ID="$(query 00000000-0000-0000-0000-000000000000 az account show --query id -o tsv)"
# ACR names are global: derive one from the subscription id so reruns reuse the same registry.
ACR="${AZURE_ACR_NAME:-interlockdemo$(printf '%s' "$SUB_ID" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-10)}"
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"

status "resource group $RG in $LOCATION"
run az group create -n "$RG" -l "$LOCATION"

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
if [ "$DRY_RUN" = 1 ]; then redact "+ az acr build -r $ACR -t $IMAGE_REPO:$TAG -f Dockerfile ."
else az acr build -r "$ACR" -t "$IMAGE_REPO:$TAG" -f Dockerfile . --no-logs -o none; fi
IMAGE="$ACR.azurecr.io/$IMAGE_REPO:$TAG"

status "log analytics workspace $LOGS"
exists az monitor log-analytics workspace show -n "$LOGS" -g "$RG" ||
  run az monitor log-analytics workspace create -n "$LOGS" -g "$RG" -l "$LOCATION"

status "container apps environment $ENV_NAME"
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

yaml_str() { local s="${1//\\/\\\\}"; printf '"%s"' "${s//\"/\\\"}"; }

# Rate-limit defaults for the public demo. Any INTERLOCK_RATE_* set by the caller is forwarded too.
: "${INTERLOCK_RATE_LIMIT_PER_MINUTE:=30}"
: "${INTERLOCK_RATE_LIMIT_RUNS_PER_HOUR:=20}"
export INTERLOCK_RATE_LIMIT_PER_MINUTE INTERLOCK_RATE_LIMIT_RUNS_PER_HOUR

render() {  # $1 = allowed host
  local name probe
  cat <<EOF
location: $LOCATION
identity:
  type: UserAssigned
  userAssignedIdentities:
    $(yaml_str "$IDENTITY_ID"): {}
properties:
  managedEnvironmentId: $(yaml_str "$ENV_ID")
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: $PORT
      transport: auto
    registries:
    - server: $ACR.azurecr.io
      identity: $(yaml_str "$IDENTITY_ID")
    secrets:
    - name: anthropic-api-key
      value: $(yaml_str "$ANTHROPIC_API_KEY")
    - name: stripe-secret-key
      value: $(yaml_str "$STRIPE_SECRET_KEY")
  template:
    scale:
      minReplicas: 1
      maxReplicas: 1
    containers:
    - name: $APP
      image: $IMAGE
      resources:
        cpu: 2.0
        memory: 4Gi
      env:
      - name: ANTHROPIC_API_KEY
        secretRef: anthropic-api-key
      - name: STRIPE_SECRET_KEY
        secretRef: stripe-secret-key
      - name: INTERLOCK_PUBLIC
        value: "1"
      - name: INTERLOCK_ALLOWED_HOSTS
        value: $(yaml_str "$1")
      - name: INTERLOCK_TRUSTED_PROXY_HOPS
        value: "1"
EOF
  while IFS= read -r name; do
    printf '      - name: %s\n        value: %s\n' "$name" "$(yaml_str "${!name}")"
  done < <(compgen -e | grep '^INTERLOCK_RATE_' | sort)
  printf '      probes:\n'
  for probe in Liveness Readiness; do
    printf '      - type: %s\n        httpGet:\n          path: /healthz\n          port: %s\n        periodSeconds: 10\n' "$probe" "$PORT"
  done
}

YAML="$(mktemp)"
chmod 600 "$YAML"
trap 'rm -f "$YAML"' EXIT

apply() {  # $1 = allowed host
  render "$1" > "$YAML"
  if [ "$DRY_RUN" = 1 ]; then
    redact "$(printf '+ az containerapp create|update -n %s -g %s --yaml <file>:\n%s' "$APP" "$RG" "$(cat "$YAML")")"
  elif exists az containerapp show -n "$APP" -g "$RG"; then
    az containerapp update -n "$APP" -g "$RG" --yaml "$YAML" -o none
  else
    az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" --yaml "$YAML" -o none
  fi
}

status "container app $APP"
EXPECTED="$APP.$DOMAIN"
apply "$EXPECTED"
FQDN="$(query "$EXPECTED" az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
if [ "$FQDN" != "$EXPECTED" ]; then
  status "ingress FQDN is $FQDN, updating INTERLOCK_ALLOWED_HOSTS"
  apply "$FQDN"
fi

REVISION="$(query "<revision>" az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)"
status "done: image $IMAGE, revision $REVISION, 1 replica"
echo "https://$FQDN"
