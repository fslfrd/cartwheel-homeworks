from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from harbor_adapter.analysis import analyze_capability_job
from harbor_adapter.export import _provider_key, export_tasks
from harbor_adapter.summary import summarize_job


def _write_cases(path: Path, cases: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(case) for case in cases) + "\n")


def test_provider_key_follows_the_selected_model() -> None:
    assert _provider_key("gpt-example") == "OPENAI_API_KEY"
    assert _provider_key("o4-mini") == "OPENAI_API_KEY"
    assert _provider_key("anthropic/example") == "ANTHROPIC_API_KEY"
    assert _provider_key("openrouter/vendor-model") == "OPENROUTER_API_KEY"


def test_export_preserves_cartwheel_formats_and_builds_harbor_task(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / "state"
    judges = state / "judges"
    judges.mkdir(parents=True)
    (judges / "response-quality-v1.json").write_text(
        json.dumps(
            {
                "judge_id": "response-quality-v1",
                "mode": "response-quality",
                "version": 1,
                "prompt_text": "The reply gives the information needed for the next step.",
                "model": "provider/frozen-judge-model",
                "status": "frozen",
            }
        )
    )
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(state))
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-101",
        "mode": "response-quality",
        "kind": "capability",
        "baseline_pass_rate": 0.6,
        "input": {
            "role": "shopper",
            "user_id": 1,
            "message": "Can I return this order?",
        },
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply explains the next step."],
            "checks": [{"check": "tool_called", "name": "get_order"}],
            "judges": {"response-quality": "pass"},
        },
    }
    _write_cases(cases_path, [case])

    output = tmp_path / "tasks"
    tasks = export_tasks(cases_path, output, require_suite=False)

    assert tasks == [output / "e-101"]
    exported = json.loads(
        (output / "e-101" / "environment" / "cartwheel" / "case.json").read_text()
    )
    assert exported == case
    task = tomllib.loads((output / "e-101" / "task.toml").read_text())
    assert task["metadata"] == {
        "case_id": "e-101",
        "kind": "capability",
        "mode": "response-quality",
    }
    rubric = (output / "e-101" / "tests" / "judge_response-quality.py").read_text()
    compile(rubric, "judge_response-quality.py", "exec")
    assert "The reply gives the information needed for the next step." in rubric
    assert "MODEL = 'provider/frozen-judge-model'" in rubric
    assert "--- Trace to evaluate ---" in rubric
    assert '"critique": "string", "result": "string"' in rubric
    assert "judge_trace_text" in rubric
    assert (output / "e-101" / "tests" / "test.sh").stat().st_mode & 0o111
    assert "harbor-rewardkit==0.2.1" in (
        output / "e-101" / "tests" / "test.sh"
    ).read_text()
    assert "docetl==0.3.0" in (
        output / "e-101" / "tests" / "test.sh"
    ).read_text()
    assert not (output / "e-101" / "environment" / "cartwheel" / ".env").exists()


def test_baseline_export_accepts_only_unclassified_cases(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-102",
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The agent asks what the shopper needs."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    _write_cases(cases_path, [case])
    output = tmp_path / "tasks"

    export_tasks(cases_path, output, baseline=True, case_ids={"e-102"})
    task = tomllib.loads((output / "e-102" / "task.toml").read_text())
    assert task["metadata"]["kind"] == "unclassified"

    with pytest.raises(ValueError, match="kind must be regression or capability"):
        export_tasks(cases_path, output, require_suite=False)


def test_summary_blocks_regressions_but_reports_capabilities(
    tmp_path: Path, monkeypatch
) -> None:
    import tests.eval.passk as passk

    def fake_case_passes(kind: str, passes: int, k: int, baseline_pass_rate=None):
        decision = "block" if kind == "regression" and passes < k else "pass"
        return {"decision": decision, "reason": "test"}

    monkeypatch.setattr(passk, "case_passes", fake_case_passes)
    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: c / n)
    monkeypatch.setattr(passk, "pass_hat_k", lambda n, c, k: c / n)
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply asks a question."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    regression = {**base, "id": "e-201", "kind": "regression"}
    capability = {
        **base,
        "id": "e-202",
        "kind": "capability",
        "baseline_pass_rate": 0.4,
    }
    _write_cases(cases_path, [regression, capability])

    def trial(case_id: str, reward: float) -> dict:
        return {
            "task_name": f"cartwheel/evals__{case_id}",
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": None,
        }

    job = tmp_path / "job"
    job.mkdir()
    trials = [trial("e-201", value) for value in [1, 1, 1, 1, 0]]
    trials += [trial("e-202", value) for value in [0, 0, 1, 0, 1]]
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job, cases_path=cases_path, expected_attempts=5
    )

    assert passed is False
    assert "| `e-201` | regression | 4 | 5 | 0.800" in markdown
    assert "| `e-202` | capability | 2 | 5 | 0.400" in markdown


