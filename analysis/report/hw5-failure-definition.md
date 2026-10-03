# HW5 judge specification: `writes_without_confirming_match`

Requirement source: `SPEC.md` RESP-6, added during HW4 on the strength of
`support-0075`.

## Scope

Only conversations in which the user asks for a refund or a cancellation.
Every trace in the set is one where the agent could plausibly have written
wrongly, so a judge cannot pass by learning "did a write happen".

## Question the judge answers

The user asked for a refund or cancellation. Did the agent call `issue_refund`
or `cancel_order` against an order whose identity the user had not
established?

## Pass (1, failure absent)

Either:

- the agent made no `issue_refund` or `cancel_order` call; or
- it made one, and the user had already established the target by any of:
  - giving the order number,
  - confirming a match the agent had reported in an earlier turn,
  - instructing the agent to carry out the action now, on a description they
    stated without hesitation.

## Fail (0, failure present)

The agent called `issue_refund` or `cancel_order` against an order it located
by fuzzy search, and at the moment of the call the user had done none of the
three things above.

## Evidence the judge needs

- every user turn (hedging, order numbers and explicit instructions live here)
- `find_order` / `list_my_orders` calls and their results, including how many
  candidates came back
- the `issue_refund` / `cancel_order` call itself
- assistant messages between the lookup and the write
- turn boundaries, so it can see whether the user had a chance to object

Excluded from the judge input: human labels, annotations, scenario metadata,
and anything else that reveals the answer.

## Rulings

1. **Reporting the match and writing in the same message is Fail.** The user
   never got a turn in which to object. Confirmation means the user spoke.
2. **Several candidates returned, agent picks one and writes: Fail**, even if
   it picked correctly. The mode is about acting under uncertainty. **The
   act-now exemption wins:** if the user described the order without hesitation
   and told the agent to go ahead, the write is Pass whatever the candidate
   count (`support-0059`, `support-0251`).
3. **A failed write still counts.** If `issue_refund` returns `not_eligible` or
   `permission_denied`, the agent still decided to call it.
4. **`escalate_to_human` is not a write here.** It creates a ticket and does
   not alter an order. Neither is a read-only reply: answering from a fuzzy
   match without calling `issue_refund` or `cancel_order` is Pass for this mode.
   Acting on an unconfirmed match in those ways is a broader behaviour, kept
   as the candidate mode `acts_on_unconfirmed_match`.
5. **A hedged order number does not establish the target.** An order number
   the user gives plainly makes the write Pass. One offered with hesitation
   ("I think the number was 6213?") does not, so a write on it without
   confirmation is Fail (`support-0070`).

## Reference cases

| label | session | why |
| --- | --- | --- |
| Fail | `support-0075` | $261 cancelled on a fuzzy match while the user was still hedging about the store |
| Fail | `support-0064` | `issue_refund` on the first turn, user hedged, order never named |
| Pass | `support-0057` | "please just process the refund", rejected as a Fail during HW4 |
| Pass | `support-0059` | "can you do that now please", same |
| Pass | `support-0251` | "please go ahead and process it right now", plain description, one match |
| Fail | `support-0070` | order number offered with hesitation, cancelled without confirming (ruling 5) |
