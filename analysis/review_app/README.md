# Review interface

A single-page trace review tool built for Homework 4 and extended for Homework 5. It reads agent traces, shows each user session as a readable conversation, and saves annotations, failure-mode labels and Homework 5 judgments to files under `analysis/state/`.

## Run it

From the repository root, after `uv sync`:

```bash
uv run python -m analysis.review_app.server
```

Open <http://127.0.0.1:8020/>. This reads the committed export `traces/support_traces.json` (250 sessions), so it needs no Langfuse and no API key. Use `--port 8021` for another port.

To read the live Langfuse project instead, start Langfuse, put the `LANGFUSE_*` variables in `.env`, and run:

```bash
uv run python -m analysis.review_app.server --source langfuse
```

That adds the 20 Homework 5 scenario sessions, which exist only in Langfuse, for 270 sessions in all. Credentials are read from `.env` by variable name and are never printed or served.

## What it shows

- **One session is one conversation.** Cartwheel writes one trace per user turn, so a session is one to three traces. A follow-up turn cannot be judged without its opening turn, so the session is the review unit.
- **The conversation reads as text.** Each user message, tool call with its result, and reply appears in order. Metadata and the scenario's expected block are collapsed.
- **A sidebar lists sessions** with batch, status and role filters, a one-line digest of each, and the tool sequence.
- **Timing.** Each step shows its own duration, each turn separator shows that turn, and the header shows the session total. Timing comes from either the raw export or the Langfuse fetch, and a trace with no timing shows none.
- **Three tabs:** `read`, `taxonomy` (failure modes with definitions and examples) and `progress` (reviewed and unreviewed counts).

### Keys

| key | action |
|---|---|
| `←` `→` | previous or next session |
| `↑` `↓` | move between steps |
| `Enter` | annotate the focused step |
| `n` | mark "no failure observed" |
| `f` | flag for re-review |
| `p` `x` | Homework 5: label Pass or Fail |
| `Esc` | close the note box |

Select text in a message and a note box opens anchored to that text. Keys are ignored while an input has focus.

## Homework 4: annotations and labels

Annotations, suggestions and failure-mode patterns are stored in `annotations.json`, `suggestions.json` and `patterns.json`. A per-mode label file is written to `analysis/state/labels/<mode>.jsonl` (HW4 convention: 1 means the failure is present). When Langfuse is configured, each label is also written as a score to every trace of its session.

## Homework 5: labelling and judge view

Pick one of the `HW5` options in the dropdown. The queue holds the sessions where the user asked for a refund or cancellation, in three tiers: wrote after a fuzzy lookup, wrote with an order number given, and no write.

- **Label.** `p` saves Pass and `x` saves Fail. Type evidence first, then press Enter, then `p` or `x`: the note saves with the label. Labels go to `analysis/state/hw5_labels/<mode>.jsonl` with **1 = Pass and 0 = Fail**, the reverse of Homework 4. Relabelling marks the earlier row `superseded_by` and keeps it.
- **Judge view.** `HW5 dev: judge disagrees with me` shows the judge's verdict and critique beside your label for the **development split only**. Test predictions are never served by this view.
- **Which judge.** The view shows the most recently registered judge. Append `?id=<judge_id>` to `/api/hw5/judge` to read another one.

## State files

| path | contents |
|---|---|
| `analysis/state/sample_manifest.json` | the sampled sessions and their review batches |
| `analysis/state/annotations.json`, `suggestions.json`, `patterns.json` | open codes, search suggestions, failure-mode groups |
| `analysis/state/labels/` | Homework 4 labels, one file per mode |
| `analysis/state/hw5_labels/` | Homework 5 labels with evidence |
| `analysis/state/splits.json`, `hw5_trace_inputs.json` | the split and the exact inputs the judge reads |
| `analysis/state/judges/` | judge versions with predictions and critiques |

## Notes

- Agent replies are model output and untrusted. Everything is built with DOM nodes and `textContent`, never `innerHTML`.
- Offline, the HW5 queue holds 69 of the 89 labelled sessions, because the other 20 are in Langfuse only.
- Tests: `tests/test_review_loader_timing.py`, `tests/test_hw5_judge_view.py` and `tests/test_run_judges_inputs.py`.
