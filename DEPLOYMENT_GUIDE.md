# Ask Your Logs - Deployment Guide

> Personal R&D / proof of concept. Not production software. See the security notes in `README.md` before running it against real logs.

## Table of Contents
1. [Local Development Setup](#local-development-setup)
2. [Code Changes and Development](#code-changes-and-development)
3. [Docker Build and Push](#docker-build-and-push)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Exposing Beyond the Cluster](#exposing-beyond-the-cluster)

Placeholders in double braces, such as `{{ ELASTICSEARCH_PASSWORD }}`, mark values you supply yourself. Never commit real values.

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Docker (for containerization)
- kubectl (for Kubernetes operations)

### Environment Setup

```bash
cd ask-your-logs
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Environment Configuration

Create a local `.env` file. It is git-ignored; keep it that way.

```bash
cat > .env << 'EOF'
ELASTICSEARCH_URL=https://localhost:9200
ELASTICSEARCH_INDEX=logs-*
ELASTICSEARCH_TIMESTAMP_FIELD=@timestamp
ELASTICSEARCH_VERIFY_CERTS=true
ELASTICSEARCH_CA_CERT_PATH=/path/to/ca.crt
ELASTICSEARCH_USERNAME={{ ELASTICSEARCH_USERNAME }}
ELASTICSEARCH_PASSWORD={{ ELASTICSEARCH_PASSWORD }}
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma3:4b
OLLAMA_TIMEOUT_SECONDS=600
GEMINI_API_KEY=
OPENAI_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
API_KEY={{ API_KEY }}
MAX_LOGS_LIMIT=330
REQUEST_TIMEOUT_SECONDS=30
EOF
```

### Running Locally

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
# Browser UI: http://127.0.0.1:8080
# API docs:   http://127.0.0.1:8080/docs
# Health:     http://127.0.0.1:8080/health
```

### Running Tests

```bash
pytest -q

curl http://127.0.0.1:8080/health
curl -X POST http://127.0.0.1:8080/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"question": "Show errors from last 30 minutes", "app": "my-app", "minutes": 30, "max_logs": 100}'
```

---

## Code Changes and Development

### Project Structure

```
ask-your-logs/
├── app/
│   ├── main.py                  # FastAPI app, browser UI, endpoints
│   ├── config.py                # Environment configuration (Settings)
│   ├── models.py                # Request/response models
│   ├── elasticsearch_client.py  # Elasticsearch query + field extraction
│   ├── llm_client.py            # LLM provider factory
│   ├── gemini_client.py         # Google Gemini
│   ├── openai_client.py         # OpenAI and Azure OpenAI
│   ├── ollama_client.py         # Ollama
│   ├── prompt_builder.py        # Prompt + answer contract (redacts every field)
│   ├── redaction.py             # Best-effort secret/PII redaction
│   └── exceptions.py
├── k8s/                         # Manifest templates (placeholders in double braces)
├── scripts/render-manifest.sh   # Fills placeholders from environment variables
├── tests/                       # pytest suite (synthetic data only)
├── requirements.txt / requirements-dev.txt
├── Dockerfile
├── README.md
└── DEPLOYMENT_GUIDE.md
```

### Common Changes

- **Configuration:** all runtime settings are environment variables in `app/config.py`. No code change needed to switch provider.
- **Elasticsearch fields:** edit `SOURCE_FIELDS`, `LOG_FIELD_CANDIDATES` and `SERVICE_FIELD_CANDIDATES` in `app/elasticsearch_client.py`.
- **Prompt:** edit `build_prompt()` in `app/prompt_builder.py`. The UI in `main.py` parses the Severity/Confidence/4-section format, so keep it in sync. Pass any new field through `redact_text()`.
- **Redaction:** add key names to `SENSITIVE_KEY_PATTERN` or patterns to `REDACTION_PATTERNS` in `app/redaction.py`, with a test in `tests/test_redaction.py`.
- **New LLM provider:** add `app/<provider>_client.py` implementing `generate_answer(prompt: str) -> str`, register it in `app/llm_client.py`, and add settings to `app/config.py`.
- **Browser UI:** edit the `INDEX_HTML` string in `app/main.py`.

---

## Docker Build and Push

```bash
docker build -t ask-your-logs:<tag> .
docker tag ask-your-logs:<tag> <registry>/ask-your-logs:<tag>
docker login <registry>          # prompts for credentials; don't put them on the command line
docker push <registry>/ask-your-logs:<tag>
```

The `Dockerfile` is a multi-stage build on `python:3.11-slim`. It runs as non-root user `appuser` (uid 10001), installs from pre-built wheels, exposes port 8080, and has a `/health` healthcheck.

---

## Kubernetes Deployment

`k8s/deployment.single-pod.yaml` contains:
- **Deployment:** 1 replica, resource limits, restricted security context (non-root, read-only root FS, no privilege escalation, all capabilities dropped), startup/readiness/liveness probes.
- **Service:** `ClusterIP` on port 8080.
- Credentials and API keys are read from Secret `ask-your-logs-secret` through `secretKeyRef`. They are never inlined. `API_KEY` is required, so the pod won't start without it.

### Steps

```bash
NS=<namespace>
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

# Image pull secret (only for a private registry)
read -rsp 'registry password: ' REGISTRY_PASSWORD; echo
kubectl -n "$NS" create secret docker-registry "{{ IMAGE_PULL_SECRET }}" \
  --docker-server=<registry> --docker-username=<user> --docker-password="$REGISTRY_PASSWORD"
unset REGISTRY_PASSWORD

# Application secret
export API_KEY="$(openssl rand -hex 32)"   # share with callers; they send it as X-API-Key
export ELASTICSEARCH_USERNAME=... ELASTICSEARCH_PASSWORD=... GEMINI_API_KEY= OPENAI_API_KEY= AZURE_OPENAI_API_KEY=
scripts/render-manifest.sh k8s/secret.example.yaml | kubectl -n "$NS" apply -f -

# Workload
export IMAGE_REGISTRY=<registry> IMAGE_TAG=<tag> IMAGE_PULL_SECRET=<pull-secret-name> \
       ELASTICSEARCH_URL=https://<es-host>:9200 ELASTICSEARCH_INDEX='logs-*' ELASTICSEARCH_CA_CERT_PATH= \
       OLLAMA_BASE_URL=http://<ollama-host>:11434 AZURE_OPENAI_ENDPOINT= AZURE_OPENAI_DEPLOYMENT=
scripts/render-manifest.sh k8s/deployment.single-pod.yaml | kubectl -n "$NS" apply -f -

# Optional network policy: apply into the SAME namespace as the workload
kubectl -n "$NS" apply -f k8s/networkpolicy.yaml
```

To use a private CA for Elasticsearch, mount the CA bundle into the pod, for example from a ConfigMap, and set `ELASTICSEARCH_CA_CERT_PATH` to the mounted path.

### Verify

```bash
kubectl -n "$NS" get deploy,pods,svc -l app=ask-your-logs
kubectl -n "$NS" logs -l app=ask-your-logs --tail=50
kubectl -n "$NS" port-forward svc/ask-your-logs 8080:8080
curl http://127.0.0.1:8080/health
```

### Updates and Rollback

```bash
kubectl -n "$NS" set image deployment/ask-your-logs ask-your-logs=<registry>/ask-your-logs:<new-tag>
kubectl -n "$NS" rollout status deployment/ask-your-logs
kubectl -n "$NS" rollout undo deployment/ask-your-logs
```

### Troubleshooting

| Symptom | Check |
|---|---|
| Pod `Pending` / `ImagePullBackOff` | `kubectl describe pod`: pull secret name, registry reachability, resources |
| `/ask` returns 401 | `X-API-Key` header, or the UI API key field, matches the `API_KEY` in the Secret |
| `CrashLoopBackOff` | `kubectl logs`: config values, Secret exists, provider key set |
| `/ask` returns 502 with a TLS error | CA bundle mounted, `ELASTICSEARCH_CA_CERT_PATH` set, cert hostname matches `ELASTICSEARCH_URL` |
| `/ask` returns 502 from the LLM | provider key, model name, Ollama reachability / NetworkPolicy egress port |
| Port-forward works but other pods can't reach it | `k8s/networkpolicy.yaml` only allows same-namespace ingress |

---

## Exposing Beyond the Cluster

`/ask` is protected only by one shared API key. There are no per-user identities or scoping. Every key holder can query any log the server's Elasticsearch user can read.

- Prefer `kubectl port-forward`, and keep the Service as `ClusterIP`.
- If you must expose it, use an Ingress or reverse proxy with **TLS** (the key is a bearer secret), restrict source networks, and rotate `API_KEY` by updating the Secret and restarting the pod.
- Document any proxy configuration with placeholders. Never use real hostnames or IPs.
