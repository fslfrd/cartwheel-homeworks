"""Turn Cartwheel traces into session records the review interface can read.

Cartwheel writes one Langfuse trace per user turn, so a three-turn
conversation arrives as three traces. The supplied
``analysis.helpers.normalization`` already merges them by
``cartwheel.session_id``; this module adds the parts the reading surface
needs and the reference interface does not provide:

* a one-line **digest** for every tool result, so the outcome of a call is
  visible without expanding anything,
* a **ribbon** of tool names, so the shape of a session is readable before
  the prose is,
* **turn indices** on every message, so the seam between a user's first
  question and their followup is visible,
* the full list of **member trace ids**, so a label recorded once against a
  session can be written to every underlying Langfuse trace, and
* the scenario's ``expected`` block, carried through for the collapsed
  ground-truth panel.

The source is either the committed Homework 3 export or the live Langfuse
project. Both paths end in the same record shape.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from analysis.helpers.normalization import normalize_traces

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT = REPO_ROOT / "traces" / "support_traces.json"
DEFAULT_SCENARIOS = REPO_ROOT / "scenarios" / "support_scenarios.jsonl"
# Targeted scenarios generated for Homework 5; read alongside the Homework 3 plan.
EXTRA_SCENARIOS = (REPO_ROOT / "scenarios" / "hw5_scenarios.jsonl",)

# Scenario families that belong to the Homework 4 review frame. The Langfuse
# project also holds pilot and ad-hoc traces from earlier sessions; they ran
# against a different world state, so they are out of frame.
FRAME_PREFIX = "support-"

MAX_DIGEST_CHARS = 110


# ---------------------------------------------------------------------------
# Tool digests
# ---------------------------------------------------------------------------


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _order_line(order: dict[str, Any]) -> str:
    """Summarize one order record the way a reviewer reads it."""
    bits = [f"#{order.get('order_id')}"]
    if order.get("status"):
        bits.append(str(order["status"]))
    if "refund_eligible" in order:
        bits.append(f"refund_eligible={str(order['refund_eligible']).lower()}")
    if order.get("total_usd") is not None:
        bits.append(_money(order["total_usd"]))
    return " · ".join(bits)


def _digest_ok(name: str, payload: dict[str, Any]) -> str:
    """One-line summary of a successful tool result.

    Each branch picks the fields a reviewer actually judges against: the
    refund decision for an order, the policy identifier for a citation, the
    ticket for an escalation. The raw JSON stays one keystroke away for
    anything this omits.
    """
    if name == "get_order":
        order = payload.get("order") or {}
        line = _order_line(order)
        if order.get("store_name"):
            line += f" · {order['store_name']}"
        return line

    if name in ("find_order", "list_my_orders"):
        orders = payload.get("orders") or []
        if not orders:
            return "0 orders"
        head = _order_line(orders[0])
        extra = f" (+{len(orders) - 1} more)" if len(orders) > 1 else ""
        return f"{len(orders)} order{'s' if len(orders) != 1 else ''} · {head}{extra}"

    if name == "search_products":
        products = payload.get("products") or []
        count = payload.get("count", len(products))
        if not products:
            return "0 products"
        top = products[0]
        title = top.get("title") or "(untitled)"
        return f"{count} products · {title} {_money(top.get('price_usd', top.get('price_cents')))}"

    if name == "search_help_center":
        results = payload.get("results") or []
        ids = [r.get("policy_id") for r in results if r.get("policy_id")]
        if not ids:
            return "0 results"
        return f"{len(results)} results · {', '.join(ids[:4])}"

    if name == "get_policy":
        return f"{payload.get('policy_id')} · {payload.get('title', '')}".strip(" ·")

    if name == "issue_refund":
        return (
            f"{payload.get('status')} · {_money(payload.get('amount_usd'))} "
            f"· refund #{payload.get('refund_id')}"
        )

    if name == "cancel_order":
        return f"#{payload.get('order_id')} · {payload.get('status')}"

    if name == "escalate_to_human":
        return f"ticket #{payload.get('ticket_id')} · sla {payload.get('sla_hours')}h"

    known = {k: v for k, v in payload.items() if k != "ok"}
    return json.dumps(known)[:MAX_DIGEST_CHARS] if known else "ok"


def digest(name: str, content: Any) -> dict[str, Any]:
    """Return ``{ok, text, error}`` summarizing one tool result.

    ``ok`` drives the colour of the digest line, ``error`` is surfaced as a
    badge, and ``text`` is the always-visible summary.
    """
    if not isinstance(content, dict):
        return {"ok": None, "text": str(content)[:MAX_DIGEST_CHARS], "error": None}

    if content.get("ok") is False:
        error = content.get("error") or "error"
        reason = content.get("reason") or ""
        return {"ok": False, "text": reason[:MAX_DIGEST_CHARS], "error": error}

    try:
        text = _digest_ok(name, content)
    except Exception:  # a malformed payload must never break the reading view
        text = json.dumps(content)[:MAX_DIGEST_CHARS]
    return {"ok": True, "text": text[:MAX_DIGEST_CHARS], "error": None}


# ---------------------------------------------------------------------------
# Session records
# ---------------------------------------------------------------------------


def _timing_schema(trace: dict[str, Any]) -> str | None:
    """Which timing schema a trace carries, decided from the trace itself.

    ``export`` is the raw Langfuse export (``latency``, ``startTime``);
    ``langfuse`` is what ``langfuse_io.fetch_traces`` returns
    (``latency_seconds``, ``start_time``, no trace-level figure). ``None`` means
    the trace carries no timing, and nothing is shown for it: a missing value
    is never reported as zero.
    """
    observations = trace.get("observations") or []
    if "latency" in trace or any("latency" in o for o in observations):
        return "export"
    if any("latency_seconds" in o for o in observations):
        return "langfuse"
    return None


def _obs_start(trace: dict[str, Any], obs: dict[str, Any]) -> str:
    key = "startTime" if _timing_schema(trace) == "export" else "start_time"
    return obs.get(key) or ""


def _obs_latency(trace: dict[str, Any], obs: dict[str, Any]) -> float | None:
    schema = _timing_schema(trace)
    if schema == "export":
        return obs.get("latency")
    if schema == "langfuse":
        return obs.get("latency_seconds")
    return None


def _trace_latency(trace: dict[str, Any]) -> float | None:
    """A turn's latency, or None when the trace carries no timing.

    The Langfuse fetch has no trace-level figure, so there it is the root
    span's, which is also how the export's figure is defined.
    """
    schema = _timing_schema(trace)
    if schema == "export":
        return trace.get("latency")
    if schema == "langfuse":
        root = next(
            (o for o in trace.get("observations") or [] if o.get("name") == "cartwheel.session_message"),
            None,
        )
        return root.get("latency_seconds") if root else None
    return None


def _timing_index(
    traces: list[dict[str, Any]],
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Collect tool and generation durations for one session, in time order.

    Returns ``(tools, generations)`` where each entry is ``(key, seconds)``:
    the tool name for a tool call, the emitted text for a model reply.
    """
    tools: list[tuple[str, float]] = []
    generations: list[tuple[str, float]] = []
    for trace in traces:
        observations = sorted(
            trace.get("observations") or [], key=lambda o, t=trace: _obs_start(t, o)
        )
        for obs in observations:
            latency = _obs_latency(trace, obs)
            if obs.get("type") == "TOOL":
                tools.append((obs.get("name") or "", latency))
            elif obs.get("type") == "GENERATION":
                for item in obs.get("output") or []:
                    if not isinstance(item, dict):
                        continue
                    for part in item.get("parts") or []:
                        content = (part or {}).get("content") or ""
                        if part.get("type") == "text" and content.strip():
                            generations.append((content, latency))
    return tools, generations


