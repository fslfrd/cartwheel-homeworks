"""Homework 5 labelling queue for ``writes_without_confirming_match``.

The queue is the review order, not a verdict. Each tier is a heuristic over
the recorded tool calls, there to put the sessions most likely to be Fail in
front of the reviewer first. Every Pass or Fail is the reviewer's own, written
through ``write_label``.

Label convention: **1 = Pass, 0 = Fail**, the reverse of the Homework 4 labels
in ``state/labels/``. The two live in separate files and are never mixed.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

MODE = "writes_without_confirming_match"
WRITES = {"issue_refund", "cancel_order"}
LOOKUPS = {"find_order", "list_my_orders"}
SCOPE_INTENTS = {"refund", "cancellation"}

TIERS = {
    "fuzzy_write": "wrote after a fuzzy lookup",
    "named_write": "wrote, order number given",
    "no_write": "no refund or cancel call",
}


def _order_id(call: dict[str, Any]) -> str:
    args = call.get("arguments")
    if isinstance(args, dict):
        return str(args.get("order_id", ""))
    match = re.search(r"order_id\W+(\d+)", str(args))
    return match.group(1) if match else ""


def classify(record: dict[str, Any]) -> str | None:
    """Return the review tier for a session, or None when out of scope."""
    if (record.get("meta") or {}).get("intent") not in SCOPE_INTENTS:
        return None
    trace = record.get("trace") or []
    calls = [m for m in trace if m.get("role") == "tool_call"]
    writes = [c for c in calls if c.get("name") in WRITES]
    if not writes:
        return "no_write"
    first = writes[0]
    order_id = _order_id(first)
    named = any(
        re.search(rf"\b{re.escape(order_id)}\b", m.get("text") or "")
        for m in trace
        if m.get("role") == "user" and int(m.get("turn") or 0) <= int(first.get("turn") or 0)
    )
    looked_up = any(c.get("name") in LOOKUPS and c["idx"] < first["idx"] for c in calls)
    return "named_write" if (named or not looked_up) else "fuzzy_write"


def build_queue(store: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = {tier: i for i, tier in enumerate(TIERS)}
    queue = []
    for record in store.values():
        tier = classify(record)
        if tier is None:
            continue
        queue.append(
            {
                "session_id": record["session_id"],
                "trace_id": record["trace_id"],
                "scenario_id": record.get("scenario_id"),
                "tier": tier,
            }
        )
    queue.sort(key=lambda q: (order[q["tier"]], q["scenario_id"] or ""))
    return queue


def label_path(state_dir: Path) -> Path:
    return state_dir / "hw5_labels" / f"{MODE}.jsonl"


def read_rows(state_dir: Path) -> list[dict[str, Any]]:
    path = label_path(state_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def live_labels(state_dir: Path) -> dict[str, dict[str, Any]]:
    """Current label per session. Superseded rows stay in the file as history."""
    return {
        row["session_id"]: row
        for row in read_rows(state_dir)
        if not row.get("superseded_by")
    }


def write_label(
    state_dir: Path, record: dict[str, Any], label: int, note: str
) -> dict[str, Any]:
    """Append a judgment, marking any earlier one for the session superseded."""
    if label not in (0, 1):
        raise ValueError("label must be 1 (Pass) or 0 (Fail)")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rows = read_rows(state_dir)
    for row in rows:
        if row.get("session_id") == record["session_id"] and not row.get("superseded_by"):
            row["superseded_by"] = ts
    new = {
        "trace_id": record["trace_id"],
        "session_id": record["session_id"],
        "scenario_id": record.get("scenario_id"),
        "mode": MODE,
        "label": label,
        "note": note,
        "source": "human",
        "ts": ts,
    }
    rows.append(new)
    path = label_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return new


def counts(state_dir: Path) -> dict[str, int]:
    live = live_labels(state_dir).values()
    return {
        "pass": sum(1 for r in live if r["label"] == 1),
        "fail": sum(1 for r in live if r["label"] == 0),
    }
