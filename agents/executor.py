import json
from core.state import AgentState
from core.llm import chat
from core.tools import run_tool, TOOL_MAP

SYSTEM = """You are a DevOps execution agent. Given a task description and available tools,
output a JSON object with keys: "tool" (string) and "params" (object).

Available tools: """ + ", ".join(TOOL_MAP.keys()) + """

Respond ONLY with a JSON object. No markdown, no explanation.
Example: {"tool": "deploy_service", "params": {"service": "api", "version": "v1.2", "environment": "staging"}}
"""


def executor_agent(state: AgentState) -> AgentState:
    state.current_agent = "executor"
    state.execution_results = []

    for i, step in enumerate(state.plan):
        state.add_log("executor", f"Step {i + 1}/{len(state.plan)}: {step}")

        try:
            raw = chat([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Task: {step}"},
            ])

            cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            call = json.loads(cleaned)

            tool_name = call.get("tool", "")
            params = call.get("params", {})

            state.add_log("executor", f"Calling {tool_name}({params})")
            result = run_tool(tool_name, params)
            state.execution_results.append(result)

            if not result.get("success", True):
                state.add_log(
                    "executor",
                    f"Tool {tool_name} reported failure: {result.get('message')}",
                    level="warning",
                )

        except Exception as e:
            state.add_log("executor", f"Step {i + 1} error: {e}", level="error")
            state.execution_results.append({
                "step": step,
                "success": False,
                "message": str(e),
            })

    state.add_log("executor", f"Execution complete — {len(state.execution_results)} results")
    return state
