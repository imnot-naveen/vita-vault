import json
import re
import glob
import os
from datetime import datetime, timezone

RAW_DIR = "data/raw"
OUT_PATH = "data/clean/all_docs.jsonl"

def strip_boilerplate(text):
    if not text:
        return ""
    # Remove quoted reply blocks (lines starting with >)
    text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)
    # Remove markdown links keeping the label: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def load_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

def load_json_array(path):
    # reddit_ingestor writes a JSON array, not JSONL
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def clean_reddit(records):
    out = []
    for r in records:
        # Schema from reddit_ingestor's reddit_dump.json:
        #   post_id, subreddit, title, selftext, score, author,
        #   created_utc (epoch float), url, flair, comments: [{comment_id,
        #   post_id, author, body, score, created_utc}, ...]
        selftext = r.get("selftext", r.get("body", ""))
        comments = "\n\n".join(
            c.get("body", "") for c in r.get("comments", []) if c.get("body")
        )
        full = f"{r['title']}\n\n{selftext}\n\n{comments}"
        full = strip_boilerplate(full)
        if len(full.split()) < 20:
            continue
        created_utc = r.get("created_utc")
        date = (
            datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
            if created_utc else None
        )
        out.append({
            "id": r.get("post_id", r.get("id")), "source": "reddit",
            "title": r["title"], "url": r["url"], "date": date, "body": full,
        })
    return out

def clean_github(records):
    out = []
    for r in records:
        comments = "\n\n".join(r.get("comments", []) or [])
        full = f"{r['title']}\n\n{r.get('body','')}\n\n{comments}"
        full = strip_boilerplate(full)
        if len(full.split()) < 20:
            continue
        out.append({
            "id": r["id"], "source": "github", "title": r["title"],
            "url": r["url"], "date": r.get("date"), "body": full,
        })
    return out

def clean_forum(records):
    out = []
    for r in records:
        full = strip_boilerplate(f"{r['title']}\n\n{r.get('body','')}")
        if len(full.split()) < 20:
            continue
        out.append({
            "id": r["id"], "source": "forum", "title": r["title"],
            "url": r["url"], "date": None, "body": full,
        })
    return out

def clean_wikis():
    out = []
    for path in glob.glob("data/raw/wikis/*/*.md"):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        text = strip_boilerplate(text)
        if len(text.split()) < 20:
            continue
        name = os.path.basename(path).replace(".md", "")
        out.append({
            "id": f"wiki_{name}_{abs(hash(path))}", "source": "wiki",
            "title": name, "url": path, "date": None, "body": text,
        })
    return out

def dedupe(docs):
    seen = set()
    result = []
    for d in docs:
        key = d["url"]
        if key in seen:
            continue
        seen.add(key)
        result.append(d)
    return result

def run():
    reddit = clean_reddit(load_json_array("yars-preview/reddit_ingestor/output/reddit_dump.json"))
    github = clean_github(load_jsonl(f"{RAW_DIR}/github_issues.jsonl"))
    forum = clean_forum(load_jsonl(f"{RAW_DIR}/forum_posts.jsonl"))
    wikis = clean_wikis()

    all_docs = dedupe(reddit + github + forum + wikis)
    os.makedirs("data/clean", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for d in all_docs:
            f.write(json.dumps(d) + "\n")

    print(f"reddit={len(reddit)} github={len(github)} forum={len(forum)} wiki={len(wikis)}")
    print(f"Total after dedupe: {len(all_docs)} -> {OUT_PATH}")

if __name__ == "__main__":
    run()