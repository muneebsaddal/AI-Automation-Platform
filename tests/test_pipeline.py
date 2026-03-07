"""
Integration tests — run with: pytest tests/ -v
Redis must be running. Ollama optional (tests mock the LLM layer).
"""
import pytest
from unittest.mock import patch, MagicMock
from core.state import AgentState
from agents.planner import planner_agent
from agents.executor import executor_agent
from agents.validator import validator_agent


def _mock_chat_planner(*args, **kwargs):
    return '["check_service_health for api-gateway", "deploy_service api-gateway v2.1 to staging"]'


def _mock_chat_executor(*args, **kwargs):
    return '{"tool": "check_service_health", "params": {"service": "api-gateway"}}'


def _mock_chat_validator(*args, **kwargs):
    return """{
        "status": "success",
        "summary": "Health check passed and service deployed",
        "actions_taken": ["Checked health", "Deployed"],
        "failures": [],
        "recommendations": ["Monitor for 10 minutes"]
    }"""


@pytest.fixture
def base_state():
    return AgentState(
        run_id="test-001",
        raw_input="Deploy api-gateway v2.1 to staging",
    )


class TestPlannerAgent:
    @patch("agents.planner.chat", side_effect=_mock_chat_planner)
    def test_produces_plan(self, _, base_state):
        result = planner_agent(base_state)
        assert len(result.plan) == 2
        assert result.status != "failed"

    @patch("agents.planner.chat", side_effect=Exception("LLM timeout"))
    def test_handles_llm_error(self, _, base_state):
        result = planner_agent(base_state)
        assert result.status == "failed"
        assert "Planner error" in result.error

    @patch("agents.planner.chat", return_value="not json at all")
    def test_handles_bad_json(self, _, base_state):
        result = planner_agent(base_state)
        assert result.status == "failed"


class TestExecutorAgent:
    @patch("agents.executor.chat", side_effect=_mock_chat_executor)
    def test_executes_all_steps(self, _, base_state):
        base_state.plan = ["check health", "check health again"]
        result = executor_agent(base_state)
        assert len(result.execution_results) == 2

    @patch("agents.executor.chat", side_effect=_mock_chat_executor)
    def test_runs_real_tool(self, _, base_state):
        base_state.plan = ["check_service_health for api-gateway"]
        result = executor_agent(base_state)
        assert result.execution_results[0]["tool"] == "check_service_health"

    @patch("agents.executor.chat", return_value='{"tool": "nonexistent_tool", "params": {}}')
    def test_handles_unknown_tool(self, _, base_state):
        base_state.plan = ["do something unknown"]
        result = executor_agent(base_state)
        assert result.execution_results[0]["success"] is False


class TestValidatorAgent:
    @patch("agents.validator.chat", side_effect=_mock_chat_validator)
    def test_produces_structured_output(self, _, base_state):
        base_state.plan = ["deploy"]
        base_state.execution_results = [{"tool": "deploy_service", "success": True, "message": "ok"}]
        result = validator_agent(base_state)
        assert result.structured_output.get("status") == "success"
        assert result.status == "completed"
        assert result.validation_errors == []

    @patch("agents.validator.chat", return_value='{"status": "success"}')
    def test_flags_missing_fields(self, _, base_state):
        base_state.plan = ["deploy"]
        base_state.execution_results = [{"success": True}]
        result = validator_agent(base_state)
        # summary, actions_taken, failures, recommendations are missing
        assert len(result.validation_errors) == 4

    @patch("agents.validator.chat", side_effect=Exception("parse error"))
    def test_handles_llm_failure(self, _, base_state):
        base_state.plan = ["deploy"]
        base_state.execution_results = []
        result = validator_agent(base_state)
        assert result.status == "failed"
        assert len(result.validation_errors) > 0


class TestAgentState:
    def test_add_log(self, base_state):
        base_state.add_log("planner", "test message", "warning")
        assert len(base_state.logs) == 1
        assert base_state.logs[0].agent == "planner"
        assert base_state.logs[0].level == "warning"

    def test_to_trace_is_serialisable(self, base_state):
        import json
        trace = base_state.to_trace()
        dumped = json.dumps(trace)  # must not raise
        assert "run_id" in dumped
