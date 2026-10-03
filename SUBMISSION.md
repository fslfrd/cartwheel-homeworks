# Homework 1 to 5: submission index

This is a fork of the course repository, <https://github.com/ai-evals-course/cartwheel-homeworks>. `main` carries all of the work. Each homework also has a branch that ends at that homework's last commit, so you can see the repository exactly as it stood when I finished it.

`main` also contains merges from the course repository (later homework materials), and this file. The course's own `README.md` is untouched.

| homework | branch | last commit | where the work is |
|---|---|---|---|
| 1, support tools | [`hw1`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw1) | `55005fd` | the five support tools in `agent/tools.py` |
| 2, sessions and tracing | [`hw2`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw2) | `cd4ec32` | the authenticated, traced endpoint in `server/app.py`; `hw2-traces.json` holds the two selected traces |
| 3, scenario dataset | [`hw3`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw3) | `23fc1d4` | `scenarios/` (30 pilot, 250 final, 50 monitoring), `traces/support_traces.json` (417 traces covering 250 scenario ids), `reports/smoke-output.txt` |
| 4, error analysis | [`hw4`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw4) | `d7eb302` | my own review interface in `analysis/review_app/`, state in `analysis/state/`, and `analysis/report/review_summary.md` |
| 5, one LLM judge | [`hw5`](https://github.com/fslfrd/cartwheel-homeworks/tree/hw5) | `7b10f1b` | `analysis/run_judges.py`, `analysis/prompts/`, `analysis/state/judges/`, `analysis/report/` |

The system prompt revision in `agent/agent.py` (covering every escalation trigger in `SPEC.md`) landed after Homework 2, in commit `9674940`, so it appears from `hw3` onward.

## Homework 4 in brief

I reviewed 81 sessions (139 traces) drawn from a 156-session sample, and grouped what I found into 7 failure modes, each with at least three confirmed examples and a requirement it traces to. Three `SPEC.md` requirements were revised or added as a result. The summary, the rejected groupings and the interface comparison are in `analysis/report/`. Part C (the optional workshop) was not done.

## Homework 5 in brief

The judge is for `writes_without_confirming_match`: the agent refunded or cancelled an order it had found by a guess, with nothing from the user establishing it. The definition and its five rulings are in `analysis/report/hw5-failure-definition.md`.

- **Labels:** 89, of which 55 Pass and 34 Fail (1 = Pass), in `analysis/state/hw5_labels/`. Twenty of the sessions came from scenarios I generated (`scenarios/hw5_scenarios.jsonl`) because the existing sessions had too few Fails.
- **Split:** 20/40/40 with seed 7, giving 18 training, 36 development and 35 test.
- **Prompts:** three versions in `analysis/prompts/`, each run on `gpt-4o-mini` and on `gpt-5.5` for development. The 3×2 table is in `analysis/report/dev-comparison.md`.
- **Official judge:** prompt v0 on `gpt-4o-mini` (`writes_without_confirming_match-v0`), frozen and run once on the test split. TPR 0.818 (18 of 22), TNR 0.923 (12 of 13), with 95% Wilson intervals of 0.615 to 0.927 and 0.667 to 0.986. See `analysis/report/test-writes_without_confirming_match-v0.json`.
- **For comparison only:** the same prompt on `gpt-5.5` was run on the test split afterwards (`...-v3.json`). It was not used to choose the official judge.

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

That gives 161 passed, plus 4 skipped, 18 expected failures and 9 unexpected passes, which come from the homework templates.

## Not yet in the repository

- `hw1-session.jsonl` and the Homework 1 write-up (Part C).
- The recorded videos for Homeworks 1 to 5.

API keys are never committed. `.env` is ignored, and `.env.example` holds the course's placeholder settings only.
