# The hosted live demo: demo/serve.py in public mode. Settings, limits and what is public: docs/deploy.md.
#   docker build -t interlock-demo .
#   docker run --rm -p 8080:8080 -e INTERLOCK_ALLOWED_HOSTS=localhost interlock-demo     # mock only: no keys
FROM python:3.12-slim

ARG TEMPORALIO_VERSION=1.32.0
ARG TEMPORAL_CLI_VERSION=1.4.1
ARG TARGETARCH

# temporalio is the Temporal demo's only dependency. The Temporal CLI (its dev server) is fetched here so a start never
# downloads anything; if it cannot run, serve.py marks the Temporal demo unavailable and serves the standalone demo.
RUN pip install --no-cache-dir "temporalio==${TEMPORALIO_VERSION}" \
 && python -c "import io, sys, tarfile, urllib.request; \
url = 'https://temporal.download/cli/archive/v%s?platform=linux&arch=%s' % (sys.argv[1], sys.argv[2] or 'amd64'); \
req = urllib.request.Request(url, headers={'User-Agent': 'interlock-docker-build'}); \
tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(req, timeout=300).read())).extract('temporal', '/opt/temporal', filter='data')" \
    "${TEMPORAL_CLI_VERSION}" "${TARGETARCH}" \
 && /opt/temporal/temporal --version \
 && useradd --create-home --uid 10001 interlock

WORKDIR /app
COPY . /app
USER interlock

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    INTERLOCK_PUBLIC=1 PORT=8080 \
    INTERLOCK_DATA=/home/interlock/data \
    INTERLOCK_TEMPORAL_CLI=/opt/temporal/temporal
EXPOSE 8080
CMD ["python", "demo/serve.py"]
