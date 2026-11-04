# Vita Vault local retrieval setup

Windows / Python 3.12.3. Setup checked on 2 November 2026.

## Run the setup check

From the repository root in PowerShell:

```powershell
Set-Location 'C:/Users/Naveen/Documents/GitHub/vita-vault'
docker start qdrant
& ./.venv/Scripts/python.exe -B tools/check_setup.py
```

Start Docker Desktop first if the Docker engine is unavailable. The existing `qdrant` container mounts this repository's `qdrant_storage` and exposes ports 6333/6334. It was observed running Qdrant 1.19.0. Do not create a second container over the same storage.

The check loads the configured embedding model from the local cache on CPU with network downloads disabled, encodes one short input, reads Qdrant collection metadata, and compares one stored vector against a fresh embedding of its payload text. It does not create a collection, upload points or generate an answer. It exits nonzero if the readiness checks fail. A successful sample comparison does not establish retrieval quality across the archive.

To save the JSON result, pass `--report PATH` pointing to a writable location. The script uses the repository root above its `tools` directory by default; `--repo PATH` can override that.

## Recreate the Python environment

The old `venv` folder points to an unavailable Python 3.10 installation. Use `.venv` instead. The version snapshot covers the retrieval/indexing dependencies and the default ingestion CLI, rather than the complete future web application or optional scraper backends.

For a checkout without `.venv`:

```powershell
& C:/Python312/python.exe -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r requirements-retrieval.lock.txt
& ./.venv/Scripts/python.exe -m pip check
```

`requirements-retrieval.lock.txt` is a pip freeze snapshot from this Windows Python 3.12 environment, without artifact hashes. It has not been validated on Linux or as a full clean reinstall. Package installation requires network access for wheels not already cached. Model weights are separate: the current local Hugging Face cache contains `BAAI/bge-large-en-v1.5`, revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`. The readiness check intentionally fails if required model files are absent rather than downloading them.

## Working directories

Use `yars-preview/reddit_ingestor` as the authoritative existing ingestion package. The root `reddit_ingestor` copy lacks required processor/storage modules.

Verify the ingestion CLI without scraping:

```powershell
Push-Location yars-preview
& ../.venv/Scripts/python.exe -B -m reddit_ingestor.main --help
Pop-Location
```

Run downstream cleaning/chunking/indexing scripts from the repository root because they use relative data paths. Running the index builder writes to Qdrant; it is not part of the readiness check.

## Configuration and next work

The root `config.py` loads local `.env` values. Keep secrets out of committed files. Current defaults name the `vita_docs` collection, cosine similarity, 1,024 vector dimensions and `BAAI/bge-large-en-v1.5`. Query and document embedding settings must remain compatible.

The [retrieval command](retrieval/README.md) searches the existing index and returns source candidates with full passages and URLs. The [source-returning HTTP API](api/README.md) now exposes the same unassessed retrieval contract. Install its pinned HTTP additions with `pip install -r requirements-api.txt`, then run `python -m uvicorn api.main:app --host 127.0.0.1 --port 8000` using the project `.venv`. Evidence assessment remains a separate explicit step, and generated answers/frontend integration remain pending.

API references: [SentenceTransformer model loading and encoding](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html), [official Qdrant Python client](https://github.com/qdrant/qdrant-client).
