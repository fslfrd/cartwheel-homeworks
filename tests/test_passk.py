"""pass@k, pass^k and the CI rule, checked beyond the supplied worked numbers."""

from itertools import combinations

import pytest

from tests.eval.passk import case_passes, pass_at_k, pass_hat_k


def _brute_force(n: int, c: int, k: int) -> tuple[float, float]:
    """Draw every size-k subset of n runs (c of them passes) and count directly."""
    runs = [1] * c + [0] * (n - c)
    subsets = list(combinations(range(n), k))
    any_pass = sum(1 for s in subsets if any(runs[i] for i in s))
    all_pass = sum(1 for s in subsets if all(runs[i] for i in s))
    return any_pass / len(subsets), all_pass / len(subsets)


@pytest.mark.parametrize("n", [1, 2, 5, 7])
def test_estimators_match_counting_every_subset(n: int) -> None:
    for c in range(n + 1):
        for k in range(1, n + 1):
            at_k, hat_k = _brute_force(n, c, k)
            assert pass_at_k(n, c, k) == pytest.approx(at_k)
            assert pass_hat_k(n, c, k) == pytest.approx(hat_k)


def test_pass_at_k_never_falls_and_pass_hat_k_never_rises_with_k() -> None:
    for c in range(0, 16):
        at = [pass_at_k(15, c, k) for k in range(1, 16)]
        hat = [pass_hat_k(15, c, k) for k in range(1, 16)]
        assert at == sorted(at)
        assert hat == sorted(hat, reverse=True)


def test_the_two_views_disagree_on_the_same_agent() -> None:
    # Lecture example: 6 of 8 reads as 1.000 for capability and 0.214 for reliability.
    assert pass_at_k(8, 6, 4) == pytest.approx(1.0)
    assert pass_hat_k(8, 6, 4) == pytest.approx(15 / 70)


@pytest.mark.parametrize("k", [1, 3, 5])
def test_all_pass_and_all_fail_are_exact_at_every_k(k: int) -> None:
    assert pass_at_k(5, 5, k) == 1.0 and pass_hat_k(5, 5, k) == 1.0
    assert pass_at_k(5, 0, k) == 0.0 and pass_hat_k(5, 0, k) == 0.0


def test_the_homework_baselines_give_these_values() -> None:
    # e-007 passed 2 of 5, e-011 passed 1 of 5.
    assert pass_at_k(5, 2, 1) == pytest.approx(0.4)
    assert pass_at_k(5, 2, 3) == pytest.approx(0.9)
    assert pass_at_k(5, 2, 5) == pytest.approx(1.0)
    assert pass_hat_k(5, 2, 5) == 0.0
    assert pass_at_k(5, 1, 3) == pytest.approx(0.6)


@pytest.mark.parametrize(
    "args",
    [(0, 0, 1), (5, -1, 1), (5, 6, 1), (5, 2, 0), (5, 2, 6)],
)
def test_impossible_counts_are_rejected(args) -> None:
    with pytest.raises(ValueError):
        pass_at_k(*args)
    with pytest.raises(ValueError):
        pass_hat_k(*args)


def test_a_regression_case_blocks_on_any_failed_run() -> None:
    for passes in range(0, 5):
        decision = case_passes("regression", passes, 5)
        assert decision["decision"] == "block"
        assert f"failed {5 - passes} of 5" in decision["reason"]
    ok = case_passes("regression", 5, 5)
    assert ok["decision"] == "pass" and "all 5" in ok["reason"]


def test_a_capability_case_never_blocks_and_reports_its_numbers() -> None:
    for passes in range(0, 6):
        assert case_passes("capability", passes, 5, 0.6)["decision"] == "pass"
    reason = case_passes("capability", 2, 5, 0.6)["reason"]
    assert reason == "capability case passed 2 of 5, baseline 0.6, not blocking"
    assert "baseline" not in case_passes("capability", 2, 5)["reason"]


def test_case_passes_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        case_passes("flaky", 3, 5)
    with pytest.raises(ValueError):
        case_passes("regression", 6, 5)
    with pytest.raises(ValueError):
        case_passes("regression", -1, 5)
    with pytest.raises(ValueError):
        case_passes("capability", 2, 5, 1.5)
