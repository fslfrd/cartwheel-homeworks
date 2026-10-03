"""The review interface shows timing from either trace source.

The raw Langfuse export and ``langfuse_io.fetch_traces`` carry the same
measurements under different field names. The loader decides which schema a
trace uses from the trace itself, and a trace with no timing reports ``None``
rather than zero.
"""

from analysis.review_app import loader


def _export_trace(latency, obs_latency):
    return {
        "id": "t1",
        "timestamp": "2026-09-21T02:31:32.760Z",
        "latency": latency,
        "observations": [
            {"type": "TOOL", "name": "get_order", "startTime": "2026-09-21T02:31:36.032Z", "latency": obs_latency},
        ],
    }


def _langfuse_trace(latency, obs_latency):
    return {
        "id": "t1",
        "timestamp": "2026-09-21T02:31:32.760Z",
        "observations": [
            {"type": "SPAN", "name": "cartwheel.session_message", "start_time": "2026-09-21T02:31:32.760", "latency_seconds": latency},
            {"type": "TOOL", "name": "get_order", "start_time": "2026-09-21T02:31:36.032", "latency_seconds": obs_latency},
        ],
    }


def test_schema_is_decided_from_the_trace():
    assert loader._timing_schema(_export_trace(8.374, 0.002)) == "export"
    assert loader._timing_schema(_langfuse_trace(8.374, 0.002)) == "langfuse"
    assert loader._timing_schema({"id": "t", "observations": [{"type": "TOOL"}]}) is None


def test_both_sources_give_the_same_session_timing():
    export = loader._session_timing([_export_trace(8.374, 0.002)])
    langfuse = loader._session_timing([_langfuse_trace(8.374, 0.002)])
    assert export == langfuse == {"work": 8.37, "elapsed": 8.37, "turns": [8.374]}


def test_both_sources_give_the_same_tool_duration():
    for trace in (_export_trace(8.374, 0.002), _langfuse_trace(8.374, 0.002)):
        tools, _ = loader._timing_index([trace])
        assert tools == [("get_order", 0.002)]


def test_a_trace_without_timing_reports_none_not_zero():
    bare = {"id": "t", "timestamp": "2026-09-21T02:31:32.760Z", "observations": [{"type": "TOOL", "name": "get_order"}]}
    assert loader._session_timing([bare]) is None
    tools, _ = loader._timing_index([bare])
    assert tools == [("get_order", None)]


def test_a_genuine_zero_is_kept():
    timing = loader._session_timing([_export_trace(0.0, 0.0)])
    assert timing is not None and timing["work"] == 0.0
