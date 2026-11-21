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
and complete v1 quality acceptance remain open. This run used `vita-evidence-v4`.

## 21 November release regression retest

The retest used the source tree merged in `55f2f5c`, prompt `vita-evidence-v18`,
the existing 1,037-point `vita_docs` collection, and the configured free
Nemotron reviewer. All 64 offline tests passed. All eight live regressions
matched their expected decision, each expected source ranked first, and the
provider reported zero cost for all eight requests.

To repeat the checks, start the [local API](../api/README.md), then send each
question as `{"question": "…", "limit": 5}` to `/search` and `/assess`.
Check that both routes return the same source points and that the expected source
appears in the results. A cited result should return `supported_answer` and a
claim backed by a quote from the expected source. A withheld result should return
`related_reports_insufficient_support` with zero permitted claims.

| Question | Expected result | Expected source |
| --- | --- | --- |
| Which VitaShell release was reuploaded with old libftpvita and then confirmed to work with WinSCP after the 0.9 FTP connection failure? | Cited VitaShell 0.9 reupload | [VitaShell #34](https://github.com/TheOfficialFloW/VitaShell/issues/34) |
| VitaShell 1.71 asked for an SD card when mounting PSVSD as a USB device. Which installable release did the reporter confirm worked? | Cited VitaShell 1.72 confirmation | [VitaShell #275](https://github.com/TheOfficialFloW/VitaShell/issues/275) |
| Which released version of PKGj does the issue document as fixing the failed to rename error 0x80010016 when downloading a non-Vita game? | Cited PKGj 0.57 fix for that error | [PKGj #414](https://github.com/blastrock/pkgj/issues/414) |
| Which already released PKGj version does the issue confirm fixed 'failed to seek for resume' after an interrupted download? | Withheld. The release was planned. | [PKGj #129](https://github.com/blastrock/pkgj/issues/129) |
| Which released VitaShell version did the report confirm fixed intermittent GPU crashes while opening files, including reports of crashes on 1.9? | Withheld. The version was suggested. | [VitaShell #397](https://github.com/TheOfficialFloW/VitaShell/issues/397) |
| VitaShell 1.5 froze before the unsafe prompt when installing a new VPK. Which installable VitaShell release does the issue confirm fixed this specific freeze? | Withheld. The release mention concerns a different symptom. | [VitaShell #181](https://github.com/TheOfficialFloW/VitaShell/issues/181) |
| Did the original PKGj v0.52 rest-mode download reporter say updating iTLS-Enso made their paused background downloads resume? | Withheld. The reporter described spontaneous recovery. | [PKGj #317](https://github.com/blastrock/pkgj/issues/317) |
| VitaShell 1.97 on firmware 3.63 crashed opening the triangle menu to refresh LiveArea after a NoNpDrm install. Did the reporter say switching to firmware 3.65 helped? | Cited the reporter's firmware 3.65 outcome | [VitaShell #502](https://github.com/TheOfficialFloW/VitaShell/issues/502) |

The retest reused the 20 November regression questions. The results measure
repeatability on those cases. Independent held-back evaluation remains part of
the v1 release checks.
