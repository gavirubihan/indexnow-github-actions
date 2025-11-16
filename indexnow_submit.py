import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import os

# ========== CONFIGURATION ==========
API_KEY = os.getenv("INDEXNOW_API_KEY")  # load API key from GitHub Secrets
SITE_URL = "https://neovise.me"
SITEMAP_URL = "https://neovise.me/sitemap.xml"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

# Local files stored in the repo
LOG_FILE = "indexnow_log.txt"
URLS_FILE = "urls_to_submit.txt"
SUBMITTED_URLS_FILE = "submitted_urls.txt"

session = requests.Session()
session.trust_env = False


def log_message(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"{timestamp} {message}\n")
    print(message)


def fetch_sitemap_urls(sitemap_url):
    log_message(f"Fetching sitemap from {sitemap_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; IndexNowBot/1.0)"
        }
        response = session.get(sitemap_url, timeout=30, headers=headers)
        if response.status_code == 200:
            xml_data = response.text

            root = ET.fromstring(xml_data)
            urls = []

            # Namespace fallback
            for elem in root.iter():
                if elem.tag.endswith("loc"):
                    urls.append(elem.text.strip())

            log_message(f"Found {len(urls)} URLs in sitemap.")
            return urls

    except Exception as e:
        log_message(f"Error reading sitemap: {e}")
        return []


def load_submitted_urls():
    try:
        with open(SUBMITTED_URLS_FILE, "r") as f:
            return set(line.strip() for line in f.readlines())
    except FileNotFoundError:
        return set()


def save_submitted_urls(urls):
    with open(SUBMITTED_URLS_FILE, "a") as f:
        for url in urls:
            f.write(url + "\n")


def submit_to_indexnow(urls):
    payload = {
        "host": SITE_URL.replace("https://", "").replace("http://", ""),
        "key": API_KEY,
        "keyLocation": f"{SITE_URL}/{API_KEY}.txt",
        "urlList": urls,
    }

    response = session.post(INDEXNOW_ENDPOINT, json=payload)
    if response.status_code in (200, 202):
        log_message(f"Submitted {len(urls)} URLs OK.")
        return True
    else:
        log_message(f"IndexNow Error {response.status_code}: {response.text}")
        return False


def main():
    log_message("=" * 60)
    log_message("Starting IndexNow Auto Submission")

    all_urls = fetch_sitemap_urls(SITEMAP_URL)
    submitted = load_submitted_urls()

    new_urls = list(set(all_urls) - submitted)

    if not new_urls:
        log_message("No new URLs found. Done.")
        return

    log_message(f"{len(new_urls)} new URLs detected.")

    ok = submit_to_indexnow(new_urls)
    if ok:
        save_submitted_urls(new_urls)

    log_message("Done.")
    log_message("=" * 60)


if __name__ == "__main__":
    main()
