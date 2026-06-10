# ai-log-router

`ai-log-router` is an R&D-friendly FastAPI service that reads existing Kubernetes and application logs from Elasticsearch, redacts obvious secrets, and asks a configurable LLM provider (Gemini, OpenAI, Azure OpenAI, or Ollama) to summarize likely issues without changing your current EFK stack.

## What it does

- Keeps your current Fluent Bit -> Elasticsearch -> Kibana pipeline untouched.
- Adds a small HTTP API for log-question workflows.
- Pulls a bounded set of recent logs from Elasticsearch.
- Extracts useful fields instead of sending full raw documents.
- Redacts common secrets before calling Gemini.
- Returns a structured analysis response.

## Architecture

```text
Existing:
Fluent Bit DaemonSet -> Elasticsearch -> Kibana

New:
User/API -> ai-log-router -> Elasticsearch
                        -> Google Gemini API
```

If you align this with the EFK setup already present in this workspace, likely values are closer to `https://elasticsearch-client.essential:9201` and `fluent-bit-*`. The shipped manifests stay generic on purpose, so you can retarget them safely.

## Browser UI

The app now also serves a lightweight browser UI at `/` for interactive log questions.

- Browser UI: `GET /`
- Swagger API docs: `GET /docs`
- Health: `GET /health`
- Main API endpoint: `POST /ask`

Use the UI when you want a browser-based workflow. Use `/docs` or `curl` when you want raw API testing.

## API

### Health

`GET /health`

Response:

```json
{
  "status": "ok"
}
```

### Ask logs

`POST /ask`

Request body fields:

- `question` required
- `namespace` optional
- `app` optional
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
  "elasticsearch_index": "logs-*"
}
```

If no logs match, the service returns:

```json
{
  "answer": "No matching logs were found for the given filters/time window.",
  "logs_used": 0,
  "time_window_minutes": 30,
  "namespace": "default",
  "app": "my-app",
  "elasticsearch_index": "logs-*"
}
```

## Prerequisites

- Python 3.11+
- Reachability to Elasticsearch from where the service runs
- Read-only Elasticsearch credentials
- At least one LLM provider path (Gemini/OpenAI/Azure keys or an Ollama endpoint)

## Configuration

Environment variables:

- `ELASTICSEARCH_URL`
- `ELASTICSEARCH_USERNAME`
- `ELASTICSEARCH_PASSWORD`
- `ELASTICSEARCH_INDEX` default `logs-*`
- `ELASTICSEARCH_VERIFY_CERTS` default `false`
- `ELASTICSEARCH_CA_CERT_PATH`
- `LLM_PROVIDER` default `gemini` (`gemini`, `openai`, `azure_openai`, `ollama`)
- `GEMINI_API_KEY`
- `GEMINI_MODEL` default `gemini-flash-latest`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` default `gpt-4o-mini`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION` default `2024-02-01`
- `OLLAMA_BASE_URL` default `http://127.0.0.1:11434`
- `OLLAMA_MODEL` default `gemma3:4b`
- `OLLAMA_TIMEOUT_SECONDS` default `600`
- `MAX_LOGS_LIMIT` default `330`
- `REQUEST_TIMEOUT_SECONDS` default `30`

Provider behavior:

- Set `LLM_PROVIDER=gemini` to use Google Gemini.
- Set `LLM_PROVIDER=openai` to use OpenAI chat completions.
- Set `LLM_PROVIDER=azure_openai` to use Azure OpenAI chat completions.
- Set `LLM_PROVIDER=ollama` to use a local or in-cluster Ollama server.

You can switch providers by changing only environment variables. No code changes are required.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ELASTICSEARCH_URL="http://elasticsearch.logging.svc.cluster.local:9200"
export ELASTICSEARCH_INDEX="logs-*"
export LLM_PROVIDER="gemini"
export GEMINI_API_KEY="replace-me"
export GEMINI_MODEL="gemini-flash-latest"

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

OpenAI example:

```bash
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="replace-me"
export OPENAI_MODEL="gpt-4o-mini"
```

Azure OpenAI example:

```bash
export LLM_PROVIDER="azure_openai"
export AZURE_OPENAI_API_KEY="replace-me"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="your-deployment-name"
export AZURE_OPENAI_API_VERSION="2024-02-01"
```

Ollama example:

```bash
export LLM_PROVIDER="ollama"
export OLLAMA_BASE_URL="http://ollama-gemma3-4b.essential.svc.cluster.local:18080"
export OLLAMA_MODEL="gemma3:4b"
export OLLAMA_TIMEOUT_SECONDS="600"
```

Local test command:

```bash
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why is my app failing?",
    "namespace": "default",
    "app": "my-app",
    "minutes": 30,
    "max_logs": 100
  }'
```

## Docker build and push

```bash
docker build -t your-registry/ai-log-router:0.1.0 .
docker push your-registry/ai-log-router:0.1.0
```

## Kubernetes deployment (portable across environments)

```bash
kubectl apply -f k8s/namespace.yaml
kubectl -n ai-log-router apply -f k8s/configmap.yaml
kubectl -n ai-log-router apply -f k8s/deployment.single-pod.yaml
```

Why this is portable:

- `k8s/deployment.single-pod.yaml` has no hardcoded namespace, so you can deploy it to any namespace with `-n`.
- All provider and Elasticsearch runtime values are injected through `k8s/configmap.yaml`.
- Elasticsearch username/password are optional. Leave empty when the target cluster has auth disabled.
- You can migrate sensitive keys to a Secret later without changing app code.

Per-environment checklist:

- Set `ELASTICSEARCH_URL`, `ELASTICSEARCH_INDEX`, TLS options in `k8s/configmap.yaml`.
- Set `LLM_PROVIDER` and model fields in `k8s/configmap.yaml`.
- Set only required provider key fields in `k8s/configmap.yaml`.
- Set `ELASTICSEARCH_USERNAME` and `ELASTICSEARCH_PASSWORD` only if the target Elasticsearch requires auth.

Optional restrictive network policy:

```bash
kubectl apply -f k8s/networkpolicy.yaml
```

Port-forward for testing:

```bash
kubectl -n ai-log-router port-forward svc/ai-log-router 8080:8080
```

## Elasticsearch query behavior

- Filters by time window using `@timestamp` by default.
- Applies namespace filters when provided.
- Applies app filters against common Fluent Bit and Kubernetes fields.
- Searches common log fields including `message`, `log`, `msg`, and `component_message`.
- Boosts error-like terms and the user question.
- Sorts newest logs first.
- Handles missing fields by using candidate field lists.

## Security notes

- Do not hardcode secrets.
- Replace placeholders in `k8s/secret.yaml` before deploying.
- Use read-only Elasticsearch credentials.
- Logs may contain sensitive data even after regex redaction.
- External LLM usage for production logs should be approved by your security and compliance owners.
- Add authentication and authorization before using this beyond an internal POC.
- The default service type is `ClusterIP`.

## Known limitations

- Regex redaction is best-effort only.
- The service depends on the shape of logs already indexed by Fluent Bit.
- Very large or noisy result sets may still omit relevant evidence because context is intentionally capped.
- Provider-specific quotas and model limits may affect reliability.

## Next enhancements

- Add authentication and audit logging.
- Add query templates for common Kubernetes failure modes.
- Add streaming responses or async job handling for large searches.
- Add Elasticsearch field discovery and index pattern auto-detection.
- Add unit tests and optional mock mode for local development.