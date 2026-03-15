"""Scraping tool definitions and implementations for the ScraperAgent."""
import re
from typing import Optional
import requests
from bs4 import BeautifulSoup
import markdownify

# ── ATS-specific CSS selectors ────────────────────────────────────────────────
ATS_SELECTORS = {
    "greenhouse": [
        "#app_body", ".job-post", ".application-body", "#content",
    ],
    "lever": [
        ".posting-page", ".posting", "#main", ".content",
    ],
    "workday": [
        "[data-automation-id='jobPostingDescription']",
        ".job-description", "#job-description",
    ],
    "stepstone": [
        "[data-at='job-ad-overview-text']",
        ".job-ad-display", ".JobAd-content",
    ],
    "xing": [
        ".job-description", "[data-testid='job-description']",
        ".jobs-description",
    ],
    "linkedin": None,  # JS-rendered — not supported
    "generic": [
        "article", "main", "#main-content", ".job-description",
        ".job-details", ".description", "[itemprop='description']",
        "#job-details", ".posting-requirements",
    ],
}

JS_HEAVY_DOMAINS = ["linkedin.com", "linkedin.de"]


# ── Tool Definitions ──────────────────────────────────────────────────────────

FETCH_URL_TOOL = {
    "name": "fetch_url",
    "description": "Fetch the HTML content of a URL via HTTP GET.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch."},
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds.",
                "default": 15,
            },
        },
        "required": ["url"],
    },
}

EXTRACT_TEXT_FROM_HTML_TOOL = {
    "name": "extract_text_from_html",
    "description": (
        "Extract the relevant job posting text from raw HTML using ATS-specific selectors. "
        "Returns cleaned text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "html": {"type": "string", "description": "Raw HTML string."},
            "url": {"type": "string", "description": "Original URL (used to pick selectors)."},
        },
        "required": ["html", "url"],
    },
}

CONVERT_TO_MARKDOWN_TOOL = {
    "name": "convert_to_markdown",
    "description": "Convert extracted HTML or plain text into clean Markdown.",
    "input_schema": {
        "type": "object",
        "properties": {
            "html": {"type": "string", "description": "HTML or plain text to convert."},
        },
        "required": ["html"],
    },
}

SUBMIT_SCRAPER_TOOL = {
    "name": "submit_scraper_result",
    "description": "Submit the final structured scraper result. Call this as the last step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "raw_markdown": {"type": "string", "description": "Full job posting in Markdown."},
            "filepath": {"type": "string", "description": "Path where the file was saved."},
            "job_title": {"type": "string", "description": "Extracted job title."},
            "company_name": {"type": "string", "description": "Extracted company name."},
            "slug": {"type": "string", "description": "URL slug used for the filename."},
        },
        "required": ["raw_markdown", "filepath", "job_title", "company_name", "slug"],
    },
}


# ── Implementations ───────────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 15) -> dict:
    for domain in JS_HEAVY_DOMAINS:
        if domain in url:
            return {
                "error": (
                    f"JavaScript-heavy portal detected ({domain}). "
                    "This site requires a browser/JS renderer which is not supported. "
                    "Please copy the job description manually and use --cv with a local file."
                )
            }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return {"html": resp.text, "status_code": resp.status_code, "url": resp.url}
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP error: {e}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed. Check the URL and your internet connection."}
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {timeout}s."}
    except Exception as e:
        return {"error": str(e)}


def _detect_ats(url: str) -> str:
    url_lower = url.lower()
    for ats in ["greenhouse", "lever", "workday", "stepstone", "xing"]:
        if ats in url_lower:
            return ats
    return "generic"


def extract_text_from_html(html: str, url: str) -> dict:
    ats = _detect_ats(url)
    soup = BeautifulSoup(html, "lxml")

    # Remove boilerplate
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
        tag.decompose()

    selectors = ATS_SELECTORS.get(ats, []) or []
    selectors = selectors + ATS_SELECTORS["generic"]

    extracted = None
    for selector in selectors:
        el = soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 200:
            extracted = el
            break

    if not extracted:
        extracted = soup.body or soup

    # Return as HTML string for markdownify
    return {
        "extracted_html": str(extracted),
        "ats_detected": ats,
        "char_count": len(extracted.get_text()),
    }


def convert_to_markdown(html: str) -> dict:
    md = markdownify.markdownify(
        html,
        heading_style="ATX",
        strip=["a"],
        newline_style="backslash",
    )
    # Clean up excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return {"markdown": md}


SCRAPER_TOOL_HANDLERS = {
    "fetch_url": lambda inp: fetch_url(**inp),
    "extract_text_from_html": lambda inp: extract_text_from_html(**inp),
    "convert_to_markdown": lambda inp: convert_to_markdown(**inp),
    "submit_scraper_result": lambda inp: inp,  # Pass-through; handled by agent
}
