import subprocess
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

DEST = "data/raw/wikis"

def clone_all():
    os.makedirs(DEST, exist_ok=True)
    for repo_url in config.WIKI_REPOS:
        name = repo_url.rstrip("/").split("/")[-1].replace(".wiki.git", "")
        target = os.path.join(DEST, name)
        if os.path.exists(target):
            print(f"Skipping {name}, already cloned. Run 'git -C {target} pull' to update.")
            continue
        print(f"Cloning {repo_url} ...")
        subprocess.run(["git", "clone", repo_url, target], check=False)

if __name__ == "__main__":
    clone_all()