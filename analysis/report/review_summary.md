# Homework 4, review summary

## The reviewed sample

81 sessions, **139 underlying traces**. Cartwheel writes one Langfuse trace
per user turn, so a session is one conversation and covers one to three
traces. The session is the review unit, because a followup turn read without
its opening turn cannot be judged.

| batch | method | n |
| --- | --- | --- |
| `b0_exploratory` | read in scenario-id order before the batches were drawn | 56 |
| `b1_uniform` | uniform random over unread sessions | 3 |
| `b1_cluster` | k-means representatives on trace features | 5 |
| `b2_intent` | distributed across the intent dimension | 9 |
| `b3_depth` | retrieved by depth search for a named mode | 2 |
| `b4_saturation` | uniform random, drawn after the taxonomy was drafted | 6 |

Composition: 54 shopper, 14 support, 13 merchant. 55 coverage, 26 challenge.
15 of the 19 intents. 70 open codes and 28 sessions marked "no failure
observed", so a reviewed-and-clean session is distinguishable from an unread
one.

`b0_exploratory` is not one of the handout's four batches. It records reading
done in scenario-id order before any sampling was designed, and it is kept
separate rather than folded into a batch it was not drawn for. That early
reading was badly skewed: all 56 sessions are shopper, coverage, and largely
`order_status`, which is why the later batches were drawn by method.

## Failure modes

Seven modes, each with at least three confirmed positive sessions and a
requirement source. Fractions are **sample fractions, not prevalence
estimates**: clustering, dimension spreads and depth searches deliberately
changed what was reviewed. Homework 5 estimates prevalence against the full
store.

| mode | fail | sample fraction | requirement | evaluator |
| --- | --- | --- | --- | --- |
| `narrates_intent_before_acting` | 19 / 81 | 23.5% | RESP-5 (revised) | LLM judge |
| `repeats_identical_lookup` | 9 / 81 | 11.1% | RESP-7 (new) | code check |
| `acts_beyond_request` | 8 / 81 | 9.9% | RESP-7 (new) | LLM judge |
| `writes_without_confirming_match` | 5 / 81 | 6.2% | RESP-6 (new) | code check |
| `reveals_internal_error_detail` | 4 / 81 | 4.9% | RESP-4 | LLM judge |
| `affective_filler_opener` | 3 / 81 | 3.7% | RESP-5 (revised) | LLM judge |
| `applies_rule_without_verifying_record` | 3 / 81 | 3.7% | RESP-3 | LLM judge |

Definitions, boundaries, positive sessions and originating annotation ids are
in `analysis/state/patterns.json`. Every mode records the annotation ids it
was built from, so the path from observation to category is inspectable.

### The first-failure undercount

Open coding records the first failure and stops, which undercounts any mode
that occurs later in a session. Re-running each mode's detector across all 81
reviewed sessions shows the size of that gap for the largest mode:

- `narrates_intent_before_acting`: **19 sessions by first-failure count, 79
  by any-instance count**. Six candidate sessions were sampled at random and
  all six matched the pattern the confirmed notes describe.
- `affective_filler_opener`: 3 by first-failure count, 10 by detector.

The labels record only the 19 and the 3. Every positive in
`analysis/state/labels/` traces to a note written after reading the session
or a suggestion accepted after reading it; no detector wrote a label. That is
a deliberate choice of precision over recall, and it means the reported
fractions are lower bounds. The detector hits are preserved undecided in
`analysis/state/suggestions.json`.

### Groups recorded but not carried as modes

| group | why |
| --- | --- |
| `answers_outside_product_scope` | Real and grounded in SCOPE-2, but a scan of all 250 sessions found one instance, so it cannot reach three positives. |
| `malformed_tool_argument` | Well evidenced (8 calls across 4 sessions, `support-0139` repeating it five times) but no requirement covers it. A tool-contract defect, reported below as an engineering finding. |
| `prefers_reference_over_inline_data` | No Cartwheel tool returns a URL, so the agent cannot do what the observation asks. A product request. |
| `addresses_wrong_party` | One observation, no further instances, no requirement. |
| `acts_on_stale_premise` | One observation, no further instances, no requirement. |
| `checked_and_conformant` | A question raised during review that AUTH-1 answers: cross-store product search is permitted to every role. |

## Taxonomy revision

`reveals_internal_error_detail` was first defined as a reply exposing
**internal error wording** after a failed tool call. Under that definition it
had two positives, and six scope-explaining refusals were classified as close
negatives.

