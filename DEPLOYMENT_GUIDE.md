# AI Log Router - Complete Deployment Guide

## Table of Contents
1. [Local Development Setup](#local-development-setup)
2. [Code Changes and Development](#code-changes-and-development)
3. [Docker Build and Push](#docker-build-and-push)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [HF Proxy Configuration](#hf-proxy-configuration)

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- pip and venv
- Docker (for containerization)
- kubectl (for Kubernetes operations)

### Python Installation and Environment Setup

```bash
# Navigate to project directory
cd /home/k8sadmin/ai-log-router

# Create virtual environment
python3.11 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python3.11 -c "from app.config import get_settings; print('Setup complete')"
```

### Environment Configuration

Create a `.env` file in the project root:

```bash
cat > .env << 'EOF'
ELASTICSEARCH_URL=http://elasticsearch.logging.svc.cluster.local:9200
ELASTICSEARCH_INDEX=logs-*
ELASTICSEARCH_TIMESTAMP_FIELD=@timestamp
ELASTICSEARCH_VERIFY_CERTS=false
ELASTICSEARCH_CA_CERT_PATH=
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=
LLM_PROVIDER=gemini
GEMINI_API_KEY=replace-with-your-key
GEMINI_MODEL=gemini-flash-latest
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2024-02-01
OLLAMA_BASE_URL=http://ollama-gemma3-4b.essential.svc.cluster.local:18080
OLLAMA_MODEL=gemma3:4b
OLLAMA_TIMEOUT_SECONDS=600
MAX_LOGS_LIMIT=330
REQUEST_TIMEOUT_SECONDS=30
EOF
```

### Running Locally

```bash
# Activate environment
source .venv/bin/activate

# Run development server
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Application will be available at:
# - Browser UI: http://localhost:8080
# - API Docs: http://localhost:8080/docs
# - Health: http://localhost:8080/health
```

### Running Tests

```bash
# Compile Python for syntax validation
python3.11 -m compileall app

# Run health check
curl http://localhost:8080/health

# Test /ask endpoint
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show errors from last 30 minutes",
    "app": "my-app",
    "minutes": 30,
    "max_logs": 100
  }'
```

---

## Code Changes and Development

### Project Structure

```
ai-log-router/
├── app/
│   ├── __init__.py              # Package initialization
│   ├── main.py                  # FastAPI application, browser UI, endpoints
│   ├── config.py                # Environment configuration (Settings class)
│   ├── models.py                # Request/Response Pydantic models
│   ├── elasticsearch_client.py   # Elasticsearch integration
│   ├── llm_client.py            # LLM provider factory
│   ├── gemini_client.py         # Google Gemini implementation
│   ├── openai_client.py         # OpenAI and Azure OpenAI implementation
│   ├── ollama_client.py         # Ollama local LLM implementation
│   ├── prompt_builder.py        # Answer contract and prompt formatting
│   ├── redaction.py             # Secret/sensitive data redaction
│   └── exceptions.py            # Custom exception classes
├── k8s/
│   ├── deployment.single-pod.yaml  # Single-pod Kubernetes deployment + service
│   └── namespace.yaml              # (Legacy - using essential namespace now)
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Multi-stage Docker build
├── README.md                    # Main documentation
└── DEPLOYMENT_GUIDE.md          # This file
```

### Making Code Changes

#### 1. Configuration Changes (No code changes needed)
All runtime configuration is injected via environment variables in `app/config.py`:

- **Elasticsearch**: URL, credentials, index, TLS settings, timestamp field
- **LLM Provider**: gemini, openai, azure_openai, or ollama
- **Timeouts**: Request and LLM-specific timeouts
- **Limits**: MAX_LOGS_LIMIT controls result set size

Example: To switch providers without code changes:
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# No code changes needed
```

#### 2. Adding New Elasticsearch Fields
Edit `app/elasticsearch_client.py`:
- Update `SOURCE_FIELDS` list to include new fields to extract
- Update `LOG_FIELD_CANDIDATES` if message is in a different field
- Update `SERVICE_FIELD_CANDIDATES` for service/component filtering

#### 3. Modifying LLM Prompt
Edit `app/prompt_builder.py`:
- `build_prompt()` function formats the system prompt
- Current contract: Severity, Confidence, 4 numbered sections
- Changing contract will affect UI parsing in `main.py`

#### 4. Adding New LLM Provider
1. Create `app/<provider>_client.py` with class implementing `generate_answer(prompt: str) -> str`
2. Update `app/llm_client.py` `create_llm_client()` to handle new provider
3. Add provider-specific env vars to `app/config.py`

#### 5. Browser UI Changes
Edit HTML/JavaScript in `app/main.py` `INDEX_HTML` string:
- `renderAnalysis()`: Parse and display analysis sections
- `suggestedMaxLogs()`: Auto-scale log limits by time window
- Form controls: Quick action buttons, preset services

### Compiling and Validating Code

```bash
# Check for Python syntax errors
python3.11 -m compileall app

# Expected output: No errors or "Listing 'app'..." messages

# Import test
python3.11 -c "from app.main import app; print('Code valid')"
```

---

## Docker Build and Push

### Building the Docker Image

```bash
# Navigate to project root
cd /home/k8sadmin/ai-log-router

# Build image (multi-stage build, optimized for size and security)
docker build -t ai-log-router:0.1.0 .

# Verify build
docker images | grep ai-log-router
# Expected: ai-log-router  0.1.0  <size: ~230MB>
```

### Dockerfile Details

The `Dockerfile` uses a **multi-stage build**:

**Stage 1: Builder**
- Base: `python:3.11-slim`
- Builds Python wheels from requirements.txt
- Discarded after build (keeps image small)

**Stage 2: Runtime**
- Base: `python:3.11-slim`
- Creates non-root user: `appuser` (uid 10001)
- Installs from pre-built wheels (no compilation)
- Sets security context: read-only filesystem, no privileges
- Exposes port 8080
- Health check: HTTP GET /health

### Registry Authentication

Extract credentials from cluster:
```bash
kubectl get secret intelligrepo -n essential -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | python3 -m json.tool
```

### Tagging and Pushing

```bash
# Tag with Honeywell Artifactory registry
docker tag ai-log-router:0.1.0 \
  igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0

# Authenticate with registry (replace password)
echo "<password>" | docker login -u hwwesuser --password-stdin \
  igs-wms-docker-stable-local.artifactory-na.honeywell.com

# Push image
docker push igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0

# Verify push
docker pull igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0
```

---

## Kubernetes Deployment

### Single File Deployment

The entire application is deployed via one manifest: `k8s/deployment.single-pod.yaml`

This YAML contains:
- **Deployment**: 1 replica, resource limits, security context, health probes
- **Service**: NodePort on port 30450 for external access

### Deployment to Essential Namespace

```bash
# Verify essential namespace exists
kubectl get namespace essential

# Create ImagePullSecret for registry access
kubectl create secret docker-registry intelligrepo \
  --docker-server=igs-wms-docker-stable-local.artifactory-na.honeywell.com \
  --docker-username=hwwesuser \
  --docker-password=<password> \
  -n essential

# Verify secret created
kubectl get secret intelligrepo -n essential

# Deploy application
kubectl apply -n essential -f k8s/deployment.single-pod.yaml

# Verify deployment
kubectl get deployment -n essential -l app=ai-log-router
kubectl get pods -n essential -l app=ai-log-router
kubectl get svc -n essential -l app=ai-log-router
```

### Deployment Manifest Structure

**Deployment Configuration:**
```yaml
spec:
  replicas: 1              # Single pod
  imagePullSecrets:        # Registry authentication
    - name: intelligrepo
  
  containers:
    image: igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0
    imagePullPolicy: IfNotPresent
    
    env:                   # All runtime configuration
      ELASTICSEARCH_URL: "http://elasticsearch.logging.svc.cluster.local:9200"
      LLM_PROVIDER: "gemini"
      # ... all other environment variables
    
    resources:
      requests: 100m CPU, 256Mi memory
      limits: 500m CPU, 512Mi memory
    
    securityContext:
      runAsNonRoot: true
      runAsUser: 10001
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
    
    probes:
      startupProbe: HTTP GET /health (30 attempts, 5s interval)
      readinessProbe: HTTP GET /health (10s initial delay)
      livenessProbe: HTTP GET /health (15s initial delay)
```

**Service Configuration:**
```yaml
spec:
  type: NodePort           # External access via node IP:port
  ports:
    - port: 8080           # Internal cluster port
      targetPort: http     # Pod port
      nodePort: 30450      # External NodePort
```

### Customizing for Different Environments

Edit `k8s/deployment.single-pod.yaml` before applying:

```yaml
# Change Elasticsearch endpoint
- name: ELASTICSEARCH_URL
  value: "http://elasticsearch.your-domain.com:9200"

# Change LLM provider and key
- name: LLM_PROVIDER
  value: "openai"
- name: OPENAI_API_KEY
  value: "sk-..."

# Change Elasticsearch credentials (if needed)
- name: ELASTICSEARCH_USERNAME
  value: "elastic-user"
- name: ELASTICSEARCH_PASSWORD
  value: "secure-password"

# Adjust resource limits for your cluster
resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### Verifying Deployment

```bash
# Check pod status
kubectl get pods -n essential -l app=ai-log-router -w

# View logs
kubectl logs -n essential -l app=ai-log-router --tail=50

# Test health endpoint
kubectl exec -n essential deployment/ai-log-router -- \
  curl http://localhost:8080/health

# Check service and NodePort
kubectl get svc -n essential -l app=ai-log-router

# Get node IPs to access via NodePort
kubectl get nodes -o wide
```

### Accessing the Application

**Cluster Internal:**
```
http://ai-log-router.essential.svc.cluster.local:8080
```

**External via NodePort:**
```
http://<node-ip>:30450
```

**Find Node IPs:**
```bash
kubectl get nodes -o wide
# Use any node's INTERNAL-IP with port 30450
```

### Scaling and Updates

```bash
# Scale to multiple replicas
kubectl scale deployment ai-log-router -n essential --replicas=3

# Update image
kubectl set image deployment/ai-log-router \
  ai-log-router=igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.2.0 \
  -n essential

# Rollback if needed
kubectl rollout undo deployment/ai-log-router -n essential

# View rollout history
kubectl rollout history deployment/ai-log-router -n essential
```

### Troubleshooting

```bash
# Pod stuck in Pending
kubectl describe pod -n essential -l app=ai-log-router
# Check: ImagePullSecret exists, resources available, node affinity

# Pod CrashLoopBackOff
kubectl logs -n essential -l app=ai-log-router
# Check: Configuration values, Elasticsearch connectivity, LLM provider key

# Service not accessible
kubectl get svc -n essential -l app=ai-log-router
# Verify: NodePort allocated, pod is running, network policies allow traffic

# Health check failing
kubectl exec -n essential deployment/ai-log-router -- \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
# Check: App logs, Elasticsearch connectivity
```

---

## HF Proxy Configuration

### HF Proxy Overview

HF Proxy (`/etc/hfproxy/hfproxy.cfg`) is a reverse proxy that routes external traffic to internal services.

### Adding New Rule for AI Log Router

Configuration file location: `/etc/hfproxy/hfproxy.cfg`

#### Step 1: Backup Current Config
```bash
sudo cp /etc/hfproxy/hfproxy.cfg /etc/hfproxy/hfproxy.cfg.backup
```

#### Step 2: Review Current Configuration
```bash
sudo cat /etc/hfproxy/hfproxy.cfg
```

#### Step 3: Add New Rule for AI Log Router

Add to `/etc/hfproxy/hfproxy.cfg`:

```
# AI Log Router - NodePort 30450
[service:ai-log-router]
listen = 0.0.0.0:8450
backend = 10.233.60.99:8080    # Use Kubernetes Service ClusterIP
# OR if using NodePort directly:
# backend = 10.11.134.31:30450  # Use any node IP with NodePort

ssl = false
timeout = 30
enable_outbound = yes
outbound_port = 8450
```

#### Step 4: Verify Syntax
```bash
sudo /path/to/hfproxy --validate /etc/hfproxy/hfproxy.cfg
```

#### Step 5: Restart HF Proxy Service
```bash
sudo systemctl restart hfproxy

# Verify service is running
sudo systemctl status hfproxy
```

#### Step 6: Test External Access
```bash
# From external host
curl http://<hfproxy-host>:8450/health

# Should return:
# {"status": "ok"}
```

### Configuration Details

- **listen**: External port where HF proxy listens (8450)
- **backend**: Internal target (Kubernetes Service ClusterIP or NodePort)
- **outbound_port**: Port used for outbound connections from proxy (8450)
- **enable_outbound**: Allow outbound traffic from this service
- **timeout**: Request timeout in seconds

### Alternative: Using Kubernetes Service ClusterIP

Get the Service ClusterIP:
```bash
kubectl get svc ai-log-router -n essential -o jsonpath='{.spec.clusterIP}'
# Output: 10.233.60.99
```

Use in HF proxy config:
```
backend = 10.233.60.99:8080  # Kubernetes Service ClusterIP + internal port
```

**Advantage**: Service handles load balancing and pod discovery
**Disadvantage**: Service must be accessible from HF proxy host

### Alternative: Using NodePort Directly

```bash
# Get any node IP
kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'
# Output: 10.11.134.31

# Get NodePort
kubectl get svc ai-log-router -n essential -o jsonpath='{.spec.ports[0].nodePort}'
# Output: 30450
```

Use in HF proxy config:
```
backend = 10.11.134.31:30450  # Node IP + NodePort
```

**Advantage**: Simpler, direct node access
**Disadvantage**: Node IP must remain stable

---

## Quick Reference

### Local Development Workflow
```bash
source .venv/bin/activate
export ELASTICSEARCH_URL="http://localhost:9200"
uvicorn app.main:app --reload
```

### Build and Deploy Workflow
```bash
docker build -t ai-log-router:0.1.0 .
docker tag ai-log-router:0.1.0 igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0
docker push igs-wms-docker-stable-local.artifactory-na.honeywell.com/ai-log-router:0.1.0
kubectl apply -n essential -f k8s/deployment.single-pod.yaml
```

### Access Points
- Local: `http://localhost:8080`
- Cluster internal: `http://ai-log-router.essential.svc.cluster.local:8080`
- NodePort: `http://<node-ip>:30450`
- HF Proxy: `http://<hfproxy-host>:8450`

---

## Support

For issues, check:
1. Application logs: `kubectl logs -n essential -l app=ai-log-router`
2. Service connectivity: `kubectl get svc,pods -n essential`
3. Configuration: Verify all env vars in deployment manifest
4. Elasticsearch access: Verify index and credentials
5. LLM provider: Verify API key and model availability
