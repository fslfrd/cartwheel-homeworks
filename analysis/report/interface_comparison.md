# Interface comparison

The review interface for Homework 4 lives in `analysis/review_app/`. It was
built after reviewing Cartwheel sessions in the standard Langfuse annotation
view and reading the reference interface in `analysis/server.py` and
`analysis/ui/index.html`.

## What the standard Langfuse view made hard

Langfuse renders a trace as a span tree. Every observation is a collapsed row,
and nothing in the tree says which rows matter, so reading one conversation
means expanding rows one at a time and holding the result of each in your head.
Our sessions carry 4 to 27 observations each, so that is a great deal of
clicking for a single judgment.

Two properties of the Cartwheel data make it worse:

- The top-level `sessionId` field is **null** on every trace. The session
  identifier is recorded only in `metadata.attributes["cartwheel.session_id"]`,
  so Langfuse cannot group a conversation. A second-turn trace opens with no
  link back to the turn that caused it.
- `cartwheel.permission_denied` is recorded on the **tool** span, not the root
  span, so an authorization refusal is invisible from the trace list.

## One design retained from the reference interface

**A tool call and the tool result that follows it are rendered as a single
container.** The reference interface does this in `renderTrace`
(`analysis/ui/index.html`), grouping a `tool_call` with its adjacent
`tool_result` into one `.step` element. This is the direct fix for the
complaint above: the arguments and the outcome are read together, so judging a
claim against what the tool actually returned needs no scrolling and no memory.
The review app keeps the behaviour and the rationale, and extends the group to
carry the annotation anchor as well.

The file-backed API is retained for the same reason: `GET` reads a JSON file
and `POST` overwrites it, so every artifact of the review is a plain file that
can be watched, diffed and committed.

## One design changed after inspecting the traces

**Every tool result now carries a permanent one-line digest, and only its raw
JSON collapses.** The reference interface hides any tool result longer than 240
characters behind a `<details>` element. In our data that threshold is met by
nearly every call: `get_order` (176 calls) and `search_help_center` (154 calls)
are the two most frequent tools in the set, and both return payloads well past
it. The effect is that the evidence needed to judge `RESP-1` and `RESP-3` is
one click away by default, which is the same friction as Langfuse in a
different wrapper.

`analysis/review_app/loader.py` therefore computes a digest per tool result,
picking the fields a reviewer actually judges against: order number, status,
refund eligibility and total for `get_order`; the returned policy identifiers
for `search_help_center`; status and amount for `issue_refund`; the ticket for
`escalate_to_human`. A failed call shows its error code as a badge and its
reason as the digest. The raw payload remains available behind `▸ full`.

Three smaller changes followed from the same reading:

- **The session is the review unit.** The store is keyed by
  `cartwheel.session_id`, a whole conversation is one record, and turn seams
  are drawn between turns so a followup is never read in isolation.
- **A sidebar summarises every session** — scenario id, role, turn count,
  opening line, tool ribbon and review status — so a hundred of them can be
  scanned rather than opened. The keyboard drives the loop: `←`/`→` between
  sessions, `↑`/`↓` between steps, `Enter` to annotate, `n` for "no failure
  observed", `f` to flag for re-review.
- **Metadata and the scenario's expected outcome start collapsed**, so the
  reviewer forms an independent read of the conversation before checking it
  against the designed outcome.

## One limitation remaining

**The interface cannot verify a claim against the database.** It shows what the
agent said and what the tools returned, which is enough to judge internal
consistency — a reply asserting more than its tool reported. It is not enough
to judge whether a tool result was itself correct. Confirming that an order was
genuinely refund-eligible, or that a store override really is 14 days, still
means leaving the interface and querying the seed database or reading
`facts.yaml`. The collapsed `expected` panel narrows the gap for the 250
scenarios that have a recorded ground truth, but it is scenario metadata rather
than a live check, and it does not cover behaviour outside the designed
outcome.

A second, smaller limitation: the reviewed-set layout assumes roughly 1220px of
width. Below that the margin notes column crowds the reading column.
