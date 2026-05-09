# ============================================================
# SAMAA TV News Scraper API
# Registration: FA23-BAI-010
# News Source:  SAMAA TV
# Endpoint:     GET /get?keyword=your_keyword  port 7000
# ============================================================

import time
import re
import logging

from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import nltk

# Download required NLTK data on startup
nltk.download('punkt',     quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('stopwords', quiet=True)

# ── Flask App Setup ──────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
REGISTRATION = "FA23-BAI-010"
NEWS_SOURCE  = "SAMAA TV"
BASE_URL     = "https://www.samaa.tv"


# ── Chrome Driver Factory ────────────────────────────────────
def get_driver():
    """
    Returns a headless Chrome WebDriver configured for Docker.
    Uses strong anti-detection to avoid CloudFront blocking.
    """
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-web-security")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--lang=en-US")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # Hide automation flags so site does not block us
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
    })

    service = Service("/usr/local/bin/chromedriver")
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)

    # Remove webdriver fingerprint — critical anti-detection step
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """
    })
    return driver


# ── Text Summarizer ──────────────────────────────────────────
def summarize(text, num_sentences=5):
    """
    Uses sumy LSA algorithm to extract most important sentences.
    Falls back to first N sentences if sumy fails.
    """
    try:
        parser     = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        result     = summarizer(parser.document, num_sentences)
        summary    = " ".join(str(s) for s in result).strip()
        if summary:
            return summary
    except Exception as e:
        logger.warning(f"sumy failed: {e} — using fallback")

    # Fallback: return first 5 sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return " ".join(sentences[:num_sentences])


# ── Core Scraping Logic ──────────────────────────────────────
def scrape_samaa(keyword):
    """
    1. Loads SAMAA TV homepage first (avoids CloudFront block)
    2. Navigates to search results for keyword
    3. Finds FIRST RELEVANT article matching the keyword
    4. Extracts title + body text
    5. Returns (article_url, full_text)
    """
    driver = None
    try:
        driver = get_driver()

        # ── Step 1: Load homepage first ───────────────────────
        # Going directly to search triggers CloudFront firewall.
        # Loading homepage first makes browser look like real user.
        logger.info("Loading SAMAA TV homepage first...")
        driver.get("https://www.samaa.tv")
        time.sleep(4)

        # ── Step 2: Navigate to search results ────────────────
        search_url = f"{BASE_URL}/?s={keyword.replace(' ', '+')}"
        logger.info(f"Navigating to search: {search_url}")
        driver.get(search_url)
        time.sleep(5)

        # ── Step 3: Check if blocked by CloudFront ────────────
        page_title  = driver.title
        page_source = driver.page_source
        logger.info(f"Search page title: {page_title}")

        if "ERROR" in page_title.upper() or "request could not" in page_source.lower():
            logger.warning("CloudFront block detected — waiting and retrying...")
            time.sleep(6)
            driver.get(search_url)
            time.sleep(7)
            logger.info(f"Retry page title: {driver.title}")

        # ── Step 4: Find FIRST RELEVANT article ───────────────
        # We check the link TEXT contains keyword words so we
        # don't accidentally pick unrelated trending articles.
        article_url  = None
        keyword_words = [w.lower() for w in keyword.split() if len(w) > 2]

        # Strategy A: look for links whose text matches keyword
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.text.strip().lower()
            if (
                "samaa.tv" in href
                and len(href) > 40
                and len(text) > 15
                and href != search_url
                and any(word in text for word in keyword_words)
            ):
                article_url = href
                logger.info(f"Found relevant article (keyword match): {article_url}")
                break

        # Strategy B: if no keyword match found, take first
        # news article on the search results page
        if not article_url:
            logger.warning("No keyword-matching link — taking first news article")
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if (
                    "samaa.tv" in href
                    and len(href) > 40
                    and len(text) > 15
                    and href != search_url
                    and any(x in href for x in [
                        "/news/", "/pakistan/", "/world/",
                        "/sport/", "/business/", "/entertainment/",
                        "samaa.tv/20"
                    ])
                ):
                    article_url = href
                    logger.info(f"Found first news article: {article_url}")
                    break

        if not article_url:
            logger.error("No article link found on search page.")
            return None, None

        # ── Step 5: Open the article ──────────────────────────
        logger.info(f"Opening article: {article_url}")
        driver.get(article_url)
        time.sleep(4)

        # ── Step 6: Extract title ─────────────────────────────
        title = ""
        for sel in [
            "h1.entry-title",
            "h1.post-title",
            "h1",
            ".article-title",
            ".jeg_post_title"
        ]:
            try:
                el    = driver.find_element(By.CSS_SELECTOR, sel)
                title = el.text.strip()
                if title:
                    logger.info(f"Title via [{sel}]: {title}")
                    break
            except Exception:
                continue

        if not title:
            title = driver.title.strip()
            logger.info(f"Title from browser tab: {title}")

        # ── Step 7: Extract article body ──────────────────────
        body = ""
        body_selectors = [
            ".story-detail",
            ".entry-content",
            ".article-content",
            ".post-content",
            ".td-post-content",
            ".jeg_post_content",
            ".content-area",
            "article .content",
            "article",
        ]

        for sel in body_selectors:
            try:
                container  = driver.find_element(By.CSS_SELECTOR, sel)
                paragraphs = container.find_elements(By.TAG_NAME, "p")
                body = " ".join(
                    p.text.strip()
                    for p in paragraphs
                    if p.text.strip()
                )
                if len(body) > 150:
                    logger.info(f"Body via [{sel}], length={len(body)} chars")
                    break
            except Exception:
                continue

        # Fallback: all <p> tags on entire page
        if len(body) < 150:
            logger.warning("Body selectors failed — scanning all <p> tags")
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            body = " ".join(
                p.text.strip()
                for p in paragraphs
                if len(p.text.strip()) > 30
            )

        full_text = f"{title}. {body}".strip()
        logger.info(f"Total text length: {len(full_text)} chars")
        return article_url, full_text

    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return None, None

    finally:
        if driver:
            driver.quit()


# ── API Endpoint ─────────────────────────────────────────────
@app.route("/get", methods=["GET"])
def get_news():
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return jsonify(
            {"error": "Missing required query parameter: keyword"}
        ), 400

    logger.info(f"=== New request: keyword='{keyword}' ===")

    url, full_text = scrape_samaa(keyword)

    if not url or not full_text:
        return jsonify({
            "error": (
                "Could not find or scrape an article "
                "for the given keyword."
            )
        }), 404

    summary = summarize(full_text)

    response = {
        "registration": REGISTRATION,
        "newssource":   NEWS_SOURCE,
        "keyword":      keyword,
        "url":          url,
        "summary":      summary
    }

    logger.info(f"=== Response ready for keyword='{keyword}' ===")
    return jsonify(response), 200


# ── Health Check ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status":       "running",
        "registration": REGISTRATION,
        "newssource":   NEWS_SOURCE,
        "usage":        "GET /get?keyword=imran+khan"
    })


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting SAMAA TV Scraper API on 0.0.0.0:7000 ...")
    app.run(host="0.0.0.0", port=7000, debug=False)
