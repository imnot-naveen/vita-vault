import json
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from tqdm import tqdm
import config

HEADERS = {"Authorization": f"token {config.GITHUB_TOKEN}"} if config.GITHUB_TOKEN else {}
OUT_PATH = "data/raw/github_issues.jsonl"

def get_issues(repo):
    issues = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {"state": "all", "per_page": 100, "page": page}
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code != 200:
            print(f"  Error {r.status_code} on {repo} page {page}: {r.text[:200]}")
            break
        batch = r.json()
        if not batch:
            break
        issues.extend(batch)
        page += 1
        time.sleep(0.3)
    return issues

def get_comments(repo, issue_number):
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return []
    return [c.get("body", "") for c in r.json()]

def scrape(include_comments=True):
    count = 0
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for repo in config.GITHUB_REPOS:
            print(f"Fetching issues for {repo} ...")
            issues = get_issues(repo)
            for issue in tqdm(issues):
                if "pull_request" in issue:
                    continue
                comments = []
                if include_comments and issue.get("comments", 0) > 0:
                    comments = get_comments(repo, issue["number"])
                    time.sleep(0.2)
                record = {
                    "id": f"gh_{repo.replace('/', '_')}_{issue['number']}",
                    "source": "github",
                    "repo": repo,
                    "title": issue.get("title", ""),
                    "body": issue.get("body") or "",
                    "comments": comments,
                    "url": issue.get("html_url"),
                    "date": issue.get("created_at"),
                }
                f.write(json.dumps(record) + "\n")
                count += 1
    print(f"Done. Wrote {count} issues to {OUT_PATH}")

if __name__ == "__main__":
    scrape()