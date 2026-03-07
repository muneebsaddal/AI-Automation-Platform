import json
from datetime import datetime
from core.state import AgentState, ValidationError
from core.llm import chat

SYSTEM = """You are a DevOps validation agent. Given execution results, produce a JSON object with:
- "status": "success" | "partial_failure" | "failure"
- "summary": one-sentence summary
- "actions_taken": list of strings
- "failures": list of {"step": string, "reason": string}
- "recommendations": list of strings

Respond ONLY with JSON. No markdown, no explanation."""


def validator_agent(state: AgentState) -> AgentState:
    state.current_agent = "validator"
    state.add_log("validator", "Validating execution results")

    # Rule-based checks before LLM synthesis
    hard_failures = [r for r in state.execution_results if r.get("success") is False]
    if hard_failures:
        state.add_log(
            "validator",
            f"{len(hard_failures)} hard failure(s) detected",
            level="warning",
        )

    try:
        context = json.dumps({
            "plan": state.plan,
            "results": state.execution_results,
        }, indent=2)

        raw = chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": context},
        ])

        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        structured = json.loads(cleaned)

        # Pydantic-style validation of required keys
        validation_errors: list[ValidationError] = []
        for required in ["status", "summary", "actions_taken", "failures", "recommendations"]:
            if required not in structured:
                validation_errors.append(ValidationError(
                    field=required,
                    issue="Missing required field in LLM output",
                    value=None,
                ))

        state.structured_output = structured
        state.validation_errors = validation_errors

        final_status = structured.get("status", "failure")
        state.status = "completed" if final_status in ("success", "partial_failure") else "failed"
        state.add_log("validator", f"Validation done — run status: {state.status}")

    except Exception as e:
        state.add_log("validator", f"Validation error: {e}", level="error")
        state.validation_errors = [ValidationError(
            field="structured_output",
            issue=f"LLM parse failure: {e}",
        )]
        state.status = "failed"
        state.error = str(e)

    state.completed_at = datetime.utcnow().isoformat()
    return state
