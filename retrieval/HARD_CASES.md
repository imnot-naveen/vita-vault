# Evidence hard-case evaluation — 3 November 2026

`tests/evidence_hard_cases.json` adds twelve scenarios to the earlier twelve
development scenarios: eight development cases and four reserved from live
prompt-tuning feedback. Each new case supplies two or three passages. Source
excerpts preserve original source IDs, hashes and character ranges in `origins`;
controlled synthetic reports are explicitly marked and are not real repair
sources. No examples were added to Qdrant.

Expected reviews and decisions were authored before model calls and the fixture
hash was frozen. Labels remain assistant-authored and require user/independent
review. These are selected-passage scenarios, not new retrieval trials. The
reserved cases reuse some source families and were authored by the same person
as the development cases; they are not an independent benchmark or a blind test.

## Coverage

- A successful report on different firmware or for another error code.
- An untested certificate suggestion with matching symptoms/setup.
- An initial fix claim followed by recurrence and explicit withdrawal.
- A valid scoped success or configuration instruction mixed with noisy sources.
- A fixing commit without an installable release number.
- Instructions embedded in a source asking the model to invent a fix.
- Two symptom reports without a repair; a valid narrow explanation despite
  irrelevant firmware information; an older failed patch followed by a distinct
  later successful test; an unrelated platform sharing network terminology.

## Observed result and repair

| Run | Decision agreement | Unexpected supported answers | Missing expected supported answers |
|---|---:|---:|---:|
| Initial v2, 8 development cases | 7/8 | 1 | 0 |
| Revised v3, same 8 development cases | 8/8 | 0 | 0 |
| Frozen v3, 4 reserved cases | 4/4 | 0 | 0 |

The v2 failure promoted a prediction that a certificate change should work into
a report of successful resolution. Its own limitations admitted no confirmation.
The v3 prompt requires an observed outcome and distinguishes failures,
withdrawals and suggestions. The decision layer also sends tentative success
quotes and unflagged withdrawal/recurrence quotes to `review_required`, with no
permitted claim. A replay of the captured false positive verifies rejection.

The quote checks are narrow English-language rules for observed failure modes,
not an entailment classifier. A mixed statement with both tentative and observed
outcome language may need a narrower quote or human review. Other unsupported
claims can still escape these particular patterns; exact quote matching alone
does not prove a claim or correct applicability.

## Disagreements retained

V3 still had 19 field disagreements across the eight development cases and three
across the reserved cases. Some reflect taxonomy ambiguity (guidance versus an
explanation of guidance; direct versus related symptoms). In particular, the
release-number question was incorrectly labeled `confirmed_fix` and the commit
report labeled matching success. Its final insufficient-evidence decision was
conservative, but that does not make those semantic labels correct. Future intent
and answer-coverage checks must not treat this as a fully correct review.

The failure-report conflict flag is relative to the row's proposed claim: a true
claim that a fix failed need not itself be contradicted. The earlier success row
was flagged as contradicted, which correctly blocked lasting-fix permission.
Do not silently rewrite frozen expectations to remove disagreements.

Positive permitted claims were inspected for scope and passage support; the
general storage explanation remains a statement about the cited discussion,
and synthetic success is valid only inside its controlled test. Reason text and
all intermediate labels should not be treated as verified answer prose.

All twenty provider completions across the baseline, rerun and reserved checks
reported cost zero. This is observed usage for those calls, not a future pricing
guarantee. No automatic retries or paid fallback were used.

## Repeat selected development checks

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
& ./.venv/Scripts/python.exe -B tools/evaluate_assessor.py --cases tests/evidence_hard_cases.json --case-id dev-untested-suggestion --case-id dev-retracted-success --case-id dev-supported-amid-noise --report hard-review.json
```

Reports retain input/prompt hashes, final decisions, field disagreements,
unexpected permissions, missing expected answers and validation failures.
Unvalidated completions are retained as local evaluation diagnostics only;
they are not accepted reviews or answer content. Usage/prompt metadata survives
validation failures. Re-running reserved cases does not create fresh validation.

Next: independent label review and fresh full-retrieval questions; refine intent
and answer coverage before exposing generated repair advice. A source-returning
API can expose sources and explicit evidence states without claiming those
future quality checks are complete.
