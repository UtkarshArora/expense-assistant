"""
Tests for the agent loop: conversation history, the step limit, and tool
dispatch errors. The Anthropic client is mocked, so no API key is needed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from app import agent
from app.agent import FALLBACK_MESSAGE, MAX_TOOL_ITERATIONS, build_history, run_agent


class FakeAPIError(anthropic.APIError):
    """An APIError without the SDK's HTTP request plumbing."""

    def __init__(self) -> None:
        Exception.__init__(self, "simulated API failure")


def text_response(text: str):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
    )


def tool_response(name: str, tool_input: dict, tool_id: str = "toolu_1"):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)],
    )


@pytest.fixture
def create(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(agent.client.messages, "create", mock)
    return mock


@pytest.fixture
def fake_tool(monkeypatch):
    tool = MagicMock(return_value="tool output")
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "fake_tool", tool)
    return tool


# ----------------------------------------------------------------------
# build_history
# ----------------------------------------------------------------------

def test_build_history_keeps_alternating_text_turns():
    turns = [("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2")]
    assert build_history(turns) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_build_history_drops_leading_assistant_from_truncated_window():
    assert build_history([("assistant", "a0"), ("user", "q1"), ("assistant", "a1")]) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]


def test_build_history_drops_trailing_unanswered_user_turn():
    assert build_history([("user", "q1"), ("assistant", "a1"), ("user", "orphan")]) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]


def test_build_history_merges_consecutive_roles_and_skips_empty():
    turns = [("user", "q1"), ("user", "q1b"), ("assistant", ""), ("assistant", "a1")]
    assert build_history(turns) == [
        {"role": "user", "content": "q1\n\nq1b"},
        {"role": "assistant", "content": "a1"},
    ]


def test_build_history_empty():
    assert build_history([]) == []


# ----------------------------------------------------------------------
# run_agent: history
# ----------------------------------------------------------------------

def test_history_is_sent_before_the_new_message(create):
    create.return_value = text_response("Engineering spent $X.")
    history = [
        {"role": "user", "content": "What did Sales spend on client meals in Q2?"},
        {"role": "assistant", "content": "Sales spent $Y."},
    ]

    text, tool_calls, truncated = run_agent(history, "What about Engineering?")

    sent = create.call_args.kwargs["messages"]
    assert sent[:2] == history
    assert sent[2] == {"role": "user", "content": "What about Engineering?"}
    assert (text, tool_calls, truncated) == ("Engineering spent $X.", [], False)


def test_history_contains_no_tool_blocks(create):
    # Invariant 2: only text history is replayed; tool calls stay UI-only.
    create.return_value = text_response("ok")
    history = build_history([("user", "q1"), ("assistant", "a1")])

    run_agent(history, "q2")

    # The mock holds a reference to the live list; the loop appends the
    # assistant reply after the call, so look only at what was sent.
    sent = create.call_args.kwargs["messages"][:3]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    for msg in sent:
        assert isinstance(msg["content"], str)


def test_run_agent_does_not_mutate_caller_history(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {}), text_response("done")]
    history = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    snapshot = [dict(m) for m in history]

    run_agent(history, "q2")

    assert history == snapshot


# ----------------------------------------------------------------------
# run_agent: tool dispatch
# ----------------------------------------------------------------------

def test_tool_call_is_recorded_and_result_sent_back(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {"x": 1}), text_response("done")]

    text, tool_calls, truncated = run_agent([], "q")

    fake_tool.assert_called_once_with(x=1)
    assert tool_calls == [{"name": "fake_tool", "input": {"x": 1}, "output": "tool output"}]
    result = create.call_args.kwargs["messages"][-2]["content"][0]
    assert result == {"type": "tool_result", "tool_use_id": "toolu_1", "content": "tool output"}
    assert (text, truncated) == ("done", False)


def test_unknown_tool_returns_error_result_instead_of_raising(create):
    create.side_effect = [tool_response("no_such_tool", {}), text_response("sorry")]

    text, tool_calls, _ = run_agent([], "q")

    result = create.call_args.kwargs["messages"][-2]["content"][0]
    assert result["is_error"] is True
    assert "unknown tool" in result["content"]
    assert text == "sorry"
    assert tool_calls[0]["name"] == "no_such_tool"


def test_bad_tool_input_returns_error_result(create, fake_tool):
    fake_tool.side_effect = TypeError("unexpected keyword argument 'bogus'")
    create.side_effect = [tool_response("fake_tool", {"bogus": 1}), text_response("retrying")]

    run_agent([], "q")

    result = create.call_args.kwargs["messages"][-2]["content"][0]
    assert result["is_error"] is True
    assert "invalid input" in result["content"]


def test_tool_crash_does_not_leak_exception_message(create, fake_tool):
    fake_tool.side_effect = RuntimeError("secret connection string")
    create.side_effect = [tool_response("fake_tool", {}), text_response("ok")]

    run_agent([], "q")

    result = create.call_args.kwargs["messages"][-2]["content"][0]
    assert result["is_error"] is True
    assert "secret" not in result["content"]
    assert "RuntimeError" in result["content"]


# ----------------------------------------------------------------------
# run_agent: step limit
# ----------------------------------------------------------------------

def test_step_limit_forces_a_final_answer_without_tools(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {})] * MAX_TOOL_ITERATIONS + [
        text_response("Partial: here's what I found.")
    ]

    text, tool_calls, truncated = run_agent([], "q")

    assert create.call_count == MAX_TOOL_ITERATIONS + 1
    final_kwargs = create.call_args.kwargs
    assert final_kwargs["tool_choice"] == {"type": "none"}
    assert "tools" in final_kwargs  # history has tool_use blocks
    last_user = final_kwargs["messages"][-1]
    assert last_user["role"] == "user"
    assert last_user["content"][0]["type"] == "tool_result"
    assert last_user["content"][-1] == {"type": "text", "text": agent.STEP_LIMIT_NOTE}
    assert text == "Partial: here's what I found."
    assert len(tool_calls) == MAX_TOOL_ITERATIONS
    assert truncated is True


def test_step_limit_uses_canned_fallback_when_final_call_fails(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {})] * MAX_TOOL_ITERATIONS + [FakeAPIError()]

    text, _, truncated = run_agent([], "q")

    assert text == FALLBACK_MESSAGE
    assert truncated is True


def test_step_limit_uses_canned_fallback_when_final_answer_is_empty(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {})] * MAX_TOOL_ITERATIONS + [
        text_response("   ")
    ]

    text, _, truncated = run_agent([], "q")

    assert text == FALLBACK_MESSAGE
    assert truncated is True


def test_answer_on_last_allowed_iteration_is_not_truncated(create, fake_tool):
    create.side_effect = [tool_response("fake_tool", {})] * (MAX_TOOL_ITERATIONS - 1) + [
        text_response("made it")
    ]

    text, _, truncated = run_agent([], "q")

    assert create.call_count == MAX_TOOL_ITERATIONS
    assert (text, truncated) == ("made it", False)