Annotations on `support-0244` and `support-0246` rejected that reading:
naming the caller's account as the reason ("I can't access order 455 from
this account") confirms the record exists and belongs to someone else, which
is the disclosure RESP-4 forbids. Repeating the order number the user
supplied in their own question was explicitly ruled out as a signal, since it
reveals nothing they did not already have.

The definition was widened to cover the scope explanation. **Confirmed
positives went from 2 to 7.** `support-0247` became the reference close
negative: "Since I'm not authorized to view that order for your store"
attributes the limit to the agent rather than locating the record in someone
else's scope.

## Rejected search suggestions

Three rejections are recorded in `analysis/state/suggestions.json`.

The consequential pair is `support-0057` and `support-0059`, both retrieved
for `writes_without_confirming_match`. The scan keyed on the user not having
named the order. In both sessions the user said "please just process the
refund" and "can you do that now please", then repeated the demand across
further turns. Stopping to confirm there would obstruct the user rather than
protect them.

Those rejections changed the mode's boundary and the requirement drafted from
it. **RESP-6 was rewritten** to turn on whether the request leaves the target
uncertain, not on whether the user named the order.

The third rejection, `support-0077` for `affective_filler_opener`, excludes
an opener that carries a fact: a line answering the question is not filler
however warmly it begins.

## Saturation

`b4_saturation` was drawn uniformly at random after the taxonomy was drafted,
and read last. Six of its 15 sessions have been reviewed.

**One previously unseen consequential mode appeared**: `support-0090`, where
the agent answers a Cartwheel account-security question correctly in turn 1
citing `cw-account-security`, then in turn 2 advises on shared-laptop logins
and separate Chrome, Firefox or Safari browser profiles. SCOPE-2 places
general web questions and other companies outside the agent's remit.

A scan of all 250 sessions found only this one instance, and cleared all
eight `out_of_scope_*` scenarios: the agent refuses legal and tax questions
correctly every time. The single new mode is therefore rare rather than a
sign the taxonomy is incomplete, and no further batch was drawn.

## Specification revisions

Three changes to `SPEC.md`, each motivated by annotations recorded during
this review.

- **RESP-5, extended.** Answer first; do not narrate steps about to be taken,
  and do not open with reassurance that carries no information. Motivating
  annotations: `amufvjgn4z437` ("verbosity. user knows what you are searching
  for") and `amullnp8adrz6` ("not helpful", on "Yes — you're not shouting
  into the void").
- **RESP-6, new.** Confirm the target of an irreversible write when the
  request leaves it uncertain. Motivating annotation: `amullbib8aqul` ("did
  we cancel too quickly without getting a confirmation that I found the order
  and it can be cancelled?") on `support-0075`, where a $261 order was
  cancelled on a single fuzzy match while the user was still hedging about
  which store it came from. The boundary comes from the two rejections above.
- **RESP-7, new.** Do only the work the request needs: no lookups on topics
  the user did not raise, and no repeated read whose result cannot have
  changed. Motivating annotations: `amufw4alm9z74` ("user did not ask about
  returns") and `amufvn5xfgz3y` ("this search was already done in the
  beginning").

The revisions describe intended behaviour. The running prompt is unchanged,
still `e9ca815022ce`, so the recorded traces remain valid evidence of what
the agent did.

## Engineering finding

`search_products` was called with a numeric store id where the tool expects a
store name, producing `not_found`, in 8 calls across `support-0115`,
`support-0139`, `support-0201` and `support-0202`. `support-0139` repeats the
identical mistake five times in one session. No requirement covers it, so it
is not a failure mode; it is a defect in either the tool's contract or the
prompt's description of it.

## Where the judgments live

- `analysis/state/labels/<mode>.jsonl` — one row per session per mode, 567
  judgments, each carrying its source (`human` or `assumed_absent`), batch and
  scenario id.
- Langfuse — 973 scores, each judgment written to every member trace of its
  session so no turn of a multi-turn conversation appears unscored.

## Carrying into Homework 5

Homework 5 needs at least 30 Pass and 30 Fail labels per mode. On the
conservative labelling used here, every mode is short on Fail: 19 is the
largest count. Two routes are open, and the choice interacts with the
undercount described above. Either accept the pending detector hits, which
would take `narrates_intent_before_acting` to roughly 79 Fail and
`affective_filler_opener` to 10, or generate scenarios targeting the modes
that stay short.
