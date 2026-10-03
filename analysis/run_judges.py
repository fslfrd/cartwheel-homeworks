"""Homework 5 judge pipeline for ``writes_without_confirming_match``.

Part B lives here: ``prepare_inputs`` saves the exact evidence the judge sees,
and ``split_data`` divides the human labels into training, development and
test. Label convention for Homework 5 is **1 = Pass, 0 = Fail**.

    uv run python -m analysis.run_judges prepare
    uv run python -m analysis.run_judges split
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.review_app import hw5, loader

MODE = hw5.MODE
STATE_DIR = Path(__file__).resolve().parent / "state"
INPUTS_PATH = STATE_DIR / "hw5_trace_inputs.json"

# What the judge may see. Everything else on a session record is review
# machinery or answer-bearing: scenario ids and expected metadata, flags,
# annotations, labels, the tier a session was queued under, step indexes and
# timings. None of it is copied into the saved inputs.
_ALLOWED_ROLES = {"user", "assistant", "tool_call", "tool_result"}


def _judge_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Reduce a review-interface message to what the judge may see.

    The tool name goes inside the data of a tool message. The shared trace
    flattener prints only a call's arguments, so without it a ``cancel_order``
    and a ``get_order`` would be hard to tell apart, and whether the agent
    wrote at all is the thing the judge has to decide.
    """
    role = message.get("role")
    if role not in _ALLOWED_ROLES:
        return None
    if role in ("user", "assistant"):
        return {"role": role, "text": message.get("text") or ""}
    name = message.get("name") or ""
    if role == "tool_call":
        return {"role": role, "name": name, "arguments": {"tool": name, "arguments": message.get("arguments")}}
    return {"role": role, "name": name, "content": {"tool": name, "result": message.get("content")}}


def prepare_inputs(source: str = "langfuse") -> list[dict[str, Any]]:
    """Save one judge input per labelled conversation.

    The eligible set is every session with a live Homework 5 label. Each
    record carries the label file's ``trace_id`` and the whole conversation
    (user turns, lookups, writes, tool results and replies), because whether
    the user had spoken before the write is decided across turns.
    """
    from observability.instrument import load_env

    load_env()
    labels = hw5.live_labels(STATE_DIR)
    records = {r["session_id"]: r for r in loader.load(source)}
    missing = sorted(set(labels) - set(records))
    if missing:
        raise ValueError(f"labelled sessions missing from the {source} traces: {missing[:5]}")

    out = []
    for session_id, label in sorted(labels.items(), key=lambda kv: records[kv[0]]["scenario_id"] or ""):
        record = records[session_id]
        if record["trace_id"] != label["trace_id"]:
            raise ValueError(f"trace id mismatch for {record['scenario_id']}")
        messages = [m for m in (_judge_message(x) for x in record["trace"]) if m]
        out.append({"trace_id": record["trace_id"], "trace": messages})

    if len(out) != len(labels):
        raise ValueError("expected one input record per eligible label")
    INPUTS_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


def split_data(mode: str = MODE) -> dict[str, list[str]]:
    """Split the labels 20/40/40 with seed 7. Run once, then leave it alone."""
    from analysis.helpers import split_labels

    records = json.loads(INPUTS_PATH.read_text())
    return split_labels(
        mode,
        fractions=(0.20, 0.40, 0.40),
        seed=7,
        min_per_class=10,
        eligible_trace_ids=[record["trace_id"] for record in records],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "split"))
    args = parser.parse_args()
    if args.step == "prepare":
        records = prepare_inputs()
        print(f"saved {len(records)} judge inputs to {INPUTS_PATH}")
    else:
        splits = split_data()
        print({name: len(ids) for name, ids in splits.items()})


if __name__ == "__main__":
    main()
