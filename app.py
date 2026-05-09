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
from webdriver_manager.chrome import ChromeDriverManager
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
    --no-sandbox            : required when running as root in Docker
    --disable-dev-shm-usage : /dev/shm is too small in Docker by default
    --headless=new          : modern headless mode (Chrome 112+)
    """
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # Hide automation flags so the site does not block us
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(40)
    return driver


# ── Text Summarizer ──────────────────────────────────────────
def summarize(text, num_sentences=5):
    """
    Uses sumy LSA algorithm to extract the most important sentences.
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

    # Fallback: first 5 sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return " ".join(sentences[:num_sentences])


# ── Core Scraping Logic ──────────────────────────────────────
def scrape_samaa(keyword):
    """
    1. Opens SAMAA TV search page for the keyword
    2. Finds and clicks the first article link
    3. Extracts title + body text
    4. Returns (article_url, full_text)
    """
    driver = None
    try:
        driver = get_driver()
        wait   = WebDriverWait(driver, 20)

        # ── Step 1: Open search results page ─────────────────
        search_url = f"{BASE_URL}/?s={keyword.replace(' ', '+')}"
        logger.info(f"Opening search URL: {search_url}")
        driver.get(search_url)
        time.sleep(3)

        # ── Step 2: Find first article link ──────────────────
        article_url = None

        candidate_selectors = [
            "h2.entry-title a",
            "h3.entry-title a",
            ".post-title a",
            "article h2 a",
            "article h3 a",
            ".jeg_post_title a",
            ".td-module-title a",
            "h2 a",
            "h3 a",
            ".search-result a",
            "a.title",
        ]

        for selector in candidate_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    href = el.get_attribute("href") or ""
                    if "samaa.tv" in href and len(href) > 30:
                        article_url = href
                        logger.info(
                            f"Found article: {article_url} "
                            f"via selector [{selector}]"
                        )
                        break
                if article_url:
                    break
            except Exception:
                continue

        # Last resort: scan all <a> tags on the page
        if not article_url:
            logger.warning("Named selectors failed — scanning all <a> tags")
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if (
                    "samaa.tv" in href
                    and len(href) > 40
                    and len(text) > 10
                    and href != search_url
                ):
                    article_url = href
                    break

        if not article_url:
            logger.error("No article link found on search results page.")
            return None, None

        # ── Step 3: Open the article ──────────────────────────
        logger.info(f"Navigating to article: {article_url}")
        driver.get(article_url)
        time.sleep(3)

        # ── Step 4: Extract title ─────────────────────────────
        title = ""
        for sel in [
            "h1.entry-title",
            "h1.post-title",
            "h1",
            ".article-title"
        ]:
            try:
                el    = driver.find_element(By.CSS_SELECTOR, sel)
                title = el.text.strip()
                if title:
                    break
            except Exception:
                continue

        if not title:
            title = driver.title.strip()
        logger.info(f"Title: {title}")

        # ── Step 5: Extract article body ──────────────────────
        body = ""
        body_selectors = [
            ".story-detail",
            ".entry-content",
            ".article-content",
            ".post-content",
            ".td-post-content",
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
                    logger.info(
                        f"Body extracted via [{sel}], "
                        f"length={len(body)} chars"
                    )
                    break
            except Exception:
                continue

        # Absolute fallback: every <p> on the whole page
        if len(body) < 150:
            logger.warning("Body selectors failed — using all <p> tags")
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            body = " ".join(
                p.text.strip()
                for p in paragraphs
                if len(p.text.strip()) > 30
            )

        full_text = f"{title}. {body}".strip()
        logger.info(f"Total extracted text length: {len(full_text)} chars")
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


# ── Health Check Endpoint ─────────────────────────────────────
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