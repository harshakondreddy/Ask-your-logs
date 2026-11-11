# ask-your-logs

> **Status: personal R&D / proof of concept — under active development, not production software.**
> It has not been deployed to production. Use it with synthetic or approved logs only.

`ask-your-logs` is a small FastAPI service that reads existing Kubernetes and application logs from Elasticsearch, applies best-effort redaction of secrets and personal data, and asks a configurable LLM provider (Gemini, OpenAI, Azure OpenAI, or Ollama) to summarize likely issues in plain English, without changing an existing EFK stack.

## What it does

- Leaves the existing Fluent Bit -> Elasticsearch -> Kibana pipeline untouched.
- Adds a small HTTP API and browser UI for log-question workflows.
- Pulls a bounded set of recent logs from Elasticsearch.
- Extracts a few useful fields instead of sending full raw documents.
- Redacts common secrets and personal data (best-effort) from every field placed in the prompt.
- Returns a structured analysis (severity, confidence, status, main issue, impact, next action).

## Architecture

```text
Existing:
Fluent Bit DaemonSet -> Elasticsearch -> Kibana

Added:
Browser UI / API client -> ask-your-logs -> Elasticsearch (read-only query)
                                         -> LLM provider selected by LLM_PROVIDER:
                                              gemini | openai | azure_openai | ollama
```

Ollama keeps all data inside your own network. The other three providers send the (redacted) prompt to an external API.

## Endpoints

- Browser UI: `GET /`
- Swagger API docs: `GET /docs`
- Health: `GET /health`
- Main API endpoint: `POST /ask`

### `POST /ask`

When `API_KEY` is set, every request must send it in the `X-API-Key` header. Otherwise the server returns `401`. The browser UI has an API key field for this. `/health` never needs a key.

Request body fields:

- `question` required
- `namespace` optional
- `app` optional (matched against `component_name` / `component_class`)
- `minutes` optional, default `30`, valid range `1..1440`
- `max_logs` optional, default `150`, capped by `MAX_LOGS_LIMIT`

Response shape:

```json
{
  "answer": "...",
  "logs_used": 87,
  "time_window_minutes": 30,
  "namespace": "default",
  "app": "my-app",
  "elasticsearch_index": "logs-*",
  "llm_provider": "ollama"
}
```

If no logs match, `answer` is `"No matching logs were found for the given filters/time window."` and `logs_used` is `0`.

## Prerequisites

- Python 3.11+
- Network access to Elasticsearch from where the service runs
- A dedicated, read-only Elasticsearch user (if auth is enabled)
- One LLM provider: a Gemini/OpenAI/Azure OpenAI key, or an Ollama endpoint

## Configuration

All settings are environment variables (see `app/config.py`).

| Variable | Default | Sensitive |
|---|---|---|
| `ELASTICSEARCH_URL` | `http://elasticsearch.logging.svc.cluster.local:9200` | |
| `ELASTICSEARCH_USERNAME` | — | yes |
| `ELASTICSEARCH_PASSWORD` | — | yes |
| `ELASTICSEARCH_INDEX` | `logs-*` | |
| `ELASTICSEARCH_TIMESTAMP_FIELD` | `@timestamp` | |
| `ELASTICSEARCH_VERIFY_CERTS` | `true` | |
| `ELASTICSEARCH_CA_CERT_PATH` | — (system CAs) | |
| `LLM_PROVIDER` | `gemini` (`gemini`, `openai`, `azure_openai`, `ollama`) | |
| `GEMINI_API_KEY` | — | yes |
| `GEMINI_MODEL` | `gemini-flash-latest` | |
| `OPENAI_API_KEY` | — | yes |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `AZURE_OPENAI_API_KEY` | — | yes |
| `AZURE_OPENAI_ENDPOINT` | — | |
| `AZURE_OPENAI_DEPLOYMENT` | — | |
| `AZURE_OPENAI_API_VERSION` | `2024-02-01` | |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | |
| `OLLAMA_MODEL` | `gemma3:4b` | |
| `OLLAMA_TIMEOUT_SECONDS` | `600` | |
| `API_KEY` | — (auth off) | yes |
| `MAX_LOGS_LIMIT` | `330` | |
| `REQUEST_TIMEOUT_SECONDS` | `30` | |

TLS: certificate verification is **on** by default. If Elasticsearch uses a private CA, mount that CA bundle and set `ELASTICSEARCH_CA_CERT_PATH`. The certificate must match the hostname in `ELASTICSEARCH_URL`. Set `ELASTICSEARCH_VERIFY_CERTS=false` only for an isolated local test cluster.

Switching providers needs only environment variable changes, no code changes.

## Local run

Bind to loopback for local use. Set `API_KEY` if anyone else can reach the port.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

export ELASTICSEARCH_URL="https://localhost:9200"
export ELASTICSEARCH_INDEX="logs-*"
export ELASTICSEARCH_CA_CERT_PATH="/path/to/ca.crt"
export LLM_PROVIDER="ollama"
export OLLAMA_BASE_URL="http://127.0.0.1:11434"

uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Other providers:

