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
persisted by the UI, and it makes no assessor or answer-generation calls.
External fonts and the credited Wikimedia console image need internet access;
system fonts and the rest of the interface remain usable without them.

Results show original passages, links and available provenance. Identifier
mentions are not exact setup matches. All candidates remain not assessed; the
UI cannot claim relevance, sufficient evidence, a verified fix or a diagnosis.
Empty retrieval and service failures have separate states. Input changes clear
old results and abort the browser request, although backend processing may
finish. Requests time out after 90 seconds. No result is stored across reloads.

The existing separate assessor remains future integration work. The full v1
insufficient-evidence/answer behavior is not implemented by this source UI.

Design: preserve the 30 October prototype’s original PCH-1000 hardware,
blue/cyan LiveArea, glossy bubbles, scroll motion and reduced-motion support.
Image: Evan-Amos, public domain, Wikimedia Commons; credit link is in the footer.