def _attach_durations(
    messages: list[dict[str, Any]],
    tools: list[tuple[str, float]],
    generations: list[tuple[str, float]],
) -> None:
    """Give each message the duration of the observation that produced it.

    Matching is by content, not by position: a tool call takes the next
    unconsumed observation carrying the same tool name, and a reply takes the
    generation that emitted that exact text. Position-based alignment would
    silently mis-attribute a duration if the normalizer's ordering changed.
    A message with no match keeps ``duration = None`` and shows no time.
    """
    by_text: dict[str, list[float]] = {}
    for text, latency in generations:
        by_text.setdefault(text, []).append(latency)

    cursor = 0
    pending_tool: float | None = None
    for message in messages:
        role = message.get("role")
        if role == "tool_call":
            name = message.get("name")
            match = next(
                (i for i in range(cursor, len(tools)) if tools[i][0] == name), None
            )
            if match is None:
                pending_tool = None
            else:
                pending_tool = tools[match][1]
                cursor = match + 1
            message["duration"] = pending_tool
        elif role == "tool_result":
            # The call and its result come from one observation.
            message["duration"] = pending_tool
        elif role == "assistant":
            bucket = by_text.get(message.get("text") or "")
            message["duration"] = bucket.pop(0) if bucket else None


def _session_timing(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Two totals for a session, plus one per turn, or None without timing.

    ``work`` sums each turn's own latency: time the agent spent working.
    ``elapsed`` runs from the first turn's start to the last turn's end, so it
    also contains the gap between turns, which for these recorded runs is
    harness overhead rather than anything the agent did. The two are equal for
    a single-turn session.
    """
    turns = [_trace_latency(t) for t in traces]
    known = [t for t in turns if t is not None]
    if not known:
        return None
    work = sum(known)
    elapsed = work
    last_latency = turns[-1]
    if len(traces) > 1 and last_latency is not None:
        first, last = traces[0], traces[-1]
        try:
            start = datetime.fromisoformat(first["timestamp"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
            elapsed = (end - start).total_seconds() + last_latency
        except (KeyError, ValueError):
            elapsed = work
    return {"work": round(work, 2), "elapsed": round(elapsed, 2), "turns": turns}


def _load_scenarios(path: Path | None) -> dict[str, dict[str, Any]]:
    paths = [path] if path else [DEFAULT_SCENARIOS, *EXTRA_SCENARIOS]
    out = {}
    for item in paths:
        if not item.exists():
            continue
        for line in item.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["id"]] = row
    return out


def _annotate_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy the message list, adding a turn index and tool digests.

    A turn begins at each user message, which is how the reviewer sees the
    seam between an opening question and a followup.
    """
    out: list[dict[str, Any]] = []
    turn = 0
    for index, message in enumerate(messages):
        item = dict(message)
        if item.get("role") == "user":
            turn += 1
        item["turn"] = turn
        item["idx"] = index
        if item.get("role") == "tool_result":
            item["digest"] = digest(item.get("name", ""), item.get("content"))
        out.append(item)
    return out


def _session_flags(messages: list[dict[str, Any]]) -> list[str]:
    """Session-level badges worth seeing in the sidebar without reading."""
    flags: list[str] = []
    errors = {
        m["digest"]["error"]
        for m in messages
        if m.get("role") == "tool_result" and m.get("digest", {}).get("error")
    }
    if "permission_denied" in errors:
        flags.append("permission_denied")
    if errors - {"permission_denied"}:
        flags.append("tool_error")
    if not any(m.get("role") == "tool_call" for m in messages):
        flags.append("no_tools")
    return flags


def build_records(
    traces: list[dict[str, Any]],
    scenarios: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge raw traces into one record per session, ready for the UI."""
    scenarios = scenarios if scenarios is not None else _load_scenarios(None)

    # Member traces per session, in time order: the ids drive score fan-out,
    # and the traces themselves carry the timing each message is given.
    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        attributes = (trace.get("metadata") or {}).get("attributes") or {}
        session_id = attributes.get("cartwheel.session_id")
        if session_id:
            members[session_id].append(trace)
    for values in members.values():
        values.sort(key=lambda t: t.get("timestamp") or "")

    records = []
    for merged in normalize_traces(traces):
        attributes = merged.get("metadata") or {}
        session_id = attributes.get("cartwheel.session_id")
        scenario_id = attributes.get("cartwheel.scenario_id")
        messages = _annotate_turns(merged.get("trace") or [])
        scenario = scenarios.get(scenario_id or "", {})

        session_traces = members.get(session_id, [])
        _attach_durations(messages, *_timing_index(session_traces))

        records.append(
            {
                "session_id": session_id,
                "trace_id": merged["trace_id"],
                "member_trace_ids": [t["id"] for t in session_traces],
                "timing": _session_timing(session_traces),
                "scenario_id": scenario_id,
                "timestamp": merged.get("timestamp"),
                "meta": {
                    "role": attributes.get("cartwheel.user_role"),
                    "user_id": attributes.get("cartwheel.user_id"),
                    "store_id": attributes.get("cartwheel.store_id"),
                    "prompt_version": attributes.get("cartwheel.prompt_version"),
                    "turn_count": sum(1 for m in messages if m["role"] == "user"),
                    "scenario_group": scenario.get("scenario_group"),
                    "intent": (scenario.get("tuple") or {}).get("intent"),
                },
                "ribbon": [m["name"] for m in messages if m["role"] == "tool_call"],
                "flags": _session_flags(messages),
                "opening": next(
                    (m.get("text") or "" for m in messages if m["role"] == "user"), ""
                ),
                "expected": scenario.get("expected"),
                "features": merged.get("features", {}),
                "trace": messages,
            }
        )

    records.sort(key=lambda r: r["scenario_id"] or "")
    return records


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def from_export(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the committed Homework 3 trace export."""
    path = path or DEFAULT_EXPORT
    payload = json.loads(path.read_text())
    return build_records(payload["traces"])


def from_langfuse(prefix: str = FRAME_PREFIX) -> list[dict[str, Any]]:
    """Load the live Langfuse project, keeping the Module 1 scenario family.

    Langfuse is canonical. The export is the offline fallback the handout
    permits when the project is unavailable.
    """
    from analysis.helpers import langfuse_io

    traces = langfuse_io.fetch_traces()
    kept = [
        t
        for t in traces
        if str(
            ((t.get("metadata") or {}).get("attributes") or {}).get(
                "cartwheel.scenario_id"
            )
            or ""
        ).startswith(prefix)
    ]
    return build_records(kept)


def load(source: str = "export") -> list[dict[str, Any]]:
    """Load session records from ``export`` or ``langfuse``."""
    if source == "langfuse":
        return from_langfuse()
    if source == "export":
        return from_export()
    raise ValueError(f"unknown source: {source!r}")
