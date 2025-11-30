import requests
import xml.etree.ElementTree as ET
import time
import json
import os
from datetime import datetime

# ========== CONFIGURATION (GitHub Actions) ==========
# Read secrets/variables from environment
API_KEY = os.getenv("INDEXNOW_API_KEY")
SITE_URL = os.getenv("SITE_URL")
SITEMAP_URL = os.getenv("SITEMAP_URL")

# Constants
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
LOG_FILE = "indexnow_log.txt"
URLS_FILE = "urls_to_submit.txt"
SUBMITTED_URLS_FILE = "submitted_urls.txt"  # Legacy tracking file
SUBMISSION_HISTORY_FILE = "submission_history.json"  # New tracking file with dates

# Configure session with DNS override
session = requests.Session()
session.trust_env = False

# ========== LOGGING & OUTPUT ==========

def log_file(message):
    """Save message to log file with timestamp."""
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"{timestamp} {message}\n")
    except Exception:
        pass # Fail silently if logging fails

def console_print(message, level="INFO"):
    """Print clean message to console."""
    prefix = "   "
    if level == "STEP":
        print(f"\n{message}")
        return
    elif level == "SUCCESS":
        prefix = "✅ "
    elif level == "WARNING":
        prefix = "⚠️ "
    elif level == "ERROR":
        prefix = "❌ "
    elif level == "INFO":
        prefix = "   "
    
    print(f"{prefix}{message}")

def log(message, console=True, level="INFO"):
    """Log to file and optionally print to console."""
    log_file(message)
    if console:
        console_print(message, level)

# ========== CORE FUNCTIONS ==========

def fetch_sitemap_urls(sitemap_url, silent_console=False):
    """Fetch all URLs from sitemap.xml with lastmod dates."""
    if not silent_console:
        log_file(f"Fetching sitemap from {sitemap_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = session.get(
            sitemap_url, 
            timeout=30,
            headers=headers
        )
        
        if response.status_code == 200:
            xml_data = response.text
            root = ET.fromstring(xml_data)
            urls = {}  # Dictionary: {url: lastmod}
            
            # Define common namespaces
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9',
                'xhtml': 'http://www.w3.org/1999/xhtml',
                'image': 'http://www.google.com/schemas/sitemap-image/1.1',
                'video': 'http://www.google.com/schemas/sitemap-video/1.1'
            }
            
            # Helper to extract URL and Lastmod
            def extract_url_info(element, ns=None):
                if ns:
                    loc = element.find('sm:loc', ns)
                    lastmod = element.find('sm:lastmod', ns)
                else:
                    loc = element.find('loc')
                    lastmod = element.find('lastmod')
                
                if loc is not None and loc.text:
                    url = loc.text.strip()
                    date_str = lastmod.text.strip() if lastmod is not None and lastmod.text else None
                    return url, date_str
                return None, None

            # Try WITH namespace
            for url_elem in root.findall('sm:url', namespaces):
                url, lastmod = extract_url_info(url_elem, namespaces)
                if url:
                    urls[url] = lastmod
            
            # Try WITHOUT namespace (fallback)
            if not urls:
                for url_elem in root.findall('.//url'):
                    url, lastmod = extract_url_info(url_elem)
                    if url:
                        urls[url] = lastmod
            
            # Check for sitemap index
            if not urls:
                for sitemap_elem in root.findall('sm:sitemap', namespaces):
                    loc_elem = sitemap_elem.find('sm:loc', namespaces)
                    if loc_elem is not None and loc_elem.text:
                        log_file(f"Found sub-sitemap: {loc_elem.text}")
                        # Recursively fetch sub-sitemap
                        sub_urls = fetch_sitemap_urls(loc_elem.text.strip(), silent_console=True)
                        urls.update(sub_urls)
                        time.sleep(0.5) # Small delay to be nice
            
            return urls
        else:
            log(f"Failed to fetch sitemap: {response.status_code}", level="ERROR")
            return {}
            
    except Exception as e:
        log(f"Error fetching sitemap: {e}", level="ERROR")
        return {}

