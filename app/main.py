import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.elasticsearch_client import ElasticsearchLogClient, ElasticsearchQueryError
from app.exceptions import LLMClientError
from app.llm_client import create_llm_client
from app.models import AskRequest, AskResponse, HealthResponse
from app.prompt_builder import build_prompt
from app.redaction import redact_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not get_settings().api_key:
        LOGGER.warning("API_KEY is not set: /ask is unauthenticated. Use loopback or port-forward only.")
    yield


app = FastAPI(title="ask-your-logs", version="0.1.0", lifespan=lifespan)


def sanitize_answer_for_end_users(answer: str) -> str:
    filtered_lines: list[str] = []
    for line in answer.splitlines():
        lowered = line.lower()
        if "kubectl" in lowered or "kubernetes" in lowered:
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines).strip() or answer

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ask-your-logs</title>
    <style>
        :root {
            color-scheme: light;
            --bg: #f2efe8;
            --panel: rgba(255, 252, 245, 0.92);
            --panel-strong: #fffdfa;
            --ink: #1f1a14;
            --muted: #6d6357;
            --line: rgba(48, 34, 18, 0.12);
            --accent: #0d6c63;
            --accent-2: #d77a2a;
            --error: #b23a2b;
            --shadow: 0 24px 70px rgba(31, 26, 20, 0.12);
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: "Segoe UI", "Helvetica Neue", sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top left, rgba(215, 122, 42, 0.14), transparent 28%),
                radial-gradient(circle at top right, rgba(13, 108, 99, 0.18), transparent 26%),
                linear-gradient(180deg, #f7f4ee 0%, var(--bg) 100%);
            min-height: 100vh;
        }

        .shell {
            max-width: 1200px;
            margin: 0 auto;
            padding: 32px 20px 56px;
        }

        .card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(10px);
        }

        .layout {
            display: grid;
            grid-template-columns: minmax(320px, 430px) minmax(0, 1fr);
            gap: 24px;
        }

        .form-card,
        .result-card {
            padding: 26px;
        }

        .section-title {
            margin: 0 0 18px;
            font-size: 1.15rem;
            letter-spacing: -0.02em;
        }

        .field-grid {
            display: grid;
            gap: 16px;
        }

        .two-up {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-size: 0.92rem;
            font-weight: 600;
        }

        input,
        textarea,
        select {
            width: 100%;
            border: 1px solid rgba(31, 26, 20, 0.14);
            border-radius: 14px;
            background: #fffdf9;
            padding: 13px 14px;
            font: inherit;
            color: var(--ink);
            transition: border-color 120ms ease, box-shadow 120ms ease;
        }

        textarea {
            min-height: 170px;
            resize: vertical;
            line-height: 1.5;
        }

        input:focus,
        textarea:focus,
        select:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 4px rgba(13, 108, 99, 0.12);
        }

        .quick-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: -2px;
        }

        .quick {
            min-width: 0;
            padding: 9px 12px;
            color: #1b4f76;
            background: rgba(27, 79, 118, 0.11);
            box-shadow: none;
            font-size: 0.88rem;
        }

        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            margin-top: 8px;
        }

        button {
            border: 0;
            border-radius: 999px;
            padding: 13px 18px;
            font: inherit;
            font-weight: 700;
            color: white;
            background: linear-gradient(135deg, var(--accent), #0f8f82);
            cursor: pointer;
            min-width: 160px;
            transition: transform 120ms ease, box-shadow 120ms ease, opacity 120ms ease;
            box-shadow: 0 12px 30px rgba(13, 108, 99, 0.24);
        }

        button:hover { transform: translateY(-1px); }
        button:disabled { opacity: 0.65; cursor: wait; transform: none; }

        .hint {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.5;
        }

        .preset-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: -2px;
        }

        .preset {
            min-width: 0;
            padding: 9px 12px;
            color: var(--accent);
            background: rgba(13, 108, 99, 0.08);
            box-shadow: none;
            font-size: 0.88rem;
        }

        .preset.secondary {
            color: #7a4b1a;
            background: rgba(215, 122, 42, 0.12);
        }

        .status {
            min-height: 24px;
            font-size: 0.93rem;
            font-weight: 600;
        }

        .status.error { color: var(--error); }
        .status.ok { color: var(--accent); }

        .result-head {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }

        .summary-widgets {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }

        .summary-widget {
            border: 1px solid var(--line);
            background: var(--panel-strong);
            border-radius: 12px;
            padding: 10px 12px;
        }

        .summary-widget strong {
            display: block;
            color: var(--muted);
            font-size: 0.82rem;
            margin-bottom: 5px;
        }

        .summary-widget span {
            font-weight: 700;
        }

        .pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(215, 122, 42, 0.1);
            color: #9a4f12;
            font-size: 0.88rem;
            font-weight: 700;
        }

        .answer {
            line-height: 1.65;
            background: var(--panel-strong);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 18px;
            min-height: 320px;
        }

        .analysis-grid {
            display: grid;
            gap: 14px;
        }

        .analysis-section {
            border: 1px solid rgba(31, 26, 20, 0.08);
            border-radius: 16px;
            padding: 16px;
            background: rgba(255, 255, 255, 0.65);
        }

        .analysis-section h3 {
            margin: 0 0 8px;
            font-size: 1rem;
            letter-spacing: -0.02em;
        }

        .analysis-section p {
            margin: 0;
            white-space: pre-wrap;
        }

        .empty {
            color: var(--muted);
            display: grid;
            place-items: center;
            text-align: center;
        }

        @media (max-width: 900px) {
            .layout,
            .two-up {
                grid-template-columns: 1fr;
            }

            .form-card,
            .result-card {
                padding: 22px;
            }
        }
    </style>