```bash
# Gemini
export LLM_PROVIDER="gemini" GEMINI_API_KEY="{{ GEMINI_API_KEY }}"
# OpenAI
export LLM_PROVIDER="openai" OPENAI_API_KEY="{{ OPENAI_API_KEY }}"
# Azure OpenAI
export LLM_PROVIDER="azure_openai" AZURE_OPENAI_API_KEY="{{ AZURE_OPENAI_API_KEY }}" \
       AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/" AZURE_OPENAI_DEPLOYMENT="<deployment>"
```

Test request:

```bash
curl -X POST http://127.0.0.1:8080/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d @sample-requests/ask.json
```

## Tests

```bash
pytest -q
```

Tests cover redaction (plain `key=value`, quoted JSON keys, nested JSON, auth headers, URL credentials, JWTs, emails, IPs, private keys), prompt construction, API-key auth, and the TLS default. All test data is synthetic.

## Docker build

```bash
docker build -t <registry>/ask-your-logs:<tag> .
docker push <registry>/ask-your-logs:<tag>
```

## Kubernetes deployment

Manifests in `k8s/` are templates. Values in double braces, such as `{{ ELASTICSEARCH_PASSWORD }}`, are placeholders. `scripts/render-manifest.sh` replaces each with the environment variable of the same name and fails if any is unset. Rendered output (`k8s/*.rendered.yaml`, `k8s/secret.yaml`) is git-ignored. Never commit it.

| File | Purpose |
|---|---|
| `k8s/namespace.yaml` | Optional namespace |
| `k8s/secret.example.yaml` | Template for `ask-your-logs-secret` (Elasticsearch credentials, LLM keys) |
| `k8s/deployment.single-pod.yaml` | Deployment + ClusterIP Service, inline non-secret config, secrets via `secretKeyRef` |
| `k8s/configmap.yaml` + `k8s/deployment.yaml` + `k8s/service.yaml` | Alternative layout using `envFrom` ConfigMap + Secret |
| `k8s/networkpolicy.yaml` | Example ingress/egress restriction |

```bash
NS=ask-your-logs
kubectl apply -f k8s/namespace.yaml

# 1. Secret (credentials never go in the Deployment or ConfigMap)
export API_KEY="$(openssl rand -hex 32)" \
       ELASTICSEARCH_USERNAME=... ELASTICSEARCH_PASSWORD=... \
       GEMINI_API_KEY= OPENAI_API_KEY= AZURE_OPENAI_API_KEY=
scripts/render-manifest.sh k8s/secret.example.yaml | kubectl -n "$NS" apply -f -

# 2. Workload
export IMAGE_REGISTRY=<registry> IMAGE_TAG=<tag> IMAGE_PULL_SECRET=<pull-secret-name> \
       ELASTICSEARCH_URL=https://<es-host>:9200 ELASTICSEARCH_INDEX='logs-*' \
       ELASTICSEARCH_CA_CERT_PATH= OLLAMA_BASE_URL=http://<ollama-host>:11434 \
       AZURE_OPENAI_ENDPOINT= AZURE_OPENAI_DEPLOYMENT=
scripts/render-manifest.sh k8s/deployment.single-pod.yaml | kubectl -n "$NS" apply -f -

# 3. Optional network policy (same namespace as the workload)
kubectl -n "$NS" apply -f k8s/networkpolicy.yaml

# 4. Access (Service is ClusterIP)
kubectl -n "$NS" port-forward svc/ask-your-logs 8080:8080
```

Pass the values through your shell, a CI secret store, or an external secrets operator. Don't write them into tracked files.

## Elasticsearch query behavior

- Filters by time window using `ELASTICSEARCH_TIMESTAMP_FIELD` (default `@timestamp`).
- Applies the `app` filter against `component_name` / `component_class`.
- Searches `component_message`, `message`, `log`, `msg`.
- Boosts ERROR/WARN levels, error-like terms and the question text.
- Sorts by relevance, then newest first.

## Security notes and limitations

- **Authentication is a single shared API key** (`API_KEY`, sent as `X-API-Key`). The Kubernetes manifest requires it. Leaving it unset locally disables auth, and the server logs a warning. There are no per-user identities, scopes or audit trail yet. Every key holder can query any log the server's Elasticsearch user can read. Keep the Service as ClusterIP. If you put it behind an ingress, use TLS so the key isn't sent in clear text.
- **Redaction is best-effort.** It uses key-name and regex matching, plus recursive redaction for JSON messages. It will miss formats it hasn't seen. Don't treat it as making real production data safe.
- External LLM providers (Gemini, OpenAI, Azure OpenAI) receive the redacted prompt. Get approval from your security and compliance owners before using real logs. Prefer Ollama for anything sensitive.
- Use a dedicated Elasticsearch user with read-only access to the log indices only.
- Keep TLS verification on.
- Results depend on the shape of logs indexed by Fluent Bit. Capped context can omit relevant evidence.

## Roadmap

- Per-user authentication (OIDC) and audit logging on `/ask`
- Server-side index/namespace scoping per caller
- Query templates for common Kubernetes failure modes
- Async job handling for large searches
- Elasticsearch field discovery
