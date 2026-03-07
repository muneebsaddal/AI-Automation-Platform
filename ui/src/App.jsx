import { useState, useEffect, useRef, useCallback } from "react";

const API = "http://localhost:8000";
const WS_BASE = "ws://localhost:8000/ws";

// ── Palette & tokens ──────────────────────────────────────────────────────────
const STATUS_COLOR = {
  pending:  { bg: "#1a1a2e", text: "#6c7a9c", dot: "#6c7a9c" },
  running:  { bg: "#0d2137", text: "#38bdf8", dot: "#38bdf8" },
  completed:{ bg: "#0d2b1e", text: "#34d399", dot: "#34d399" },
  failed:   { bg: "#2b0d0d", text: "#f87171", dot: "#f87171" },
};

const LEVEL_COLOR = { info: "#94a3b8", warning: "#fbbf24", error: "#f87171" };

// ── Tiny helpers ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] || STATUS_COLOR.pending;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 10px", borderRadius: 99, fontSize: 11,
      fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase",
      background: c.bg, color: c.text, border: `1px solid ${c.dot}33`,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%", background: c.dot,
        boxShadow: status === "running" ? `0 0 6px ${c.dot}` : "none",
        animation: status === "running" ? "pulse 1.4s ease-in-out infinite" : "none",
      }} />
      {status}
    </span>
  );
}

function Panel({ title, children, action }) {
  return (
    <div style={{
      background: "#0f1117", border: "1px solid #1e2535",
      borderRadius: 10, overflow: "hidden", display: "flex", flexDirection: "column",
    }}>
      <div style={{
        padding: "10px 16px", borderBottom: "1px solid #1e2535",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "#0b0e16",
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em",
          textTransform: "uppercase", color: "#4a5a7a" }}>
          {title}
        </span>
        {action}
      </div>
      <div style={{ padding: 14, flex: 1, overflowY: "auto", maxHeight: 320 }}>
        {children}
      </div>
    </div>
  );
}

