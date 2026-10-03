# Development comparison: three prompts on two judge models

Development split only (36 traces: 22 human Pass, 14 human Fail). Pass is the positive class. Intervals are 95% Wilson. The test split was not used.

| prompt (chars) | gpt-4o-mini | gpt-5.5 |
|---|---|---|
| v0 (16,969) | TPR 0.82 [0.61, 0.93]<br>TNR 0.79 [0.52, 0.92]<br>wrong 7 of 36 (FN 4, FP 3) | TPR 1.00 [0.85, 1.00]<br>TNR 0.93 [0.69, 0.99]<br>wrong 1 of 36 (FN 0, FP 1) |
| v1 (31,437) | TPR 0.64 [0.43, 0.80]<br>TNR 0.86 [0.60, 0.96]<br>wrong 10 of 36 (FN 8, FP 2) | TPR 1.00 [0.85, 1.00]<br>TNR 1.00 [0.78, 1.00]<br>wrong 0 of 36 (FN 0, FP 0) |
| v2 (14,753) | TPR 1.00 [0.85, 1.00]<br>TNR 0.43 [0.21, 0.67]<br>wrong 8 of 36 (FN 0, FP 8) | TPR 1.00 [0.85, 1.00]<br>TNR 1.00 [0.78, 1.00]<br>wrong 0 of 36 (FN 0, FP 0) |

Judge ids: `-v0`,`-v1`,`-v2` are prompts v0 to v2 on gpt-4o-mini; `-v3`,`-v4`,`-v5` are prompts v0 to v2 on gpt-5.5. Ids count registrations, not prompt files.

Caveats:
- v0 was written before any development run. v1 and v2 were written after reading v0's development errors, so their development scores are optimistic.
- With 14 Fail cases, a perfect TNR still has a lower bound of 0.78.
- The `Writes:` line check (claimed writes against real tool calls) was clean for gpt-5.5 on v1 and v2 (0 of 36 mismatches); gpt-4o-mini claimed non-existent writes in 9 of 36 on v1 and mismatched 2 of 36 on v2. v0 has no `Writes:` line.
