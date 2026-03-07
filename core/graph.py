from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from typing import Any

from core.state import AgentState
from agents.planner import planner_agent
from agents.executor import executor_agent
from agents.validator import validator_agent


# LangGraph requires dict-based state; we wrap our Pydantic model
def _planner(state: dict) -> dict:
    s = AgentState(**state)
    result = planner_agent(s)
    return result.model_dump()


def _executor(state: dict) -> dict:
    s = AgentState(**state)
    result = executor_agent(s)
    return result.model_dump()


def _validator(state: dict) -> dict:
    s = AgentState(**state)
    result = validator_agent(s)
    return result.model_dump()


def _route_after_validator(state: dict) -> str:
    """Retry executor if validation failed and retries remain."""
    s = AgentState(**state)
    if s.status == "failed" and s.retry_count < s.max_retries:
        return "retry"
    return "done"


def _increment_retry(state: dict) -> dict:
    s = AgentState(**state)
    s.retry_count += 1
    s.add_log("orchestrator", f"Retrying — attempt {s.retry_count}/{s.max_retries}", level="warning")
    s.status = "running"
    return s.model_dump()


def build_graph() -> CompiledStateGraph:
    g = StateGraph(dict)

    g.add_node("planner", _planner)
    g.add_node("executor", _executor)
    g.add_node("validator", _validator)
    g.add_node("retry", _increment_retry)

    g.set_entry_point("planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", "validator")
    g.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"retry": "retry", "done": END},
    )
    g.add_edge("retry", "executor")

    return g.compile()


# Module-level singleton
pipeline: CompiledStateGraph = build_graph()