def load_submission_history():
    """Load submission history from JSON file."""
    history = {}
    if os.path.exists(SUBMISSION_HISTORY_FILE):
        try:
            with open(SUBMISSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            log_file(f"Loaded history for {len(history)} URLs")
            return history
        except Exception as e:
            log(f"Error loading JSON history: {e}", level="ERROR")
    
    # Fallback: Migrate from legacy text file
    if os.path.exists(SUBMITTED_URLS_FILE):
        log("Migrating legacy submission history...", level="WARNING")
        try:
            with open(SUBMITTED_URLS_FILE, "r", encoding="utf-8") as f:
                legacy_urls = [line.strip() for line in f if line.strip()]
            for url in legacy_urls:
                history[url] = "1970-01-01T00:00:00Z"
            return history
        except Exception:
            pass
            
    return history

def save_submission_history(history):
    """Save submission history to JSON file."""
    try:
        with open(SUBMISSION_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        log_file(f"Saved history to {SUBMISSION_HISTORY_FILE}")
        return True
    except Exception as e:
        log(f"Error saving history: {e}", level="ERROR")
        return False

def identify_urls_to_submit(sitemap_urls, history):
    """Identify new or updated URLs to submit."""
    to_submit = []
    
    for url, current_lastmod in sitemap_urls.items():
        if url not in history:
            log_file(f"New URL found: {url}")
            to_submit.append(url)
            continue
            
        history_lastmod = history.get(url)
        if current_lastmod and history_lastmod:
            # DEBUG LOGGING for specific URL
            if "li-fi-technology" in url:
                 log_file(f"DEBUG: Checking {url}: Sitemap={current_lastmod} History={history_lastmod}")
            
            if current_lastmod > history_lastmod:
                log_file(f"Updated content: {url} ({current_lastmod} > {history_lastmod})")
                to_submit.append(url)
    
    return to_submit

def save_urls_to_file(urls, filename):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for url in urls:
                f.write(url + "\n")
        return True
    except Exception as e:
        log(f"Error saving URLs to file: {e}", level="ERROR")
        return False

def submit_to_indexnow(urls):
    """Submit URLs to IndexNow API."""
    if len(urls) > 10000:
        log("WARNING: >10,000 URLs. Submitting first 10k only.", level="WARNING")
        urls = urls[:10000]
    
    payload = {
        "host": SITE_URL.replace("https://", "").replace("http://", ""),
        "key": API_KEY,
        "keyLocation": f"{SITE_URL}/{API_KEY}.txt",
        "urlList": urls
    }

    try:
        log_file(f"Submitting {len(urls)} URLs...")
        response = session.post(INDEXNOW_ENDPOINT, json=payload, timeout=60)
        status = response.status_code

        if status == 200 or status == 202:
            log_file(f"SUCCESS: {len(urls)} URLs submitted (Status: {status})")
            return True
        elif status == 429:
            log("Too many requests (429). Retrying in 60s...", level="WARNING")
            time.sleep(60)
            return submit_to_indexnow(urls)
        else:
            log(f"Submission failed: {status} - {response.text}", level="ERROR")
            return False

    except Exception as e:
        log(f"Submission error: {e}", level="ERROR")
        return False

def main():
    print("=" * 50)
    print("      IndexNow Submission (Smart Mode)")
    print("=" * 50)
    
    # Validate Environment Variables
    if not API_KEY or not SITE_URL or not SITEMAP_URL:
        console_print("Missing environment variables!", level="ERROR")
        console_print("Ensure INDEXNOW_API_KEY, SITE_URL, and SITEMAP_URL are set.", level="ERROR")
        return

    # Step 1: Fetch
    console_print("[1/5] Fetching sitemaps...", level="STEP")
    sitemap_data = fetch_sitemap_urls(SITEMAP_URL)
    if not sitemap_data:
        console_print("No URLs found in sitemap.", level="ERROR")
        return
    console_print(f"Found {len(sitemap_data)} URLs in sitemap.", level="INFO")

    # Step 2: History
    console_print("[2/5] Loading history...", level="STEP")
    history = load_submission_history()
    console_print(f"Loaded {len(history)} previously submitted URLs.", level="INFO")

    # Step 3: Identify
    console_print("[3/5] Analyzing for updates...", level="STEP")
    urls_to_submit = identify_urls_to_submit(sitemap_data, history)
    
    if not urls_to_submit:
        console_print("No new or updated content found.", level="SUCCESS")
        print("\n" + "=" * 50)
        print("                  SUMMARY")
        print("=" * 50)
        print(f" Total URLs:      {len(sitemap_data)}")
        print(f" New/Updated:     0")
        print(f" Status:          Skipped (Nothing new)")
        print("=" * 50 + "\n")
        return
    
    console_print(f"Found {len(urls_to_submit)} URLs to submit.", level="INFO")

    # Step 4: Save temp
    console_print(f"[4/5] Saving list to {URLS_FILE}...", level="STEP")
    save_urls_to_file(urls_to_submit, URLS_FILE)

    # Step 5: Submit
    console_print("[5/5] Submitting to IndexNow...", level="STEP")
    success = submit_to_indexnow(urls_to_submit)

    # Update History
    if success:
        for url in urls_to_submit:
            if url in sitemap_data:
                history[url] = sitemap_data[url]
        save_submission_history(history)
        console_print("History updated.", level="SUCCESS")

    # Summary
    print("\n" + "=" * 50)
    print("                  SUMMARY")
    print("=" * 50)
    print(f" Total URLs:      {len(sitemap_data)}")
    print(f" Submitted:       {len(urls_to_submit)}")
    print(f" Status:          {'SUCCESS' if success else 'FAILED'}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
