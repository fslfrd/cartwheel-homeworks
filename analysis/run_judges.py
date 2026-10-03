"""Homework 5 judge pipeline for ``writes_without_confirming_match``.

Part B: ``prepare_inputs`` saves the exact evidence the judge sees, and
``split_data`` divides the human labels into training, development and test.
Parts C and D: ``run_development`` registers a prompt version and scores it on
the development split, and ``run_test`` freezes a chosen version and scores it
once on the test split. Label convention for Homework 5 is **1 = Pass,
0 = Fail**.

    uv run python -m analysis.run_judges prepare
    uv run python -m analysis.run_judges split
    uv run python -m analysis.run_judges dev analysis/prompts/<mode>-v0.txt
    uv run python -m analysis.run_judges test <judge_id>
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from analysis.review_app import hw5, loader

MODE = hw5.MODE
STATE_DIR = Path(__file__).resolve().parent / "state"
INPUTS_PATH = STATE_DIR / "hw5_trace_inputs.json"
REPORT_DIR = Path(__file__).resolve().parent / "report"
JUDGE_MODEL = "gpt-4o-mini"  # the same model for development and the final test

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


def _use_saved_inputs() -> None:
    """Point the judge helpers at the saved inputs, not at live Langfuse."""
    from observability.instrument import load_env

    load_env()
    os.environ["CARTWHEEL_JUDGE_TRACE_SOURCE"] = str(INPUTS_PATH)


def run_development(
    mode: str, prompt_path: str | Path, model: str = JUDGE_MODEL
) -> dict[str, Any]:
    """Register a prompt version, score it on the development split, save metrics.

    Each call registers a new judge id (``<mode>-v<N>``, counted by
    registration, not by prompt file), so call it once per prompt and model. To
    resume an interrupted run, call ``run_judge`` and ``judge_alignment`` with
    the same judge id instead.
    """
    from analysis.helpers import judge_alignment, register_judge, run_judge

    _use_saved_inputs()
    record = register_judge(
        mode=mode,
        prompt_text=Path(prompt_path).read_text(),
        judge_model=model,
    )
    judge_id = record["judge_id"]
    run_judge(judge_id, split="dev", batch_size=10)
    development = judge_alignment(judge_id, split="dev")
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / f"dev-{judge_id}.json").write_text(json.dumps(development, indent=1) + "\n")
    return development


def run_test(judge_id: str) -> dict[str, Any]:
    """Freeze the chosen version, score the test split once, save metrics.

    Resuming after an interruption skips the freeze: an already frozen judge is
    scored as it stands, and completed batches are served from the cache.
    """
    from analysis.helpers import freeze_judge, judge_alignment, run_judge

    _use_saved_inputs()
    judge = json.loads((STATE_DIR / "judges" / f"{judge_id}.json").read_text())
    if judge.get("status") != "frozen":
        freeze_judge(judge_id)
    run_judge(judge_id, split="test", batch_size=10)
    test = judge_alignment(judge_id, split="test")
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / f"test-{judge_id}.json").write_text(json.dumps(test, indent=1) + "\n")
    return test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "split", "dev", "test"))
    parser.add_argument("target", nargs="?", help="prompt path for dev, judge id for test")
    parser.add_argument("--model", default=JUDGE_MODEL, help="judge model for the dev step")
    args = parser.parse_args()
    if args.step == "prepare":
        records = prepare_inputs()
        print(f"saved {len(records)} judge inputs to {INPUTS_PATH}")
    elif args.step == "split":
        splits = split_data()
        print({name: len(ids) for name, ids in splits.items()})
    elif args.step == "dev":
        print(json.dumps(run_development(MODE, args.target, args.model), indent=1))
    else:
        print(json.dumps(run_test(args.target), indent=1))


if __name__ == "__main__":
    main()
