# Automatic evidence assessment

`assessor.py` sends the question and returned passages to the configured free
OpenRouter model, requests one structured review tool call, validates it, and
passes the review to `decide_evidence`. The model does not run a tool or generate
a troubleshooting answer; the tool call is an output format for labels.

The program, not the model, supplies the question binding, point IDs, URLs and
passage hashes. Source indices must cover every returned passage once. Positive
support labels require a scoped claim and an exact quote from the corresponding
passage. Extra fields, invented quotes, truncated output, unknown indices and
invalid labels cannot authorize an answer. Titles, metadata, questions and
embedded instructions remain untrusted data in the prompt.

These checks verify structure/provenance. They cannot prove the model's semantic
judgment, quote entailment, completeness, or resistance to source instructions.
Source interpretation and proposed claims still need evaluation and review.
The prompt is versioned; development results must identify the version tested.

## Run

With the project `.venv`, local cached embedding model, Docker and the existing
Qdrant container available:

```powershell
& ./.venv/Scripts/python.exe -B tools/assess_evidence.py --question 'Why do VitaShell and PKGj show different amounts of free space after a download?' --limit 5 --report assessment.json
```

Or assess an already saved retrieval result without loading the embedding model
or calling Qdrant:

```powershell
& ./.venv/Scripts/python.exe -B tools/assess_evidence.py retrieval-result.json --report assessment.json
```

The report preserves retrieval, review, decision, prompt version and the
provider's token/cost counters when available. A supported result contains only
scoped permitted claims. Related reports do not become a confirmed repair.
No answer model, scraping or index writes are included. Optional HTTP/frontend
integration is documented in `../api/README.md` and `../frontend/README.md`.
The existing `retrieval.search` command still returns unassessed
candidates; assessment is an explicit separate command or Python function.

HTTP/service failures return `service_error`; malformed model reviews return
`review_required`. Neither is interpreted as absence of evidence. Empty
retrieval and invalid input skip the provider. Exit codes: 0 for assessed or
no-candidate decisions, 1 for service failure, 2 for invalid/unreviewable input.

## Provider and cost

Uses existing `OPENROUTER_API_KEY` and `LLM_MODEL` from root configuration.
Requests is already in the retrieval environment; no OpenAI SDK installation is
required. Requests are pinned to OpenRouter's HTTPS completion endpoint, reject
redirects, use a bounded response timeout and make no automatic retries.
Only explicit `:free` model IDs are accepted. Provider price ceilings are zero
for prompt, completion and request charges; fallback is disabled. A failed free
request is not replaced with a paid model.

On 3 November 2026 the configured Nemotron free endpoint supported tools and
forced tool choice, but not `response_format`. The tool schema is therefore
validated locally. Availability/rate limits and provider capabilities can change.
The configured free endpoint's published terms say inputs are logged and must
not contain confidential/personal data. Live smoke inputs were anonymous
questions and selected public passages; broader use must fit the chosen
provider's terms and the user's data preferences.

References checked 3 November 2026:

- [Configured model](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b%3Afree)
- [Model endpoints/capabilities](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b%3Afree/endpoints)
- [Tool calling](https://openrouter.ai/docs/guides/features/tool-calling)
- [Provider price caps](https://openrouter.ai/docs/guides/routing/provider-selection#max-price)

## Checks and evaluation

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
& ./.venv/Scripts/python.exe -B tools/evaluate_assessor.py --case-id space-explanation --case-id personal-firmware-mismatch --case-id unrelated-cooking --max-sources 1 --report assessor-smoke.json
```

The evaluator sends only explicitly selected case IDs, at most twelve requests,
and stops on a provider failure. `--max-sources` deliberately limits each input:
that is a selected-passage scenario, not a full retrieval evaluation. Reports
retain decisions, label disagreements, latency, token counts and supplied
expected labels. Inspect claim wording as well as counters.

Initial live v1 checks produced the expected decisions on three selected-passage
development examples, with two label disagreements. One explanation also
generalized the source too broadly. Prompt v2 clarifies historical/scoped claims
and the symptoms-only label. The original result is retained; v1 results must
not be presented as validation of v2 or as held-out accuracy.

## Hard-case continuation

The [hard-case evaluation](HARD_CASES.md) adds twelve multi-passage scenarios,
including conflicts, suggestions, version/error mismatches, source instructions
and positive controls. V2 permitted one unsupported remedy in eight development
cases. V3 clarifies observed outcomes; the decision layer rejects tentative
success quotes and unflagged withdrawal/recurrence quotes for review. The
captured failure has a regression test. These narrow checks do not establish
semantic entailment generally.

The v3 development rerun matched 8/8 expected decisions and a frozen v3 run
matched 4/4 reserved decisions, with field disagreements retained. In particular,
the release-number question still had incorrect intent/support labels despite
its conservative final decision. See the detailed note before interpreting
the counters as quality evidence. The schema is unchanged; prompt version is
`vita-evidence-v3` for those historical runs.

## 6 November continuation

Four fresh full-retrieval paraphrases exercised an explanation, an exact release
request, a confirmed GPU-fix request and an unrelated question. V3 reached the
expected broad decisions but generalized the community storage explanation.
V4 reinforces attribution in the claim itself and missing exact-version limits.
Rechecking the same saved inputs kept all four routes and produced a claim
scoped to the specific discussion. The exact-release question still received
the wrong `confirmed_fix` intent label, even though it was conservatively
withheld. V4 does not establish corrected intent classification. These are
reused development inputs, not a
held-out benchmark. Intermediate labels/limitations still need human review;
schema/provenance checks cannot establish their semantic correctness.

The UI now opts into `/assess` explicitly. It shows supported scoped claims and
quotes rather than calling another model to write a troubleshooting answer.
Independent label review, broader retrieval/intent coverage, citation reachability
and complete v1 quality acceptance remain open. Current prompt is
`vita-evidence-v4`; historical v3 results above are not evidence for v4.