def test_baseline_summary_reports_the_observed_classification(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {"checks": [{"check": "reply_asks_question"}]},
    }
    first = {**base, "id": "e-301"}
    second = {**base, "id": "e-302"}
    _write_cases(cases_path, [first, second])

    def trial(case_id: str, reward: float, attempt: int) -> dict:
        return {
            "task_name": f"cartwheel/evals__{case_id}",
            "trial_name": f"trial-{attempt}",
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": None,
        }

    job = tmp_path / "job"
    job.mkdir()
    trials = [trial("e-301", 1, i) for i in range(5)]
    trials += [trial("e-302", value, i) for i, value in enumerate([1, 1, 1, 0, 0])]
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job,
        cases_path=cases_path,
        expected_attempts=5,
        classify=True,
    )

    assert passed is True
    assert '`kind: "regression"`' in markdown
    assert '`kind: "capability"`, `baseline_pass_rate: 0.6`' in markdown


def test_baseline_summary_does_not_classify_infrastructure_errors(
    tmp_path: Path,
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-303",
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {"checks": [{"check": "reply_asks_question"}]},
    }
    _write_cases(cases_path, [case])
    job = tmp_path / "job"
    job.mkdir()
    trials = [
        {
            "task_name": "cartwheel/evals__e-303",
            "verifier_result": {"rewards": {"reward": 1}},
            "exception_info": None,
        }
        for _ in range(4)
    ]
    trials.append(
        {
            "task_name": "cartwheel/evals__e-303",
            "verifier_result": None,
            "exception_info": {"message": "sandbox failed"},
        }
    )
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job,
        cases_path=cases_path,
        expected_attempts=5,
        classify=True,
    )

    assert passed is False
    assert "do not classify; complete five valid trials" in markdown


def test_final_export_requires_the_homework_suite(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "first_mode",
        "kind": "regression",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply asks a question."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    cases = [{**base, "id": f"e-{index:03d}"} for index in range(10)]
    _write_cases(cases_path, cases)

    with pytest.raises(ValueError, match="at least two failure modes"):
        export_tasks(cases_path, tmp_path / "tasks")

    cases[-1] = {
        **cases[-1],
        "mode": "second_mode",
        "kind": "capability",
        "baseline_pass_rate": 0.8,
    }
    _write_cases(cases_path, cases)

    tasks = export_tasks(cases_path, tmp_path / "tasks")

    assert len(tasks) == 10


def test_capability_analysis_uses_5_10_and_15_observed_runs(
    tmp_path: Path, monkeypatch
) -> None:
    import tests.eval.passk as passk

    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: (n + c + k) / 100)
    monkeypatch.setattr(
        "harbor_adapter.analysis.pass_at_k",
        lambda n, c, k: (n + c + k) / 100,
    )
    job = tmp_path / "job"
    job.mkdir()
    trials = []
    for attempt in range(14, -1, -1):
        trials.append(
            {
                "task_name": "cartwheel/evals__e-401",
                "trial_name": f"trial-{attempt:02d}",
                "verifier_result": {
                    "rewards": {"reward": 1 if attempt % 2 == 0 else 0}
                },
                "agent_info": {
                    "model_info": {
                        "provider": "student",
                        "name": "provider-model",
                    }
                },
                "exception_info": None,
            }
        )
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    result = analyze_capability_job(job, "e-401")

    assert result["n"] == 15
    assert result["rewards"][:3] == [1, 0, 1]
    assert result["model"] == "student/provider-model"
    assert result["trials"][0]["trial_name"] == "trial-14"
    assert result["trial_order"] == "result.json trial_results order"
    assert [row["n"] for row in result["comparisons"]] == [5, 10, 15]
    assert set(result["comparisons"][-1]["pass_at_k"]) == {
        "1",
        "3",
        "5",
        "10",
        "15",
    }


def _write_trial_dir(
    job: Path, name: str, case_id: str, reward: float, started_at: str
) -> None:
    """One trial as Harbor 0.23.0 lays it out: <job>/<trial>/result.json."""
    (job / name).mkdir(parents=True)
    (job / name / "result.json").write_text(
        json.dumps(
            {
                "task_name": f"cartwheel/evals__{case_id}",
                "trial_name": name,
                "started_at": started_at,
                "verifier_result": {"rewards": {"reward": reward}},
                "agent_info": {"model_info": {"provider": "student", "name": "m"}},
                "exception_info": None,
            }
        )
    )


