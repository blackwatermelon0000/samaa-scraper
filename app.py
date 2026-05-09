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

nltk.download('punkt',     quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('stopwords', quiet=True)

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

REGISTRATION = "FA23-BAI-010"
NEWS_SOURCE  = "SAMAA TV"
BASE_URL     = "https://www.samaa.tv"

# ── Phrases to filter out from article body ──────────────────
COOKIE_PHRASES = [
    "your personal data",
    "we and our partners",
    "cookies, unique identifiers",
    "legitimate interest",
    "privacy and cookie",
    "manage or withdraw consent",
    "geolocation data",
    "list of partners",
    "stored by, accessed",
    "information from your device",
    "221 partners",
]


def clean_text(text):
    """Remove cookie consent and privacy policy sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for sentence in sentences:
        low = sentence.lower()
        if not any(phrase in low for phrase in COOKIE_PHRASES):
            cleaned.append(sentence)
    return " ".join(cleaned).strip()


def get_driver():
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
    opts.add_argument("--lang=en-US")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
    })

    service = Service("/usr/local/bin/chromedriver")
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)

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


def summarize(text, num_sentences=5):
    """LSA summarizer with fallback."""
    try:
        parser     = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        result     = summarizer(parser.document, num_sentences)
        summary    = " ".join(str(s) for s in result).strip()
        if summary:
            return summary
    except Exception as e:
        logger.warning(f"sumy failed: {e} — using fallback")

    sentences = re.split(r'(?<=[.!?])\s+', text)
    return " ".join(sentences[:num_sentences])


def scrape_samaa(keyword):
    driver = None
    try:
        driver = get_driver()

        # ── Step 1: Load homepage first ───────────────────────
        logger.info("Loading SAMAA TV homepage...")
        driver.get("https://www.samaa.tv")
        time.sleep(3)

        # ── Step 2: Go to search page ─────────────────────────
        search_url = f"{BASE_URL}/?s={keyword.replace(' ', '+')}"
        logger.info(f"Searching: {search_url}")
        driver.get(search_url)
        time.sleep(6)

        logger.info(f"Search page title: {driver.title}")

        # ── Step 3: Retry if blocked ──────────────────────────
        if (
            "error" in driver.title.lower()
            or "could not" in driver.page_source.lower()[:500]
        ):
            logger.warning("Possible block — retrying...")
            time.sleep(5)
            driver.get(search_url)
            time.sleep(7)

        # ── Step 4: Get ALL links from page ───────────────────
        links = driver.find_elements(By.TAG_NAME, "a")
        logger.info(f"Total links found on search page: {len(links)}")

        # ── Step 5: Find relevant article ─────────────────────
        # keyword_words = individual meaningful words in keyword
        keyword_words = [
            w.lower() for w in keyword.split()
            if len(w) > 2
        ]
        logger.info(f"Looking for keyword words: {keyword_words}")

        article_url = None

        # Strategy A: link TEXT contains any keyword word
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.text.strip().lower()
            if (
                "samaa.tv" in href
                and len(href) > 40
                and len(text) > 10
                and href != search_url
                and any(word in text for word in keyword_words)
            ):
                article_url = href
                logger.info(f"Strategy A match: {article_url}")
                break

        # Strategy B: keyword word in the URL itself
        if not article_url:
            logger.warning("Strategy A failed — trying URL keyword match")
            for link in links:
                href = (link.get_attribute("href") or "").lower()
                text = link.text.strip()
                if (
                    "samaa.tv" in href
                    and len(href) > 40
                    and len(text) > 10
                    and href != search_url
                    and any(word in href for word in keyword_words)
                ):
                    article_url = href
                    logger.info(f"Strategy B match: {article_url}")
                    break

        # Strategy C: just take first news article on page
        if not article_url:
            logger.warning("Strategy B failed — taking first news link")
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if (
                    "samaa.tv" in href
                    and len(href) > 40
                    and len(text) > 10
                    and href != search_url
                    and any(x in href for x in [
                        "/news/", "/pakistan/", "/world/",
                        "/sport/", "/business/", "/entertainment/",
                        "samaa.tv/20"
                    ])
                ):
                    article_url = href
                    logger.info(f"Strategy C match: {article_url}")
                    break

        if not article_url:
            logger.error("All strategies failed — no article found")
            return None, None

        # ── Step 6: Open the article ──────────────────────────
        logger.info(f"Opening: {article_url}")
        driver.get(article_url)
        time.sleep(4)

        # ── Step 7: Extract title ─────────────────────────────
        title = ""
        for sel in [
            "h1.entry-title", "h1.post-title",
            "h1", ".article-title", ".jeg_post_title"
        ]:
            try:
                el    = driver.find_element(By.CSS_SELECTOR, sel)
                title = el.text.strip()
                if title:
                    logger.info(f"Title: {title}")
                    break
            except Exception:
                continue

        if not title:
            title = driver.title.strip()

        # ── Step 8: Extract body ──────────────────────────────
        body = ""
        for sel in [
            ".story-detail", ".entry-content",
            ".article-content", ".post-content",
            ".td-post-content", ".jeg_post_content",
            ".content-area", "article"
        ]:
            try:
                container  = driver.find_element(By.CSS_SELECTOR, sel)
                paragraphs = container.find_elements(By.TAG_NAME, "p")
                body = " ".join(
                    p.text.strip()
                    for p in paragraphs
                    if p.text.strip()
                )
                if len(body) > 150:
                    logger.info(f"Body via [{sel}]: {len(body)} chars")
                    break
            except Exception:
                continue

        # Fallback
        if len(body) < 150:
            logger.warning("Using all <p> tags fallback")
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            body = " ".join(
                p.text.strip()
                for p in paragraphs
                if len(p.text.strip()) > 30
            )

        # ── Step 9: Clean cookie text from body ───────────────
        body      = clean_text(body)
        full_text = clean_text(f"{title}. {body}".strip())
        logger.info(f"Final text length: {len(full_text)} chars")
        return article_url, full_text

    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return None, None

    finally:
        if driver:
            driver.quit()


@app.route("/get", methods=["GET"])
def get_news():
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return jsonify(
            {"error": "Missing required query parameter: keyword"}
        ), 400

    logger.info(f"=== Request: keyword='{keyword}' ===")

    url, full_text = scrape_samaa(keyword)

    if not url or not full_text:
        return jsonify({
            "error": "Could not find or scrape an article for the given keyword."
        }), 404

    summary = summarize(full_text)

    return jsonify({
        "registration": REGISTRATION,
        "newssource":   NEWS_SOURCE,
        "keyword":      keyword,
        "url":          url,
        "summary":      summary
    }), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status":       "running",
        "registration": REGISTRATION,
        "newssource":   NEWS_SOURCE,
        "usage":        "GET /get?keyword=imran+khan"
    })


if __name__ == "__main__":
    logger.info("Starting SAMAA TV Scraper API on 0.0.0.0:7000 ...")
    app.run(host="0.0.0.0", port=7000, debug=False)
