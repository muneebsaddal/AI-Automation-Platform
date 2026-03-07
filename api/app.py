import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.graph import pipeline
from core.state import AgentState
from core.persistence import save_state, load_state, list_runs, delete_run
from core.ws import manager

app = FastAPI(title="AI Automation Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class RunRequest(BaseModel):
    input: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    started_at: str
    completed_at: str
    summary: str


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.post("/runs")
async def create_run(req: RunRequest):
    """Create and immediately start a new automation run."""
    run_id = str(uuid.uuid4())[:8]
    state = AgentState(run_id=run_id, raw_input=req.input, status="running")
    save_state(state)

    # Run the graph in the background so we can return the run_id immediately
    asyncio.create_task(_execute_run(run_id, state))
    return {"run_id": run_id}


@app.get("/runs")
async def get_runs():
    """List recent runs with summary info."""
    run_ids = list_runs()
    summaries = []
    for rid in run_ids:
        s = load_state(rid)
        if s:
            summaries.append({
                "run_id": s.run_id,
                "status": s.status,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "summary": s.structured_output.get("summary", s.raw_input[:60]),
            })
    return summaries


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    state = load_state(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")
    return state.model_dump()


@app.get("/runs/{run_id}/trace")
async def export_trace(run_id: str):
    """Export full execution trace as downloadable JSON."""
    state = load_state(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")
    return JSONResponse(
        content=state.to_trace(),
        headers={"Content-Disposition": f'attachment; filename="trace-{run_id}.json"'},
    )


@app.post("/runs/{run_id}/replay")
async def replay_run(run_id: str):
    """Replay a failed run with the same input."""
    original = load_state(run_id)
    if not original:
        raise HTTPException(404, f"Run {run_id} not found")
    if original.status not in ("failed",):
        raise HTTPException(400, f"Run {run_id} has status '{original.status}'; only failed runs can be replayed")

    new_run_id = str(uuid.uuid4())[:8]
    state = AgentState(
        run_id=new_run_id,
        raw_input=original.raw_input,
        status="running",
    )
    state.add_log("orchestrator", f"Replaying failed run {run_id}")
    save_state(state)
    asyncio.create_task(_execute_run(new_run_id, state))
    return {"run_id": new_run_id, "replayed_from": run_id}


@app.delete("/runs/{run_id}")
async def delete_run_endpoint(run_id: str):
    delete_run(run_id)
    return {"deleted": run_id}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await manager.connect(run_id, websocket)
    try:
        # Immediately push current state so the UI can hydrate on reconnect
        state = load_state(run_id)
        if state:
            await manager.broadcast_state(run_id, state.model_dump())
        # Keep connection alive until client disconnects
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)


# ── Internal run executor ─────────────────────────────────────────────────────

async def _execute_run(run_id: str, initial_state: AgentState) -> None:
    """Run the LangGraph pipeline, streaming state updates over WebSocket."""

    async def _push_log(agent: str, message: str, level: str = "info"):
        await manager.broadcast_log(run_id, agent, message, level)
        # Small yield so WebSocket frames flush between heavy sync work
        await asyncio.sleep(0)

    try:
        await _push_log("orchestrator", f"Run {run_id} started")

        state_dict = initial_state.model_dump()

        # Stream graph nodes — each yields a partial state update
        async for chunk in pipeline.astream(state_dict):
            for node_name, node_output in chunk.items():
                updated = AgentState(**node_output)
                save_state(updated)

                # Broadcast any new logs produced by this node
                for log in updated.logs[-5:]:  # tail — avoid re-broadcasting old logs
                    await manager.broadcast_log(run_id, log.agent, log.message, log.level)

                # Broadcast full state snapshot after each node
                await manager.broadcast_state(run_id, updated.model_dump())
                await asyncio.sleep(0)

        final = load_state(run_id)
        if final:
            await manager.broadcast_done(run_id, final.model_dump())
            await _push_log("orchestrator", f"Run {run_id} finished with status: {final.status}")

    except Exception as e:
        err_state = load_state(run_id) or initial_state
        err_state.status = "failed"
        err_state.error = str(e)
        err_state.completed_at = datetime.utcnow().isoformat()
        err_state.add_log("orchestrator", f"Unhandled error: {e}", level="error")
        save_state(err_state)
        await manager.broadcast_error(run_id, str(e))


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
