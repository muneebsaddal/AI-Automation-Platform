# AI Automation Platform

End-to-end AI automation system with a real-time observability dashboard. Phase 5 of a structured AI/ML engineering roadmap — focused on production readiness, determinism, and portfolio credibility.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React UI (Vite)                       │
│  Panel 1: Raw Input   Panel 2: Graph State              │
│  Panel 3: Structured  Panel 4: Validation Errors        │
│  Panel 5: Exec Logs   Panel 6: Tool Results             │
└───────────────────┬─────────────────────────────────────┘
                    │ WebSocket (bidirectional)
┌───────────────────▼─────────────────────────────────────┐
│                  FastAPI                                 │
│  POST /runs   GET /runs/:id   POST /runs/:id/replay     │
│  GET /runs/:id/trace          WS /ws/:id                │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│              LangGraph Pipeline                          │
│                                                          │
│   [Planner] ──► [Executor] ──► [Validator]              │
│                     ▲               │                   │
│                     └── retry ◄─────┘ (on failure)      │
└───────────────────┬─────────────────────────────────────┘
                    │ state persistence
              ┌─────▼─────┐
              │   Redis   │
              └───────────┘
```

## Graph Diagram

```
START
  │
  ▼
planner          — decomposes raw input into ordered tool-call steps
  │
  ▼
executor         — maps each step to a mock DevOps tool via LLM + runs it
  │
  ▼
validator        — synthesises structured output, flags validation errors
  │
  ├─► [status==failed AND retry_count < max_retries] ──► retry ──► executor
  │
  └─► END
```

## Structure

```
ai-automation-platform/
├── core/
│   ├── llm.py          # LLM provider (Ollama / OpenAI via USE_OPENAI flag)
│   ├── state.py        # AgentState Pydantic model
│   ├── graph.py        # LangGraph pipeline
│   ├── persistence.py  # Redis state read/write
│   ├── tools.py        # Mock DevOps tools
│   └── ws.py           # WebSocket connection manager
├── agents/
│   ├── planner.py      # Planning agent
│   ├── executor.py     # Execution agent
│   └── validator.py    # Validation agent
├── api/
│   └── app.py          # FastAPI app (REST + WebSocket)
├── ui/                 # React + Vite dashboard
│   └── src/App.jsx     # Single-file UI (all 5 panels)
├── traces/             # Example execution traces (JSON)
├── tests/              # Pytest integration tests
├── main.py
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.11+
- Node 18+
- Redis running locally
- Ollama (dev) or OpenAI API key (portfolio/prod)

## Usage

**1. Backend**

```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
# API available at http://localhost:8000
```

**2. Frontend**

```bash
cd ui
npm install
npm run dev
# UI available at http://localhost:3000
```

**3. Switch to OpenAI**

In `.env`:
```
USE_OPENAI=true
OPENAI_API_KEY=sk-...
```

**4. Run tests**

```bash
pytest tests/ -v
```

## Key Design Decisions

**Single-flag LLM switching** — `USE_OPENAI=true/false` in `.env` is the only change needed to swap between Ollama (local dev) and OpenAI (portfolio/prod). All other code is identical.

**WebSocket fan-out** — `core/ws.py` maintains a `run_id → set[WebSocket]` registry. Multiple browser tabs can observe the same run simultaneously. Dead connections are pruned on next broadcast.

**Deterministic retry routing** — LangGraph's conditional edge evaluates `status == "failed" AND retry_count < max_retries`. Retry count is part of state, making the routing fully reproducible from the trace JSON.

**Pydantic-first state** — `AgentState` is the single source of truth. Every agent receives and returns a validated model. Partial LLM failures surface as `ValidationError` entries rather than exceptions, keeping the pipeline alive.

**Trace export = full reproducibility** — `GET /runs/:id/trace` returns the complete `AgentState` as JSON. Any run can be inspected, diffed, or replayed via `POST /runs/:id/replay`.

**Mock tools with intentional failure rate** — `core/tools.py` introduces an 85% success rate on `deploy_service` to exercise the retry path in normal development. No external services required.

## Example Execution Logs

See `traces/example-success.json` and `traces/example-failure-with-retry.json` for annotated real traces.

**Success run (3 steps, 0 retries):**
```
[orchestrator] Run a1b2c3d4 started
[planner]      Plan created — 3 steps
[executor]     Step 1/3: deploy_service api-gateway v2.3 to staging
[executor]     Step 2/3: check_service_health for api-gateway
[executor]     Step 3/3: scale_service api-gateway to 4 replicas
[validator]    Validation done — run status: completed
```

**Failure run (1 step, 2 retries exhausted):**
```
[executor]     Tool deploy_service reported failure: health check timeout
[orchestrator] Retrying — attempt 1/2
[executor]     Tool deploy_service reported failure: health check timeout
[orchestrator] Retrying — attempt 2/2
[executor]     Tool deploy_service reported failure: health check timeout
[validator]    Validation done — run status: failed
```

## Failure Cases

| Scenario | Behaviour |
|---|---|
| LLM returns malformed JSON | Agent logs error, state marked `failed`, retried if retries remain |
| Tool call with unknown tool name | `run_tool` returns `{success: False}`, pipeline continues to validator |
| Validator missing required fields | `ValidationError` entries created, visible in UI panel 4 |
| LLM timeout / network error | Exception caught, state persisted as `failed`, available for replay |
| WebSocket client disconnects mid-run | Dead socket pruned on next broadcast, run continues unaffected |

## Determinism

Each run produces an identical execution trace given the same input and tool responses. The graph topology is fixed at startup (`core/graph.py`). Routing decisions depend only on state fields (`status`, `retry_count`) — no random branching. Mock tools use `random` for realism but real tools are fully deterministic. The `run_id` + full state serialised to Redis means any run can be replayed exactly.
