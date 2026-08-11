import json
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
import config

OUT_PATH = "data/raw/forum_posts.jsonl"

def scrape_thread(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_timeout(1500)
    title = page.title()

    # XenForo-based forums (GBAtemp, PSX-Place) use ".message" for each post.
    # Inspect the page (right-click -> Inspect) and adjust this selector if it doesn't match.
    post_elements = page.query_selector_all(".message-body, .message")
    posts = []
    for el in post_elements:
        text = el.inner_text().strip()
        if text:
            posts.append(text)
    return {
        "id": f"forum_{abs(hash(url))}",
        "source": "forum",
        "title": title,
        "url": url,
        "body": "\n\n".join(posts),
    }

def scrape():
    if not config.FORUM_SEED_URLS:
        print("No URLs in config.FORUM_SEED_URLS — add some thread URLs first.")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for url in config.FORUM_SEED_URLS:
                try:
                    record = scrape_thread(page, url)
                    f.write(json.dumps(record) + "\n")
                    print(f"OK: {url}")
                except Exception as e:
                    print(f"FAILED: {url} ({e})")
                time.sleep(2)  # be polite
        browser.close()

if __name__ == "__main__":
    scrape()