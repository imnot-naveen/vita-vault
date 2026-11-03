# Source retrieval

From the repository root in PowerShell, with Docker Desktop and the existing Qdrant container running:

```powershell
& ./.venv/Scripts/python.exe -B -m retrieval.search 'PS Vita GPU driver crash during native games' --limit 3
```

The command embeds the question locally with the cached `BAAI/bge-large-en-v1.5` model and searches the existing `vita_docs` collection. It uses BAAI's query instruction, normalized vectors and cosine similarity. Document embeddings remain unchanged. Missing cached model files cause a service error rather than a download. Long questions are subject to the model's input-length limit; this version does not split them.

JSON output includes the question, model/settings and source candidates. Each candidate retains its Qdrant point ID, similarity score and full original payload, including the passage (`chunk`), URL and any available source/model/firmware metadata. It requests up to four times the selected limit, discards missing passages and invalid/local source URLs, and keeps one passage per exact source URL. The default limit is 5, with an allowed range of 1–20. Bounded overfetch can return fewer eligible sources than requested.

Within that bounded pool, passages mentioning explicitly requested error codes or firmware are ranked before other neighbors, then sorted by cosine score. Output records `query_identifiers` and each passage's `matching_query_identifiers`; `score` remains the original cosine similarity. A matching mention does not establish applicability: a passage may discuss several versions or quote someone else's problem. There are no hard hardware/firmware filters.

URL checking validates plausible public HTTP(S) syntax; it does not fetch the remote page or confirm availability. Existing local wiki paths are excluded until their public provenance is repaired. Model and firmware fields are retained as context.

## States and limitations

- `candidates_require_review`: source-bearing neighbors were returned. They have not been assessed for relevance or support for a fix.
- `no_candidates`: no eligible passages remained in the bounded result set after filtering and any requested score cutoff. This does not establish that the whole archive lacks relevant evidence.
- `invalid_input`: blank question or invalid search option, with exit code 2.
- `service_error`: unavailable model/database or incompatible vector configuration, with exit code 1. Run `tools/check_setup.py` to diagnose readiness.

Successful search calls, including `no_candidates`, exit 0. Scores are similarity rankings, not confidence or proof that a reported fix applies. `evidence_assessment` remains `not_assessed`; the command does not generate troubleshooting answers or assert an exact diagnosis.

An optional `--min-score` passes a cosine cutoff to Qdrant. There is no default cutoff because relevance/abstention has not been calibrated. Choosing a cutoff is not a substitute for assessing source support. In particular, an unrelated question can still return neighbors. Automatic relevance rejection and grounded answer/no-answer generation remain separate work.

## Verification

Run deterministic contract checks with Qdrant's in-memory engine and a fixed test encoder:

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_retrieval.py -v
```

Run six fixed questions against the live existing index, saving full passages for manual review:

```powershell
& ./.venv/Scripts/python.exe -B tools/evaluate_retrieval.py --report retrieval-review.json
```

The fixture includes four known-source lookups, Naveen's detailed GPU-crash question and an unrelated cooking question. One lookup is close to an indexed title. Expected source hits at five are smoke checks on development examples, not a held-out quality estimate or a check that a remedy is supported. The runner exits nonzero when an expected known source is missing; the personal/negative cases require manual review regardless of the exit code.

Keep generated review reports out of commits if they contain private questions. No collection creation, scraping, index rebuild or answer-model calls are performed by the search/evaluation commands.

References: [BAAI model card and query instructions](https://huggingface.co/BAAI/bge-large-en-v1.5), [Qdrant query-points API](https://api.qdrant.tech/api-reference/search/query-points/).

## Evidence decisions from supplied reviews

The separate [evidence decision layer](EVIDENCE.md) binds supplied relevance,
applicability and claim-support reviews to the exact retrieved question and
passages. It distinguishes scoped supported claims, related reports with
insufficient support, no relevant evidence retrieved and review/service errors.
The separate [model-assisted assessor](ASSESSOR.md) can now infer and validate
these labels for new passages. Its semantic accuracy still requires evaluation;
answer generation remains unimplemented. Existing search output stays unassessed
until a supplied or model-assisted review is applied.

Run the offline evidence contract tests:

```powershell
& ./.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_evidence.py -v
```
