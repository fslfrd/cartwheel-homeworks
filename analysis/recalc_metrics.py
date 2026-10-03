"""Recompute a judge's metrics from saved predictions, independently.

This reads only three committed files and does not use the course helpers, so
it is an independent check of the saved report:

* ``analysis/state/hw5_labels/<mode>.jsonl``  human labels, 1 = Pass, 0 = Fail
* ``analysis/state/splits.json``              which trace ids are in each split
* ``analysis/state/judges/<judge_id>.json``   the judge's cached predictions

    uv run python -m analysis.recalc_metrics writes_without_confirming_match-v0 test
    uv run python -m analysis.recalc_metrics writes_without_confirming_match-v0 dev

Pass is the positive class. TPR = TP / (TP + FN) and TNR = TN / (TN + FP). The
intervals are 95% Wilson score intervals. The test split is refused unless the
judge was frozen, the same rule the pipeline enforces.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

STATE = Path(__file__).resolve().parent / "state"
REPORT = Path(__file__).resolve().parent / "report"
Z = 1.96


def wilson(successes: int, total: int, z: float = Z) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial rate."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_labels(mode: str) -> dict[str, int]:
    """Live label per trace id: rows marked ``superseded_by`` are history."""
    labels = {}
    for line in (STATE / "hw5_labels" / f"{mode}.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("superseded_by"):
            labels[row["trace_id"]] = int(row["label"])
    return labels


def recompute(judge_id: str, split: str) -> dict:
    judge = json.loads((STATE / "judges" / f"{judge_id}.json").read_text())
    if split == "test" and judge.get("status") != "frozen" and not judge.get("frozen_at"):
        raise SystemExit(f"{judge_id} is not frozen, so the test split stays closed")
    mode = judge["mode"]
    ids = json.loads((STATE / "splits.json").read_text())[mode][split]
    labels = load_labels(mode)
    predictions = judge["predictions"][judge["prompt_hash"]]

    tp = fn = tn = fp = 0
    wrong = []
    for trace_id in ids:
        human, judged = labels[trace_id], int(predictions[trace_id])  # both 1 = Pass
        if human == 1 and judged == 1:
            tp += 1
        elif human == 1:
            fn += 1
            wrong.append(trace_id)
        elif judged == 0:
            tn += 1
        else:
            fp += 1
            wrong.append(trace_id)
    tpr, tnr = tp / (tp + fn), tn / (tn + fp)
    return {
        "judge_id": judge_id, "model": judge["model"], "split": split, "n": len(ids),
        "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "tpr": tpr, "tpr_interval": wilson(tp, tp + fn),
        "tnr": tnr, "tnr_interval": wilson(tn, tn + fp),
        "agreement": (tp + tn) / len(ids), "disagreements": wrong,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("judge_id")
    parser.add_argument("split", choices=("dev", "test"))
    args = parser.parse_args()
    r = recompute(args.judge_id, args.split)

    print(f"{r['judge_id']} ({r['model']}) on {r['split']}, n = {r['n']}")
    print("                 human Pass   human Fail")
    print(f"  judge Pass     {r['tp']:>8}     {r['fp']:>8}   (TP, FP)")
    print(f"  judge Fail     {r['fn']:>8}     {r['tn']:>8}   (FN, TN)")
    print(f"  TPR = {r['tp']}/{r['tp'] + r['fn']} = {r['tpr']:.3f}  95% CI [{r['tpr_interval'][0]:.3f}, {r['tpr_interval'][1]:.3f}]")
    print(f"  TNR = {r['tn']}/{r['tn'] + r['fp']} = {r['tnr']:.3f}  95% CI [{r['tnr_interval'][0]:.3f}, {r['tnr_interval'][1]:.3f}]")
    print(f"  agreement = {r['agreement']:.3f}")

    saved = REPORT / f"{args.split}-{args.judge_id}.json"
    if saved.exists():
        s = json.loads(saved.read_text())
        same = (s["tp"], s["fn"], s["tn"], s["fp"]) == (r["tp"], r["fn"], r["tn"], r["fp"])
        print(f"  matches the saved report {saved.name}: {'yes' if same else 'NO'}")


if __name__ == "__main__":
    main()
