# ============================================================
# SAMAA TV News Scraper API
# Registration: FA23-BAI-010
# News Source: SAMAA TV
# Endpoint: GET /get?keyword=your_keyword
# ============================================================

import time
import re
import logging
from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import nltk

# Download NLTK data
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

REGISTRATION = "FA23-BAI-010"
NEWS_SOURCE = "SAMAA TV"

# Cookie / Privacy consent phrases to remove
COOKIE_PHRASES = [
    "personal data", "221 partners", "cookies,", "geolocation data",
    "legitimate interest", "manage or withdraw consent", "privacy and cookie",
    "your device", "stored by, accessed", "information from your device"
]

def clean_text(text):
    """Remove cookie consent and unwanted text"""
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = [
        s.strip() for s in sentences 
        if s.strip() and not any(phrase in s.lower() for phrase in COOKIE_PHRASES)
    ]
    return " ".join(cleaned).strip()

def get_driver():
    """Configure Chrome driver for Docker"""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)
    return driver

def summarize_text(text, num_sentences=5):
    """Extractive summarization with fallback"""
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        result = summarizer(parser.document, num_sentences)
        return " ".join(str(sentence) for sentence in result).strip()
    except Exception as e:
        logger.warning(f"Sumy failed: {e} - using fallback")
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return " ".join(sentences[:num_sentences]).strip()

@app.route("/get", methods=["GET"])
def get_news():
    keyword = request.args.get("keyword", "").strip()
    
    if not keyword:
        return jsonify({"error": "Missing required parameter: keyword"}), 400

    logger.info(f"Received request for keyword: '{keyword}'")
    
    driver = None
    try:
        driver = get_driver()
        
        # Use direct search URL (most reliable method)
        search_url = f"https://www.samaa.tv/?s={keyword.replace(' ', '+')}"
        logger.info(f"Opening search URL: {search_url}")
        driver.get(search_url)
        time.sleep(6)

        # Find article link
        article_url = None
        
        # Strategy 1: Best selector for news links
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='samaa.tv/20']")
            for link in links:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href and len(text) > 15 and "samaa.tv" in href:
                    article_url = href
                    logger.info(f"Found article: {article_url}")
                    break
        except:
            pass

        # Strategy 2: Fallback - any long article link
        if not article_url:
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href") or ""
                if "samaa.tv/20" in href and len(href) > 50:
                    article_url = href
                    logger.info(f"Fallback article found: {article_url}")
                    break

        if not article_url:
            return jsonify({
                "error": "Could not find any article for the given keyword"
            }), 404

        # Open the article
        logger.info(f"Opening article: {article_url}")
        driver.get(article_url)
        time.sleep(5)

        # Extract Title
        title = driver.title.strip()
        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            if h1.text and len(h1.text.strip()) > 5:
                title = h1.text.strip()
        except:
            pass

        # Extract Body
        body = ""
        content_selectors = [
            "article", ".entry-content", ".jeg_post_content", 
            ".story-detail", ".post-content", ".content-area"
        ]
        
        for selector in content_selectors:
            try:
                container = driver.find_element(By.CSS_SELECTOR, selector)
                paragraphs = container.find_elements(By.TAG_NAME, "p")
                body = " ".join(
                    p.text.strip() for p in paragraphs 
                    if len(p.text.strip()) > 30
                )
                if len(body) > 200:
                    break
            except:
                continue

        # Final fallback
        if len(body) < 150:
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            body = " ".join(
                p.text.strip() for p in paragraphs 
                if len(p.text.strip()) > 40
            )

        # Clean and summarize
        full_text = clean_text(f"{title}. {body}")
        summary = summarize_text(full_text, 5)
        summary = clean_text(summary)  # Extra cleaning

        return jsonify({
            "registration": REGISTRATION,
            "newssource": NEWS_SOURCE,
            "keyword": keyword,
            "url": article_url,
            "summary": summary
        })

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            "error": "Failed to scrape article",
            "message": str(e)[:150]
        }), 500

    finally:
        if driver:
            driver.quit()


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "running",
        "registration": REGISTRATION,
        "newssource": NEWS_SOURCE,
        "message": "Use /get?keyword=your_keyword"
    })


if __name__ == "__main__":
    logger.info("Starting SAMAA TV Scraper API on port 7000...")
    app.run(host="0.0.0.0", port=7000, debug=False)