function JsonTree({ data }) {
  if (!data || Object.keys(data).length === 0) {
    return <span style={{ color: "#3a4a6a", fontSize: 12 }}>—</span>;
  }
  return (
    <pre style={{
      margin: 0, fontSize: 11.5, lineHeight: 1.6, color: "#7dd3fc",
      whiteSpace: "pre-wrap", wordBreak: "break-word",
    }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [input, setInput]           = useState("");
  const [activeRunId, setActiveRunId] = useState(null);
  const [runState, setRunState]     = useState(null);
  const [logs, setLogs]             = useState([]);
  const [runs, setRuns]             = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [wsStatus, setWsStatus]     = useState("disconnected");
  const wsRef   = useRef(null);
  const logsRef = useRef(null);

  // Auto-scroll logs
  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  // Load run history on mount
  useEffect(() => { fetchRuns(); }, []);

  const fetchRuns = async () => {
    try {
      const res = await fetch(`${API}/runs`);
      if (res.ok) setRuns(await res.json());
    } catch {}
  };

  // Connect WebSocket for a given run
  const connectWs = useCallback((runId) => {
    if (wsRef.current) wsRef.current.close();
    setLogs([]);
    setRunState(null);
    setWsStatus("connecting");

    const ws = new WebSocket(`${WS_BASE}/${runId}`);
    wsRef.current = ws;

    ws.onopen  = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.type === "log") {
        setLogs(prev => [...prev, msg]);
      } else if (msg.type === "state") {
        setRunState(msg.data);
        // Sync logs from state (covers hydration on reconnect)
        if (msg.data.logs?.length) {
          setLogs(msg.data.logs.map(l => ({
            type: "log", agent: l.agent, level: l.level, message: l.message,
          })));
        }
      } else if (msg.type === "done") {
        setRunState(msg.data);
        setSubmitting(false);
        fetchRuns();
      } else if (msg.type === "error") {
        setLogs(prev => [...prev, {
          type: "log", agent: "system", level: "error", message: msg.message,
        }]);
        setSubmitting(false);
      }
    };
  }, []);

  const handleSubmit = async () => {
    if (!input.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: input.trim() }),
      });
      const { run_id } = await res.json();
      setActiveRunId(run_id);
      connectWs(run_id);
    } catch (err) {
      setSubmitting(false);
      alert("Failed to start run: " + err.message);
    }
  };

  const handleSelectRun = async (runId) => {
    setActiveRunId(runId);
    connectWs(runId);
    // Also load initial state via REST in case WS hasn't hydrated yet
    try {
      const res = await fetch(`${API}/runs/${runId}`);
      if (res.ok) setRunState(await res.json());
    } catch {}
  };

  const handleExportTrace = async () => {
    if (!activeRunId) return;
    const res = await fetch(`${API}/runs/${activeRunId}/trace`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `trace-${activeRunId}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const handleReplay = async (runId) => {
    try {
      const res = await fetch(`${API}/runs/${runId}/replay`, { method: "POST" });
      if (!res.ok) { alert("Cannot replay this run."); return; }
      const { run_id } = await res.json();
      setActiveRunId(run_id);
      connectWs(run_id);
      setSubmitting(true);
      fetchRuns();
    } catch (err) {
      alert("Replay failed: " + err.message);
    }
  };

  const validationErrors = runState?.validation_errors || [];
  const structuredOutput = runState?.structured_output || {};
  const status = runState?.status || "pending";

  return (
    <div style={{
      minHeight: "100vh", background: "#080b12", color: "#c8d4e8",
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      display: "flex", flexDirection: "column",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0b0e16; }
        ::-webkit-scrollbar-thumb { background: #1e2d45; border-radius: 2px; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:none} }
        textarea:focus, input:focus { outline: none; }
        button:hover { filter: brightness(1.15); }
        button:active { filter: brightness(0.9); }
      `}</style>

      {/* Header */}
      <header style={{
        borderBottom: "1px solid #1a2235", padding: "14px 28px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "#090c14",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6, background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14,
          }}>⚙</div>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0", letterSpacing: "0.02em" }}>
            AI Automation Platform
          </span>
          <span style={{ fontSize: 11, color: "#3a4a6a", marginLeft: 4 }}>v1.0</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11 }}>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 5, color: "#3a4a6a",
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: "50%",
              background: wsStatus === "connected" ? "#34d399" : wsStatus === "connecting" ? "#fbbf24" : "#475569",
              boxShadow: wsStatus === "connected" ? "0 0 6px #34d399" : "none",
            }} />
            WS {wsStatus}
          </span>
          {activeRunId && (
            <span style={{ color: "#3a4a6a" }}>run <span style={{ color: "#6b7fd4" }}>{activeRunId}</span></span>
          )}
        </div>
      </header>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Sidebar — run history */}
        <aside style={{
          width: 220, borderRight: "1px solid #1a2235", background: "#090c14",
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{
            padding: "10px 14px", borderBottom: "1px solid #1a2235",
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#3a4a6a",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            History
            <button onClick={fetchRuns} style={{
              background: "none", border: "none", color: "#4a5a7a",
              cursor: "pointer", fontSize: 12, padding: 0,
            }}>↺</button>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {runs.length === 0 && (
              <p style={{ fontSize: 11, color: "#2a3a55", padding: "12px 14px" }}>No runs yet</p>
            )}
            {runs.map(r => (
              <div
                key={r.run_id}
                onClick={() => handleSelectRun(r.run_id)}
                style={{
                  padding: "10px 14px", borderBottom: "1px solid #111827",
                  cursor: "pointer", animation: "fadeIn 0.2s ease",
                  background: activeRunId === r.run_id ? "#0d1525" : "transparent",
                  borderLeft: activeRunId === r.run_id ? "2px solid #3b82f6" : "2px solid transparent",
                  transition: "background 0.15s",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: "#6b7fd4", fontWeight: 600 }}>{r.run_id}</span>
                  <StatusBadge status={r.status} />
                </div>
                <p style={{ fontSize: 10, color: "#3a4a6a", margin: 0, lineHeight: 1.4,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.summary}
                </p>
                {r.status === "failed" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleReplay(r.run_id); }}
                    style={{
                      marginTop: 6, fontSize: 10, padding: "2px 8px", borderRadius: 4,
                      background: "#1a1a2e", border: "1px solid #f87171", color: "#f87171",
                      cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    ↺ Replay
                  </button>
                )}
              </div>
            ))}
          </div>
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, padding: 20, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Panel 1: Raw Input */}
          <Panel title="01 · Raw Input">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && e.metaKey) handleSubmit(); }}
                placeholder="e.g. Deploy api-gateway v2.3 to production, then verify health..."
                rows={3}
                style={{
                  width: "100%", background: "#080b12", border: "1px solid #1e2535",
                  borderRadius: 6, padding: "10px 12px", color: "#c8d4e8",
                  fontSize: 13, fontFamily: "inherit", resize: "vertical", lineHeight: 1.5,
                }}
              />
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <button
                  onClick={handleSubmit}
                  disabled={submitting || !input.trim()}
                  style={{
                    padding: "8px 20px", borderRadius: 6, border: "none",
                    background: submitting ? "#1a2235" : "linear-gradient(135deg,#3b82f6,#6366f1)",
                    color: submitting ? "#4a5a7a" : "#fff",
                    fontFamily: "inherit", fontSize: 12, fontWeight: 600,
                    cursor: submitting ? "not-allowed" : "pointer", letterSpacing: "0.04em",
                  }}
                >
                  {submitting ? "Running…" : "▶ Run"}
                </button>
                <span style={{ fontSize: 10, color: "#2a3a55" }}>⌘↵ to submit</span>
                {activeRunId && <StatusBadge status={status} />}
              </div>
            </div>
          </Panel>

          {/* Panels 2–5 in 2×2 grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

            {/* Panel 2: Graph State */}
            <Panel title="02 · Graph State">
              {!runState ? (
                <span style={{ color: "#2a3a55", fontSize: 12 }}>No active run</span>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
                  <Row label="Run ID"    value={<span style={{ color: "#6b7fd4" }}>{runState.run_id}</span>} />
                  <Row label="Status"    value={<StatusBadge status={runState.status} />} />
                  <Row label="Agent"     value={<span style={{ color: "#38bdf8" }}>{runState.current_agent || "—"}</span>} />
                  <Row label="Retries"   value={`${runState.retry_count}/${runState.max_retries}`} />
                  <Row label="Started"   value={fmt(runState.started_at)} />
                  <Row label="Completed" value={fmt(runState.completed_at)} />
                  {runState.plan?.length > 0 && (
                    <div style={{ marginTop: 6 }}>
                      <div style={{ fontSize: 10, color: "#3a4a6a", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                        Plan ({runState.plan.length} steps)
                      </div>
                      {runState.plan.map((step, i) => (
                        <div key={i} style={{
                          display: "flex", gap: 8, padding: "4px 0",
                          borderBottom: "1px solid #111827", fontSize: 11, color: "#7a8faa",
                        }}>
                          <span style={{ color: "#2a3a55", minWidth: 16 }}>{i + 1}.</span>
                          <span>{step}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Panel>

            {/* Panel 3: Structured Output */}
            <Panel
              title="03 · Structured Output"
              action={activeRunId && (
                <button
                  onClick={handleExportTrace}
                  style={{
                    fontSize: 10, padding: "3px 10px", borderRadius: 4,
                    background: "#0d1525", border: "1px solid #1e2d45", color: "#6b7fd4",
                    cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
                  }}
                >
                  ↓ Export Trace
                </button>
              )}
            >
              <JsonTree data={structuredOutput} />
            </Panel>

            {/* Panel 4: Validation Errors */}
            <Panel title="04 · Validation Errors">
              {validationErrors.length === 0 ? (
                <span style={{ color: "#1a4a2e", fontSize: 12 }}>✓ No validation errors</span>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {validationErrors.map((err, i) => (
                    <div key={i} style={{
                      background: "#1a0d0d", border: "1px solid #3a1a1a",
                      borderRadius: 6, padding: "8px 12px", fontSize: 11,
                      animation: "fadeIn 0.2s ease",
                    }}>
                      <div style={{ color: "#f87171", fontWeight: 600, marginBottom: 2 }}>
                        {err.field}
                      </div>
                      <div style={{ color: "#9a7a7a" }}>{err.issue}</div>
                      {err.value !== null && (
                        <div style={{ color: "#5a3a3a", marginTop: 2, fontSize: 10 }}>
                          value: {JSON.stringify(err.value)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            {/* Panel 5: Execution Logs */}
            <Panel title="05 · Execution Logs">
              <div ref={logsRef} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {logs.length === 0 && (
                  <span style={{ color: "#2a3a55", fontSize: 11 }}>Waiting for logs…</span>
                )}
                {logs.map((log, i) => (
                  <div key={i} style={{
                    display: "flex", gap: 8, fontSize: 11, lineHeight: 1.5,
                    animation: "fadeIn 0.15s ease",
                  }}>
                    <span style={{
                      minWidth: 66, color: "#2a3a55", fontSize: 10,
                      paddingTop: 1, flexShrink: 0,
                    }}>
                      [{log.agent}]
                    </span>
                    <span style={{ color: LEVEL_COLOR[log.level] || "#94a3b8" }}>
                      {log.message}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>

          </div>

          {/* Execution Results (bonus) */}
          {runState?.execution_results?.length > 0 && (
            <Panel title="06 · Tool Execution Results">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {runState.execution_results.map((r, i) => (
                  <div key={i} style={{
                    background: r.success === false ? "#1a0d0d" : "#0a1a0a",
                    border: `1px solid ${r.success === false ? "#3a1a1a" : "#1a3a1a"}`,
                    borderRadius: 6, padding: "8px 12px", fontSize: 11,
                    animation: "fadeIn 0.2s ease",
                  }}>
                    <div style={{
                      display: "flex", justifyContent: "space-between", marginBottom: 4,
                    }}>
                      <span style={{ color: "#7dd3fc", fontWeight: 600 }}>
                        {r.tool || `step ${i + 1}`}
                      </span>
                      <span style={{ color: r.success === false ? "#f87171" : "#34d399" }}>
                        {r.success === false ? "✗ failed" : "✓ ok"}
                      </span>
                    </div>
                    <span style={{ color: "#5a6a8a" }}>{r.message}</span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

        </main>
      </div>
    </div>
  );
}

// ── Utility components ────────────────────────────────────────────────────────
function Row({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
      borderBottom: "1px solid #0f1520", paddingBottom: 4 }}>
      <span style={{ color: "#3a4a6a", fontSize: 10, textTransform: "uppercase",
        letterSpacing: "0.08em" }}>{label}</span>
      <span style={{ color: "#8a9aba", fontSize: 11 }}>{value}</span>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString();
  } catch { return iso; }
}