</head>
<body>
    <div class="shell">
        <section class="layout">
            <article class="card form-card">
                <h2 class="section-title">Ask Logs</h2>
                <form id="ask-form" class="field-grid">
                    <div>
                        <label for="api_key">API key</label>
                        <input id="api_key" name="api_key" type="password" autocomplete="off" placeholder="Required when the server sets API_KEY">
                    </div>

                    <div>
                        <label for="question">Question</label>
                        <textarea id="question" name="question" placeholder="What is the current status of my application?" required></textarea>
                    </div>

                    <div class="quick-row">
                        <button type="button" class="quick" data-quick-question="Show errors from the last 30 minutes." data-quick-minutes="30" data-quick-max-logs="40">Errors in last 30 minutes</button>
                        <button type="button" class="quick" data-quick-question="What is the overall status of the application in the last 60 minutes?" data-quick-minutes="60" data-quick-max-logs="60">Status in last 1 hour</button>
                        <button type="button" class="quick" data-quick-question="Show business impact and key risks from the last 2 hours." data-quick-minutes="120" data-quick-max-logs="80">Impact in last 2 hours</button>
                        <button type="button" class="quick" data-quick-question="Show top issues and trend from the last 4 hours." data-quick-minutes="240" data-quick-max-logs="100">Top issues in last 4 hours</button>
                    </div>

                    <div>
                        <label for="app">Service name (component_name filter)</label>
                        <input id="app" name="app" placeholder="e.g. api-gateway or leave blank for all services">
                        <div class="hint">Partial names are matched. Leave blank to search all services.</div>
                    </div>

                    <div class="preset-row">
                        <button type="button" class="preset" data-app="">All services</button>
                        <button type="button" class="preset" data-app="api-gateway">API Gateway</button>
                        <button type="button" class="preset" data-app="auth">Auth</button>
                        <button type="button" class="preset" data-app="orders">Orders</button>
                        <button type="button" class="preset secondary" data-app="payments">Payments</button>
                        <button type="button" class="preset secondary" data-app="worker">Worker</button>
                    </div>

                    <div class="two-up">
                        <div>
                            <label for="minutes">Time window (minutes)</label>
                            <select id="minutes" name="minutes" required>
                                <option value="15">Last 15 minutes</option>
                                <option value="30" selected>Last 30 minutes</option>
                                <option value="60">Last 1 hour</option>
                                <option value="120">Last 2 hours</option>
                                <option value="240">Last 4 hours</option>
                                <option value="720">Last 12 hours</option>
                                <option value="1440">Last 24 hours</option>
                            </select>
                        </div>
                        <div>
                            <label for="max_logs">Max logs</label>
                            <select id="max_logs" name="max_logs" required>
                                <option value="20">20</option>
                                <option value="40">40</option>
                                <option value="60">60</option>
                                <option value="100">100</option>
                                <option value="120">120</option>
                                <option value="150" selected>150</option>
                                <option value="200">200</option>
                                <option value="300">300</option>
                                <option value="330">330</option>
                            </select>
                            <div class="hint">Auto-adjusts with time window. 24h uses 330 logs.</div>
                        </div>
                    </div>

                    <div class="actions">
                        <button id="submit-button" type="submit">Analyze Error And Impact</button>
                        <span class="hint">Simple summary for application users.</span>
                    </div>
                    <div id="status" class="status"></div>
                </form>
            </article>

            <article class="card result-card">
                <h2 class="section-title">Analysis</h2>
                <div id="result-head" class="result-head" hidden>
                    <div class="pill" id="logs-used">Logs used: 0</div>
                    <div class="pill" id="time-window">Window: 0 minutes</div>
                    <div class="pill" id="index-name">Index: unknown</div>
                    <div class="pill" id="llm-provider">AI: unknown</div>
                </div>
                <div id="summary-widgets" class="summary-widgets" hidden>
                    <div class="summary-widget"><strong>Severity</strong><span id="severity-level">Unknown</span></div>
                    <div class="summary-widget"><strong>Confidence</strong><span id="confidence-level">Unknown</span></div>
                    <div class="summary-widget"><strong>Signal strength</strong><span id="signal-level">Low</span></div>
                </div>
                <div id="answer" class="answer empty">Run a query to see the log analysis here.</div>
            </article>
        </section>
    </div>

    <script>
        const form = document.getElementById("ask-form");
        const questionInput = document.getElementById("question");
        const appInput = document.getElementById("app");
        const apiKeyInput = document.getElementById("api_key");
        const minutesInput = document.getElementById("minutes");
        const maxLogsInput = document.getElementById("max_logs");
        const statusNode = document.getElementById("status");
        const answerNode = document.getElementById("answer");
        const resultHead = document.getElementById("result-head");
        const submitButton = document.getElementById("submit-button");
        const logsUsedNode = document.getElementById("logs-used");
        const timeWindowNode = document.getElementById("time-window");
        const indexNameNode = document.getElementById("index-name");
        const llmProviderNode = document.getElementById("llm-provider");
        const summaryWidgetsNode = document.getElementById("summary-widgets");
        const severityLevelNode = document.getElementById("severity-level");
        const confidenceLevelNode = document.getElementById("confidence-level");
        const signalLevelNode = document.getElementById("signal-level");
        const presetButtons = document.querySelectorAll(".preset[data-app]");
        const quickButtons = document.querySelectorAll(".quick[data-quick-question]");

        function escapeHtml(value) {
            return value
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#39;");
        }

        function normalizeLevel(value) {
            const lowered = (value || "").toLowerCase();
            if (lowered.includes("high")) return "High";
            if (lowered.includes("medium")) return "Medium";
            if (lowered.includes("low")) return "Low";
            return "Unknown";
        }

        function signalFromLogs(logsUsed) {
            if (logsUsed >= 120) return "High";
            if (logsUsed >= 40) return "Medium";
            return "Low";
        }

        function suggestedMaxLogs(minutes) {
            if (minutes >= 1440) return "330";
            if (minutes >= 720) return "300";
            if (minutes >= 240) return "260";
            if (minutes >= 120) return "220";
            if (minutes >= 60) return "180";
            if (minutes >= 30) return "120";
            return "60";
        }

        function syncMaxLogsToWindow() {
            const target = suggestedMaxLogs(Number(minutesInput.value));
            const existing = [...maxLogsInput.options].some((opt) => opt.value === target);
            if (!existing) {
                const option = document.createElement("option");
                option.value = target;
                option.textContent = target;
                maxLogsInput.append(option);
            }
            maxLogsInput.value = target;
        }

        function renderAnalysis(rawText) {
            const severityMatch = rawText.match(/Severity:\\s*([^\\n]+)/i);
            const confidenceMatch = rawText.match(/Confidence:\\s*([^\\n]+)/i);

            const normalizedText = rawText
                .replace(/```[\\s\\S]*?```/g, "")
                .replace(/Severity:\\s*[^\\n]+/gi, "")
                .replace(/Confidence:\\s*[^\\n]+/gi, "")
                .replace(/\\r/g, "")
                .replace(/^\\s*#{1,6}\\s*/gm, "")
                .trim();

            const matches = [...normalizedText.matchAll(/(?:^|\\n)\\s*(\\d+)\\.\\s+([^\\n]+)\\n?([\\s\\S]*?)(?=(?:\\n\\s*\\d+\\.\\s+)|$)/g)];
            const sections = matches.map((match) => ({
                header: `${match[1]}. ${match[2].trim()}`,
                body: match[3].trim(),
            })).slice(0, 4);

            if (!sections.length) {
                answerNode.textContent = normalizedText || rawText;
                answerNode.className = "answer";
                return {
                    severity: normalizeLevel(severityMatch ? severityMatch[1] : ""),
                    confidence: normalizeLevel(confidenceMatch ? confidenceMatch[1] : ""),
                };
            }

            const cards = sections.map((section) => {
                return `
                    <section class="analysis-section">
                        <h3>${escapeHtml(section.header)}</h3>
                        <p>${escapeHtml(section.body || "No details returned.")}</p>
                    </section>
                `;
            });

            answerNode.innerHTML = `<div class="analysis-grid">${cards.join("")}</div>`;
            answerNode.className = "answer";

            return {
                severity: normalizeLevel(severityMatch ? severityMatch[1] : ""),
                confidence: normalizeLevel(confidenceMatch ? confidenceMatch[1] : ""),
            };
        }

        presetButtons.forEach((button) => {
            button.addEventListener("click", () => {
                appInput.value = button.dataset.app || "";
            });
        });

        minutesInput.addEventListener("change", () => {
            syncMaxLogsToWindow();
        });

        async function submitAsk(payload) {
            submitButton.disabled = true;
            statusNode.textContent = "Querying Elasticsearch and generating analysis...";
            statusNode.className = "status";
            answerNode.textContent = "Working...";
            answerNode.className = "answer";

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minute timeout

            try {
                const response = await fetch("/ask", {
                    method: "POST",
                    headers: Object.assign(
                        { "Content-Type": "application/json" },
                        apiKeyInput.value ? { "X-API-Key": apiKeyInput.value } : {}
                    ),
                    body: JSON.stringify(payload),
                    signal: controller.signal,
                });
                clearTimeout(timeoutId);

                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.detail || "Request failed");
                }

                resultHead.hidden = false;
                logsUsedNode.textContent = `Logs used: ${result.logs_used}`;
                timeWindowNode.textContent = `Window: ${result.time_window_minutes} minutes`;
                indexNameNode.textContent = `Index: ${result.elasticsearch_index}`;
                llmProviderNode.textContent = `AI: ${result.llm_provider || 'unknown'}`;
                const meta = renderAnalysis(result.answer);
                summaryWidgetsNode.hidden = false;
                severityLevelNode.textContent = meta.severity;
                confidenceLevelNode.textContent = meta.confidence;
                signalLevelNode.textContent = signalFromLogs(result.logs_used);
                statusNode.textContent = "Analysis complete.";
                statusNode.className = "status ok";
            } catch (error) {
                clearTimeout(timeoutId);
                resultHead.hidden = true;
                summaryWidgetsNode.hidden = true;
                if (error.name === 'AbortError') {
                    answerNode.textContent = "Request timed out after 5 minutes. Try reducing the time window or max logs.";
                } else {
                    answerNode.textContent = error.message;
                }
                answerNode.className = "answer";
                statusNode.textContent = "Request failed.";
                statusNode.className = "status error";
            } finally {
                submitButton.disabled = false;
            }
        }

        quickButtons.forEach((button) => {
            button.addEventListener("click", () => {
                questionInput.value = button.dataset.quickQuestion || "";
                minutesInput.value = button.dataset.quickMinutes || "30";
                maxLogsInput.value = button.dataset.quickMaxLogs || "60";

                syncMaxLogsToWindow();

                submitAsk({
                    question: questionInput.value.trim(),
                    namespace: null,
                    app: appInput.value.trim() || null,
                    minutes: Number(minutesInput.value),
                    max_logs: Number(maxLogsInput.value),
                });
            });
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            await submitAsk({
                question: questionInput.value.trim(),
                namespace: null,
                app: appInput.value.trim() || null,
                minutes: Number(minutesInput.value),
                max_logs: Number(maxLogsInput.value),
            });
        });

        syncMaxLogsToWindow();
    </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require X-API-Key on /ask when API_KEY is configured.

    If API_KEY is unset the endpoint stays open, which is only acceptable for
    loopback/port-forward use. A warning is logged at startup in that case.
    """
    expected = get_settings().api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_api_key)])
def ask_logs(request: AskRequest) -> AskResponse:
    settings = get_settings()
    effective_max_logs = min(request.max_logs, settings.max_logs_limit)

    es_client = ElasticsearchLogClient(settings)
    try:
        logs = es_client.search_logs(request, effective_max_logs)
    except ElasticsearchQueryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not logs:
        return AskResponse(
            answer="No matching logs were found for the given filters/time window.",
            logs_used=0,
            time_window_minutes=request.minutes,
            namespace=request.namespace,
            app=request.app,
            elasticsearch_index=settings.elasticsearch_index,
        )

    redacted_logs = [log.model_copy(update={"message": redact_text(log.message)}) for log in logs]
    prompt = build_prompt(request, redacted_logs)

    try:
        llm = create_llm_client(settings)
        answer = llm.generate_answer(prompt)
        answer = sanitize_answer_for_end_users(answer)
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    LOGGER.info(
        "Answered log question provider=%s app=%s logs_used=%s",
        settings.llm_provider,
        request.app,
        len(redacted_logs),
    )

    return AskResponse(
        answer=answer,
        logs_used=len(redacted_logs),
        time_window_minutes=request.minutes,
        namespace=request.namespace,
        app=request.app,
        elasticsearch_index=settings.elasticsearch_index,
        llm_provider=settings.llm_provider,
    )
