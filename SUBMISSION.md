# Homework 1 to 6: submission index

This is a fork of the course repository, <https://github.com/ai-evals-course/cartwheel-homeworks>. `main` carries all of the work. Each homework also has a branch that ends at that homework's last commit, so you can see the repository exactly as it stood when I finished it.

`main` also contains merges from the course repository (later homework materials), and this file. The course's own `README.md` is untouched.

| homework | branch | last commit | where the work is |
|---|---|---|---|
| 1, support tools | [`hw1`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw1) | `55005fd` | the five support tools in `agent/tools.py` |
| 2, sessions and tracing | [`hw2`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw2) | `cd4ec32` | the authenticated, traced endpoint in `server/app.py`; `hw2-traces.json` holds the two selected traces |
| 3, scenario dataset | [`hw3`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw3) | `23fc1d4` | `scenarios/` (30 pilot, 250 final, 50 monitoring), `traces/support_traces.json` (417 traces covering 250 scenario ids), `reports/smoke-output.txt` |
| 4, error analysis | [`hw4`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw4) | `d7eb302` | my own review interface in `analysis/review_app/`, state in `analysis/state/`, and `analysis/report/review_summary.md` |
| 5, one LLM judge | [`hw5`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw5) | `7b10f1b` | `analysis/run_judges.py`, `analysis/prompts/`, `analysis/state/judges/`, `analysis/report/` |
| 6, CI evaluation | [`hw6/ci`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw6/ci) (PR [#1](https://github.com/fslfrd/cartwheel-homeworks/pull/1), merged into `main`) | `d0ed8b4` | `eval_cases/cases.jsonl`, `tests/eval/passk.py`, `.github/workflows/evals.yml`, `ci-runs.json`, `eval_results/e-007-15.json` |

The system prompt revision in `agent/agent.py` (covering every escalation trigger in `SPEC.md`) landed after Homework 2, in commit `9674940`, so it appears from `hw3` onward.

## Homework 4 in brief

I reviewed 81 sessions (139 traces) drawn from a 156-session sample, and grouped what I found into 7 failure modes, each with at least three confirmed examples and a requirement it traces to. Three `SPEC.md` requirements were revised or added as a result. The summary, the rejected groupings and the interface comparison are in `analysis/report/`. Part C (the optional workshop) was not done.

## Homework 5 in brief

The judge is for `writes_without_confirming_match`: the agent refunded or cancelled an order it had found by a guess, with nothing from the user establishing it. The definition and its five rulings are in `analysis/report/hw5-failure-definition.md`.

- **Labels:** 89, of which 55 Pass and 34 Fail (1 = Pass), in `analysis/state/hw5_labels/`. Twenty of the sessions came from scenarios I generated (`scenarios/hw5_scenarios.jsonl`) because the existing sessions had too few Fails.
- **Split:** 20/40/40 with seed 7, giving 18 training, 36 development and 35 test.
- **Prompts:** three versions in `analysis/prompts/`, each run on `gpt-4o-mini` and on `gpt-5.5` for development. The 3×2 table is in `analysis/report/dev-comparison.md`.
- **Official judge:** prompt v0 on `gpt-4o-mini` (`writes_without_confirming_match-v0`), frozen and run once on the test split. TPR 0.818 (18 of 22), TNR 0.923 (12 of 13), with 95% Wilson intervals of 0.615 to 0.927 and 0.667 to 0.986. See `analysis/report/test-writes_without_confirming_match-v0.json`.
- **For comparison only:** the same prompt on `gpt-5.5` was run on the test split afterwards (`...-v3.json`). It was not used to choose the official judge, and its status is `evaluated_not_selected` so that tools that load the highest frozen judge for a mode (such as the Homework 6 adapter) use the accepted `-v0`.

To reproduce the steps:

```bash
uv run python -m analysis.run_judges prepare
uv run python -m analysis.run_judges split
uv run python -m analysis.run_judges dev analysis/prompts/writes_without_confirming_match-v0.txt
uv run python -m analysis.run_judges test writes_without_confirming_match-v0
```

To recompute a judge's metrics independently from the saved predictions and labels, without the course helper:

```bash
uv run python -m analysis.recalc_metrics writes_without_confirming_match-v0 test
```

It prints the confusion matrix, TPR, TNR and 95% Wilson intervals, and checks them against the saved report. It refuses the test split for a judge that was never frozen.

The `dev` and `test` steps call a model and need `OPENAI_API_KEY` in `.env`. `split` should be run once; `analysis/state/splits.json` is committed and must not change. Cached predictions are in `analysis/state/judges/`.

## Homework 6 in brief

**Part A, cases.** `eval_cases/cases.jsonl` holds 11 cases: 9 capability and 2 regression. Six of them test `writes_without_confirming_match` (judged by the accepted HW5 judge, `-v0`) and five test `reveals_internal_error_detail`. Each case was run 5 times through Harbor 0.23.0 on `gpt-5.5` to set its baseline: a case that passed 5 of 5 is a regression case (`e-005`, `e-006`), and every other case is a capability case carrying its `baseline_pass_rate` (0.0 for seven of them, 0.4 for `e-007`, 0.2 for `e-011`). Harbor 0.23.0 does not write `trial_results` into a job's `result.json`, so `harbor_adapter/summary.py` reads the per-trial `result.json` files and orders them by `started_at` (tests in `tests/test_harbor_adapter.py`).

**Part B, pass@k.** `tests/eval/passk.py` computes pass@k = 1 − C(n−c, k)/C(n, k) and pass^k = C(c, k)/C(n, k), and the CI decision: a regression case blocks if any of its runs failed, a capability case never blocks. Tests are in `tests/test_passk.py`.

**Part C, workflow.** `.github/workflows/evals.yml` runs the Harbor evaluation on `pull_request` only, with 5 attempts per case, a concurrency group that cancels superseded runs, a job summary, and the job directory uploaded as an artifact. The offline checks run on every push and cost nothing. The provider key is the repository secret `OPENAI_API_KEY`; its value is not in the repository.

**Part D, two runs from one pull request.** [PR #1](https://github.com/fslfrd/cartwheel-homeworks/pull/1) is inside my fork, with the fork's `main` as base, and was merged after the second run. A temporary instruction in `agent/agent.py` (ask for confirmation before any refund) made [run 1](https://github.com/fslfrd/cartwheel-homeworks/actions/runs/37152118698) fail: `e-005` passed 0 of 5 and `e-006` also blocked. Reverting it made [run 2](https://github.com/fslfrd/cartwheel-homeworks/actions/runs/37160050425) succeed, with `e-005` at 5 of 5. Both runs and the explanation are in `ci-runs.json`. The net change to `agent/agent.py` is zero.

**Part E, 15 runs of one capability case.** `e-007` (baseline 0.4) passed 11 of 15 runs on `gpt-5.5`. `eval_results/e-007-15.json` has pass@k at n of 5, 10 and 15:

| runs observed (n) | passes | pass@1 | pass@3 | pass@5 |
|---|---|---|---|---|
| 5 | 3 | 0.600 | 1.000 | 1.000 |
| 10 | 7 | 0.700 | 0.992 | 1.000 |
| 15 | 11 | 0.733 | 0.991 | 1.000 |

pass@10 and pass@15 at n = 15 are both 1.000.

To reproduce Part E (this calls the model and needs the provider key in `.env`, about $0.5):

```bash
uv run python scripts/export_harbor_tasks.py
PYTHONPATH="$PWD" harbor run --env-file .env -p .harbor/tasks --include-task-name "*e-007" \
  -a harbor_adapter.agent:CartwheelAgent -m "$CARTWHEEL_MODEL" -e docker \
  --n-attempts 15 --job-name hw6-capability-15 --jobs-dir .harbor/jobs --yes
uv run python scripts/analyze_harbor_job.py .harbor/jobs/hw6-capability-15 --case e-007 --out eval_results/e-007-15.json
```

Pending: my own reading of these results and the HW6 video. The explanation in `ci-runs.json` is a factual summary I will reword.

## Review interface

```bash
uv run python -m analysis.review_app.server
```

See [`analysis/review_app/README.md`](analysis/review_app/README.md) for what it does, its keys, and the Homework 5 labelling and judge views.

## Tests

```bash
uv run pytest tests/
```

With a populated `.env`, one upstream test in `tests/test_cli.py` leaks the Langfuse settings into the test process, and `test_m2_run_judge_persists_store_predictions_for_prevalence` then fails. Pointing the judge at the committed store avoids it:

```bash
CARTWHEEL_JUDGE_TRACE_SOURCE=analysis/state/store_traces.json uv run pytest tests/
```

That gives 194 passed, plus 14 skipped, 15 expected failures and 12 unexpected passes, which come from the homework templates.

## Not yet in the repository

- `hw1-session.jsonl` and the Homework 1 write-up (Part C).
- The recorded videos for Homeworks 1 to 6.

API keys are never committed. `.env` is ignored, and `.env.example` holds the course's placeholder settings only.
