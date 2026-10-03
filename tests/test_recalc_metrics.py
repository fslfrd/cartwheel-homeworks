"""The standalone recalculation agrees with the saved reports and the course helper."""

import json
from pathlib import Path

import pytest

from analysis import recalc_metrics
from analysis.helpers.tools import _wilson_interval

REPORT = Path(__file__).resolve().parents[1] / "analysis" / "report"
JUDGE = "writes_without_confirming_match-v0"


def test_wilson_matches_the_handout_example():
    # The handout: 16 of 20 detected is 0.80 with an interval of about 0.58 to 0.92.
    low, high = recalc_metrics.wilson(16, 20)
    assert (round(low, 2), round(high, 2)) == (0.58, 0.92)


@pytest.mark.parametrize("successes,total", [(18, 22), (12, 13), (22, 22), (0, 5), (3, 3)])
def test_wilson_agrees_with_the_course_helper(successes, total):
    mine = tuple(round(x, 4) for x in recalc_metrics.wilson(successes, total))
    assert list(mine) == list(_wilson_interval(successes, total))


@pytest.mark.parametrize("split", ["dev", "test"])
def test_recomputed_counts_match_the_saved_report(split):
    saved = json.loads((REPORT / f"{split}-{JUDGE}.json").read_text())
    r = recalc_metrics.recompute(JUDGE, split)
    assert (r["tp"], r["fn"], r["tn"], r["fp"]) == (saved["tp"], saved["fn"], saved["tn"], saved["fp"])
    assert round(r["tpr"], 4) == saved["tpr"] and round(r["tnr"], 4) == saved["tnr"]
    assert len(r["disagreements"]) == len(saved["disagreements"])


def test_the_test_split_is_refused_for_an_unfrozen_judge():
    # v1 was never frozen: its test split must stay closed.
    with pytest.raises(SystemExit):
        recalc_metrics.recompute("writes_without_confirming_match-v1", "test")
