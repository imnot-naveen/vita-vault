# Vita Vault Source API

A local HTTP interface over the existing read-only retriever. It returns full
source passages and provenance with an explicit unassessed state. It embeds
questions locally and queries the configured Qdrant collection; no OpenRouter
assessment or answer-generation call is made by `/search`. The separate
`/assess` endpoint explicitly opts into model-assisted evidence review below.

## Install and run

From the repository root, using the existing Python 3.12 `.venv`:

```powershell
& ./.venv/Scripts/python.exe -m pip install -r requirements-api.txt
& ./.venv/Scripts/python.exe -m pip check
& ./.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Docker and the existing `qdrant` container must be available for search. The BGE
embedding weights must already be cached: the existing retriever loads them
offline and reports service failure if unavailable. The first search loads the
model; later requests reuse the app-owned retriever/model. Search access is
serialized within one server process. The default command starts one worker.

Open the [Vita Vault UI](http://127.0.0.1:8000/) or [interactive API documentation](http://127.0.0.1:8000/docs) or
[OpenAPI JSON](http://127.0.0.1:8000/openapi.json) while the server is running.

## POST /search

```json
{
  "question": "Why do VitaShell and PKGj show different amounts of free space?",
  "limit": 3
}
```

- `question`: required string, trimmed, 1–8,000 non-whitespace characters.
- `limit`: optional integer from 1–20, default 5. Boolean, fractional and string
  values are rejected. Unknown fields are rejected.

PowerShell example:

```powershell
$searchBody = @{ question = 'PS Vita GPU driver crash during native games'; limit = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/search' -ContentType 'application/json' -Body $searchBody
```

The 200 response preserves the CLI retrieval contract, including:

- `status`: `candidates_require_review` or `no_candidates`.
- `question`, collection/model/query settings, identifier matches and ranking.
- `evidence_assessment`: always `not_assessed` for this endpoint.
- `sources`: point ID, original similarity score, matched identifiers and the
  full original payload (`chunk`, URL, title and any additional provenance or
  hardware/firmware fields).
- `fetched_points`, skipped-source counts and the similarity notice.

`no_candidates` means no eligible passage remained in this bounded retrieval
result; it is not an assessment that the whole archive lacks relevant evidence.
Returned source URLs retain existing syntax checks; remote availability is not
verified. Scores and matching metadata do not establish a fix or diagnosis.

## HTTP states

| HTTP | Body status | Meaning |
|---|---|---|
| 200 | `candidates_require_review` | Source-bearing neighbors returned, unassessed |
| 200 | `no_candidates` | No eligible candidates remained |
| 422 | `invalid_input` | Invalid/malformed request body |
| 400 | `invalid_input` | Search layer rejected options |
| 503 | `service_error` | Retrieval or output-contract validation unavailable |

Errors contain a stable message, not backend exception strings, credentials,
paths or the invalid request body. A backend error is not converted into an
empty successful search or an insufficient-evidence judgment.

## GET /health

Returns `{"status":"ok","service":"vita-vault","check":"process_liveness"}`.
This checks the running HTTP process only; it does not assert Qdrant/model
readiness. A search can return 503 while this liveness endpoint returns 200.

## Verification and scope

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
```

The nine API checks use FastAPI's HTTP test client, real Qdrant in-memory
retrieval and a fixed encoder. They cover payload preservation, strict request
validation, empty results, malformed JSON, redacted failures, invalid response
contracts, liveness/schema and retriever reuse/cleanup. They need no model
download, live Qdrant service or provider call.

`requirements-api.txt` pins the HTTP additions over the existing Windows
retrieval snapshot. Installation/dependency checks passed in the current
environment; a full fresh reinstall on another platform is not established.

This completes the source-returning API layer. The separate assessment CLI and
[evidence-quality limitations](../retrieval/HARD_CASES.md) remain in place.
The browser UI serves from the same origin at `/`; see `frontend/README.md`.
Free-form generated troubleshooting answers remain later work.

## POST /assess — experimental evidence review

Accepts the same strict question/limit body as `/search`. Retrieves passages on
the server, then sends the question and passages to the existing configured
OpenRouter `:free` model through `retrieval.assessor`. This may include console
details entered in the question. The browser offers an unchecked opt-in and a
data-sharing notice; `/search` remains entirely local and never calls this model.
Use anonymous questions. Run this development server on loopback only; no
authentication, public hosting, or production traffic controls are provided.

The response contains `retrieval`, `status`, `decision`, and `model_called`.
The original retrieval remains `not_assessed`; the separate decision describes
the review of its exact question and passages. No browser-supplied source list
or review is accepted. Accepted model reviews are bound to server-owned source
IDs, URLs and passage hashes; scoped permitted claims include exact quotes and
limitations. Raw provider completions, credentials and intermediate reviews are
not exposed. No extra answer-generation model call is made.

| HTTP | Review state | Meaning |
|---|---|---|
| 200 | `assessed` | Decision is supported information, related reports with insufficient support, or no relevant evidence in the returned passages |
| 200 | `no_relevant_evidence_retrieved` | No eligible candidates; provider skipped |
| 200 | `review_required` | Review failed validation; original sources retained, no claims authorized |
| 503 | `service_error` | Provider/configuration failure; original sources retained when retrieval succeeded |
| 503 | top-level error | Retrieval unavailable or another review already running |
| 400/422 | `invalid_input` | Same strict input rules as source search |

Only one evidence review runs at a time in each server process. Further review
requests fail promptly; local source searches remain available. A browser abort
does not cancel the backend request. There are no retries, paid fallback or
index writes. Provider price ceilings remain zero. Empty input/results skip
the provider. Review or service failure never becomes an insufficient-evidence
verdict. A schema-valid review can still misinterpret a source: this is an
experimental aid, not independent verification of a repair.

Seven additional offline HTTP tests cover the positive quote/provenance path,
distinct evidence states, malformed reviews, redacted errors, provider skips,
busy review capacity and retrieval failure. The full suite has 52 tests.

Implementation references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[lifespan tests](https://fastapi.tiangolo.com/advanced/testing-events/),
[validation-error handlers](https://fastapi.tiangolo.com/tutorial/handling-errors/).
