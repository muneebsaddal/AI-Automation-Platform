import json
from core.state import AgentState
from core.llm import chat

SYSTEM = """You are a DevOps planning agent. Given a user request, produce a JSON array of
actionable steps to execute using these tools:
- deploy_service(service, version, environment)
- check_service_health(service)
- rollback_service(service, target_version)
- scale_service(service, replicas)
- fetch_logs(service, lines)

Respond ONLY with a JSON array of strings. No markdown, no explanation.
Example: ["check_service_health for api-gateway", "deploy_service api-gateway v2.1 to staging"]
"""


def planner_agent(state: AgentState) -> AgentState:
    state.current_agent = "planner"
    state.add_log("planner", f"Analysing request: {state.raw_input[:120]}")

    try:
        raw = chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": state.raw_input},
        ])

        # Strip any accidental markdown fences
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        steps = json.loads(cleaned)

        if not isinstance(steps, list) or not steps:
            raise ValueError("Planner returned empty or non-list plan")

        state.plan = [str(s) for s in steps]
        state.add_log("planner", f"Plan created — {len(state.plan)} steps")

    except Exception as e:
        state.add_log("planner", f"Planning failed: {e}", level="error")
        state.status = "failed"
        state.error = f"Planner error: {e}"

    return state
