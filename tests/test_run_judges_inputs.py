"""The judge sees the conversation and nothing that reveals the label."""

from analysis import run_judges
from analysis.helpers.normalization import normalize_trace


def test_review_machinery_is_dropped_from_every_message():
    message = {
        "role": "user", "text": "refund the mug", "turn": 1, "idx": 0,
        "duration": 1.2, "digest": {"ok": True}, "scenario_id": "support-0001",
    }
    assert run_judges._judge_message(message) == {"role": "user", "text": "refund the mug"}


def test_non_conversation_roles_are_dropped():
    assert run_judges._judge_message({"role": "observation", "text": "x"}) is None


def test_tool_name_is_in_the_data_the_judge_reads():
    call = {"role": "tool_call", "name": "cancel_order", "arguments": {"order_id": 6213}}
    result = {"role": "tool_result", "name": "cancel_order", "content": {"ok": True}}
    record = {
        "trace_id": "t1",
        "trace": [run_judges._judge_message(call), run_judges._judge_message(result)],
    }
    text = normalize_trace(record)["text"]
    assert text.count("cancel_order") == 2
    assert "6213" in text
