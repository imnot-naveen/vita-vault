import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# LLM via OpenRouter — OpenAI-compatible endpoint, free/open-source model
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_BASE_URL = "https://openrouter.ai/api/v1"
# Free open-source model (rate-limited). OpenRouter's free catalog changes
# over time; swap in any model ID from https://openrouter.ai/models
LLM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

SUBREDDITS = ["vitahacks", "PSVita", "vitahomebrew", "VitaPiracy", "vita"]
# Reference only — the ingestor keeps its own SUBREDDITS list in
# reddit_ingestor/config.py (plus POST_LIMIT / MAX_COMMENTS knobs). Keep both in sync.

GITHUB_REPOS = [
    "TheOfficialFloW/VitaShell",
    "TheOfficialFloW/Adrenaline",
    "blastrock/pkgj",
    "TheOfficialFloW/NoNpDrm",
]

FORUM_SEED_URLS = [
    # fill in with real thread URLs you find by searching.
    # "https://gbatemp.net/threads/example-thread.123456/",
]

WIKI_REPOS = [
    "https://github.com/TheOfficialFloW/VitaShell.wiki.git",
]

COLLECTION_NAME = "vita_docs"
EMBED_MODEL = "BAAI/bge-large-en-v1.5"
VECTOR_SIZE = 1024