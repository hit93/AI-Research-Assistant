"""
Full-Text Fetcher — Fetches full article body for arXiv papers (HTML/PDF) and web pages.
Falls back gracefully to abstract/snippet when full text is inaccessible,
recording `has_full_text` for downstream conservative wording & transparency.
"""

import io
import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from src.models.schemas import ResearchSource
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger("tools.full_text_fetcher")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
TIER_1_DOMAINS = {
    "nist.gov",
    "ieee.org",
    "nature.com",
    "science.org",
    "acm.org",
    "arxiv.org",
    "research.ibm.com",
    "ibm.com",
    "quantumai.google",
    "blog.google",
    "microsoft.com",
    "aws.amazon.com",
    "energy.gov",
    "ornl.gov",
    "lanl.gov",
}


def _extract_arxiv_id(url_or_id: str) -> str:
    """Extract standard clean arXiv ID from string or URL."""
    clean = url_or_id.strip()
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", clean)
    if match:
        return match.group(1)
    if "arxiv:" in clean.lower():
        return clean.split(":")[-1].strip()
    return clean.split("/")[-1].replace(".pdf", "")


def fetch_arxiv_full_text(url_or_id: str, timeout: float | None = None) -> tuple[str, bool]:
    """
    Attempt to fetch the full text of an arXiv paper.
    Tries arXiv HTML first, falls back to PDF parsing via pypdf.
    """
    arxiv_id = _extract_arxiv_id(url_or_id)
    if not arxiv_id:
        return "", False

    timeout_val = timeout or settings.FULL_TEXT_FETCH_TIMEOUT
    headers = {"User-Agent": USER_AGENT}

    # 1. Try arXiv HTML format (available for many modern papers)
    html_urls = [
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ]
    for html_url in html_urls:
        try:
            resp = requests.get(html_url, headers=headers, timeout=timeout_val)
            if resp.status_code == 200 and len(resp.text) > 1000:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove navigation, headers, footers, bib items
                for tag in soup(["script", "style", "nav", "header", "footer", "section.ltx_bibliography"]):
                    tag.decompose()
                main_article = soup.find("article") or soup.find("main") or soup.body
                if main_article:
                    text = main_article.get_text(separator="\n ")
                    clean = re.sub(r"[ \t]+", " ", text).strip()
                    clean = re.sub(r"\n{3,}", "\n\n", clean)
                    if len(clean) > 800:
                        logger.info(f"[FullText] Retrieved arXiv HTML full text ({len(clean)} chars) for {arxiv_id}")
                        return clean[:35000], True
        except Exception as e:
            logger.debug(f"[FullText] arXiv HTML fetch failed for {html_url}: {e}")

    # 2. Try PDF download and extraction via pypdf
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        resp = requests.get(pdf_url, headers=headers, timeout=timeout_val, stream=True)
        if resp.status_code == 200:
            import pypdf
            pdf_bytes = io.BytesIO(resp.content)
            reader = pypdf.PdfReader(pdf_bytes)
            pages_text = []
            # Extract text up to first 12 pages
            for page in reader.pages[:12]:
                extracted = page.extract_text()
                if extracted:
                    pages_text.append(extracted)
            full_pdf_text = "\n\n".join(pages_text).strip()
            if len(full_pdf_text) > 800:
                logger.info(f"[FullText] Retrieved arXiv PDF full text ({len(full_pdf_text)} chars) for {arxiv_id}")
                return full_pdf_text[:35000], True
    except Exception as e:
        logger.debug(f"[FullText] arXiv PDF fetch failed for {pdf_url}: {e}")

    return "", False


def fetch_web_full_text(url: str, timeout: float | None = None) -> tuple[str, bool]:
    """
    Fetch and extract clean article text from a web URL, stripping boilerplate.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        return "", False

    timeout_val = timeout or settings.FULL_TEXT_FETCH_TIMEOUT
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout_val)
        if resp.status_code == 200 and len(resp.text) > 500:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
                tag.decompose()

            # Target main content containers
            content_node = (
                soup.find("article")
                or soup.find("main")
                or soup.find(class_=re.compile(r"content|post|article|entry", re.I))
                or soup.body
            )
            if content_node:
                # Collect paragraphs or text blocks
                paragraphs = [p.get_text(separator=" ").strip() for p in content_node.find_all(["p", "h2", "h3", "li"])]
                text = "\n\n".join(p for p in paragraphs if len(p) > 25)
                if not text:
                    text = content_node.get_text(separator=" ")
                clean = re.sub(r"[ \t]+", " ", text).strip()
                clean = re.sub(r"\n{3,}", "\n\n", clean)
                if len(clean) > 400:
                    logger.info(f"[FullText] Retrieved Web full text ({len(clean)} chars) for {url}")
                    return clean[:25000], True
    except Exception as e:
        logger.debug(f"[FullText] Web page body fetch failed for {url}: {e}")

    return "", False


def determine_source_tier(url_or_id: str, source_type: str) -> int:
    """Classify source into quality tiers (1 = primary/peer-reviewed, 2 = secondary, 3 = tertiary)."""
    if source_type == "arxiv":
        return 1

    parsed = urlparse(url_or_id.lower())
    domain = parsed.netloc

    if any(domain == d or domain.endswith("." + d) for d in TIER_1_DOMAINS):
        return 1
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 1
    if "wikipedia.org" in domain:
        return 3

    return 2


def enrich_source_with_full_text(source: ResearchSource, timeout: float | None = None) -> ResearchSource:
    """
    Fetch full text for a source, populating has_full_text and full_text.
    Preserves original abstract/snippet content if full text is unavailable.
    """
    source.source_tier = determine_source_tier(source.url_or_id, source.source_type)

    full_text = ""
    success = False

    if source.source_type == "arxiv":
        full_text, success = fetch_arxiv_full_text(source.url_or_id, timeout=timeout)
    elif source.source_type == "web":
        full_text, success = fetch_web_full_text(source.url_or_id, timeout=timeout)

    if success and full_text:
        source.has_full_text = True
        source.full_text = full_text
        # Keep a rich preview in content for prompt budgeting, but retain complete body in full_text
        source.content = full_text[:3000]
    else:
        source.has_full_text = False
        source.full_text = source.content

    return source
