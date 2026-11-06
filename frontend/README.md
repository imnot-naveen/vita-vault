# Vita Vault local UI

The original Vita/LiveArea motion prototype is now connected to the local
source-returning API. No frontend build or Node dependencies are needed.

From the repository root:

```powershell
& ./.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ and select Start debugging. Search requires the
existing Qdrant service and cached embedding model described in `api/README.md`.
The API serves only this public folder, after its API routes; source search is
same-origin and requires no permissive CORS configuration. Do not run the UI
with a standalone static server: `/search` would be unavailable.

Questions, optional model/firmware, and previous tests are joined into one
retrieval query. These are context, not strict database filters. Nothing is
persisted by the UI. Source-only search makes no assessor or answer-generation
calls. Optional experimental evidence review uses `/assess` as described below.
External fonts and the credited Wikimedia console image need internet access;
system fonts and the rest of the interface remain usable without them.

Results show original passages, links and available provenance. Identifier
mentions are not exact setup matches. In source-only mode all candidates remain
not assessed; source search cannot claim relevance, sufficient evidence, a
verified fix or a diagnosis.
Empty retrieval and service failures have separate states. Input changes clear
old results and abort the browser request, although backend processing may
finish. Requests time out after 90 seconds. No result is stored across reloads.

## Optional evidence review

Check **Review source evidence with AI** before submitting to retrieve sources
and review them with the configured free OpenRouter model. This option is off
by default. Its notice identifies the question, console details and passages
sent to the provider. Source-only search remains local.

The review panel distinguishes source-supported information with exact quotes,
related reports with insufficient support, no relevant evidence in the returned
passages, failed validation and service failure. Source cards retain original
passages and label the model's relevance/applicability judgments explicitly.
Provider failure retains readable sources and does not claim evidence is absent.
Supported claims remain attributed/scoped and preserve limitations. All model
and source text is rendered literally, without HTML interpretation.

Input/mode/opt-in changes clear results and abort the browser request. Evidence
review has a 150-second browser timeout; source-only search retains 90 seconds.
Backend requests may finish after cancellation and occupy the review slot until
then. No questions/results persist across reloads. Free-form answer generation
is not implemented; the review is experimental and needs broader evaluation
before full v1 quality acceptance.

Design: preserve the 30 October prototype’s original PCH-1000 hardware,
blue/cyan LiveArea, glossy bubbles, scroll motion and reduced-motion support.
Image: Evan-Amos, public domain, Wikimedia Commons; credit link is in the footer.
