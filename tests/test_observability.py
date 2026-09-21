"""Homework 2 authentication and instrumentation tests.

Offline by design: no Langfuse, no Docker, and no model provider key. The
endpoint tests exercise the identity the server issues; the span test checks
the application attributes that Part A adds to the tool span.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.auth import AuthContext
from observability.instrument import record_tool_result
from server import app as server_app


def test_session_creation_rejects_a_claimed_role_that_is_not_the_stored_role(
    world: dict,
) -> None:
    server_app._SESSIONS.clear()
    with pytest.raises(HTTPException) as denied:
        server_app.create_session(server_app.SessionCreate(user_id=1, role="support"))
    assert denied.value.status_code == 403
    assert server_app._SESSIONS == {}


def test_a_token_from_one_session_cannot_authorize_another(world: dict) -> None:
    server_app._SESSIONS.clear()
    shopper = server_app.create_session(
        server_app.SessionCreate(user_id=1, role="shopper")
    )
    merchant = server_app.create_session(
        server_app.SessionCreate(user_id=9002, role="merchant")
    )
    with pytest.raises(HTTPException) as denied:
        server_app._authorize(shopper["session_id"], f"Bearer {merchant['token']}")
    assert denied.value.status_code == 403


def test_tool_spans_carry_the_authenticated_caller_and_permission_decision() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    merchant = AuthContext(user_id=9002, role="merchant", store_id=2)
    with tracer.start_as_current_span("execute_tool get_order"):
        record_tool_result(
            merchant,
            {"ok": False, "error": "permission_denied", "reason": "outside store"},
        )
    with tracer.start_as_current_span("execute_tool list_my_orders"):
        record_tool_result(AuthContext(user_id=1, role="shopper"), {"ok": True})

    denied, allowed = (span.attributes for span in exporter.get_finished_spans())
    assert denied["cartwheel.user_role"] == "merchant"
    assert denied["cartwheel.user_id"] == "9002"
    assert denied["cartwheel.store_id"] == "2"
    assert denied["cartwheel.permission_denied"] is True
    assert denied["cartwheel.permission_denied.reason"] == "outside store"

    assert allowed["cartwheel.permission_denied"] is False
    assert "cartwheel.permission_denied.reason" not in allowed
    assert "cartwheel.store_id" not in allowed
