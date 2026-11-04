# Evidence decisions

`evidence.py` applies supplied reviews to source retrieval JSON. It runs offline
with the Python standard library. It does not assess passage meaning, call an
answer model, or automatically classify a new question.

## Input and output

Pass the result of `Retriever.search` and a review to
`decide_evidence(retrieval_result, review)`. A review has this shape:

```json
{
  "schema_version": 1,
  "question": "The exact retrieved question",
  "requested_support": "explanation",
  "assessments": [
    {
      "point_id": 1,
      "url": "https://example.com/source",
      "passage_sha256": "SHA-256 of the original UTF-8 chunk",
      "relevance": "direct",
      "applicability": "matching",
      "support": "explanation",
      "claim": "The narrow claim supported by this passage",
      "evidence_quote": "An exact excerpt from that passage",
      "contradicted": false,
      "reason": "Why the passage supports this claim for this question",
      "limitations": []
    }
  ]
}
```

`requested_support` is `explanation`, `guidance`, `reported_remedy`, or
`confirmed_fix`. It is a supplied assessment of user intent, not inferred here.
Applicability is relative to the scoped claim; missing user/source details must
not silently become a match. All returned passages must have one review with
matching ID, URL and content hash. Quote matching verifies provenance, not
whether a claim follows from its quote.

Relevance: `direct`, `related`, `irrelevant`.
Applicability: `matching`, `mismatch`, `unknown`, `not_applicable`.
Support: `explanation`, `documented_guidance`, `reported_success`,
`suggestion_without_outcome`, `symptoms_only`, `none`.

Only direct, matching, non-conflicting evidence with the requested support kind
can permit a claim. A positive label requires a scoped claim and an exact quote.
Irrelevant passages must have `none` support, `not_applicable` applicability and
no claim. Related conflicting evidence conservatively prevents a supported
answer. The current contract does not independently confirm fixes: community
success can be described as reported success, but cannot satisfy `confirmed_fix`.

Narrow checks reject reported-success quotes containing tentative outcome
predictions and unflagged withdrawal/recurrence language. Rejected reviews
remain `review_required`; no claim is permitted. These English-language checks
cover observed failure modes and can conservatively reject mixed quotes. They
do not prove semantic entailment or replace an assessor/human review. See
[hard-case results and limitations](HARD_CASES.md).

Decisions:

- `supported_answer`: use only `permitted_claims`, including their evidence kind,
  quote, source and limitations. This does not authorize unrestricted advice.
- `related_reports_insufficient_support`: show scoped related reports without
  asserting the requested answer/fix.
- `no_relevant_evidence_retrieved`: either retrieval returned no candidates or
  all supplied reviews marked returned passages irrelevant. `basis` distinguishes
  these situations; neither is an exhaustive statement about the archive.
- `review_required`: missing, stale, malformed or incomplete reviews. No claims
  are permitted. An assessor failure must follow this path or an explicit service
  failure, rather than being converted into a knowledge/abstention judgment.
- `service_error` / `invalid_input`: preserve the operational distinction.

## Commands

From the repository root:

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_evidence.py -v
& ./.venv/Scripts/python.exe -B tools/decide_evidence.py retrieval-result.json evidence-review.json
```

The CLI reads two saved JSON files and prints a decision. It has no model,
database or network calls. Exit code 0 includes supported/insufficient/no-evidence
decisions; 2 means review/input failure; 1 means a retrieval service error.

`tests/evidence_development.json` contains twelve assistant-reviewed development
scenarios from saved passages. Some questions are derived and were not run
through retrieval; selected-source cases are not judgments about full result
sets. These test enforcement of supplied labels, not automatic semantic
accuracy, relevance calibration or held-out answer quality.

## Model-assisted reviews

The [automatic assessor](ASSESSOR.md) now produces and validates reviews for
saved retrieval results or a live question before applying this decision layer.
It is an explicit separate step; `retrieval.search` still returns unassessed
candidates. Semantic correctness requires evaluation beyond these contract tests.

## Remaining work

Review the assessor's claims against source text, broaden the examples and
reserve fresh questions for evaluation. Assessing user intent, relevance,
applicability, contradictions and support remains a semantic task. Hashes and
schemas cannot replace it. No generated troubleshooting answers or API/frontend
integration are added here.