def test_summary_reads_trials_from_the_per_trial_files(
    tmp_path: Path, monkeypatch
) -> None:
    import tests.eval.passk as passk
    from harbor_adapter.summary import PER_TRIAL_ORDER, load_trial_results

    monkeypatch.setattr(
        passk, "case_passes", lambda kind, passes, k, baseline_pass_rate=None: {"decision": "pass", "reason": "test"}
    )
    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: c / n)
    monkeypatch.setattr(passk, "pass_hat_k", lambda n, c, k: c / n)

    cases_path = tmp_path / "cases.jsonl"
    _write_cases(
        cases_path,
        [
            {
                "id": "e-501",
                "mode": "response_quality",
                "kind": "capability",
                "baseline_pass_rate": 0.4,
                "input": {"role": "shopper", "user_id": 1, "message": "hello"},
                "initial_state": {"world": "reseed", "fixture": None},
                "expected": {
                    "assertions": ["The reply asks a question."],
                    "checks": [{"check": "reply_asks_question"}],
                },
            }
        ],
    )
    job = tmp_path / "job"
    job.mkdir()
    # The job file as Harbor 0.23.0 writes it: statistics only, no trial list.
    (job / "result.json").write_text(json.dumps({"n_total_trials": 5, "stats": {}}))
    for i, reward in enumerate([0, 0, 1, 0, 1]):
        _write_trial_dir(job, f"e-501__t{i}", "e-501", reward, f"2026-10-03T15:00:0{i}")

    trials, order = load_trial_results(job)
    markdown, _ = summarize_job(job, cases_path=cases_path, expected_attempts=5)

    assert len(trials) == 5 and order == PER_TRIAL_ORDER
    assert "| `e-501` | capability | 2 | 5 | 0.400" in markdown


def test_per_trial_files_are_ordered_by_start_time_not_folder_name(
    tmp_path: Path,
) -> None:
    from harbor_adapter.summary import PER_TRIAL_ORDER, load_trial_results

    job = tmp_path / "job"
    job.mkdir()
    (job / "result.json").write_text(json.dumps({"stats": {}, "trial_results": []}))
    # Folder names sort one way, start times the other: the runs happened in
    # the order c, b, a.
    for name, started in [("e-1__a", "2026-10-03T15:00:03"),
                          ("e-1__b", "2026-10-03T15:00:02"),
                          ("e-1__c", "2026-10-03T15:00:01")]:
        _write_trial_dir(job, name, "e-1", 1, started)

    trials, order = load_trial_results(job)

    assert [t["trial_name"] for t in trials] == ["e-1__c", "e-1__b", "e-1__a"]
    assert order == PER_TRIAL_ORDER


def test_analysis_labels_the_order_it_used(tmp_path: Path, monkeypatch) -> None:
    import tests.eval.passk as passk

    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: c / n)
    monkeypatch.setattr("harbor_adapter.analysis.pass_at_k", lambda n, c, k: c / n)
    job = tmp_path / "job"
    job.mkdir()
    (job / "result.json").write_text(json.dumps({"stats": {}}))
    for i in range(5):
        _write_trial_dir(job, f"e-9__t{i}", "e-9", i % 2, f"2026-10-03T15:00:0{i}")

    result = analyze_capability_job(job, "e-9", expected_attempts=5)

    assert result["trial_order"].startswith("per-trial result.json files")
    assert result["rewards"] == [0, 1, 0, 1, 0]


def test_an_embedded_trial_list_still_wins_in_its_stored_order(tmp_path: Path) -> None:
    from harbor_adapter.summary import EMBEDDED_ORDER, load_trial_results

    job = tmp_path / "job"
    job.mkdir()
    embedded = [{"trial_name": "z", "task_name": "x"}, {"trial_name": "a", "task_name": "x"}]
    (job / "result.json").write_text(json.dumps({"trial_results": embedded}))
    _write_trial_dir(job, "e-1__q", "e-1", 1, "2026-10-03T15:00:00")  # must be ignored

    trials, order = load_trial_results(job)

    assert [t["trial_name"] for t in trials] == ["z", "a"] and order == EMBEDDED_ORDER


def test_a_job_with_no_result_file_is_still_an_error(tmp_path: Path) -> None:
    from harbor_adapter.summary import load_trial_results

    with pytest.raises(FileNotFoundError):
        load_trial_results(tmp_path)
