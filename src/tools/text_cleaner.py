import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from src.models.schemas import ResearchSource


LOW_AUTHORITY_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "www.reddit.com",
    "tiktok.com",
    "pinterest.com",
}

SPONSORED_PATTERNS = [
    r"/sponsored/",
    r"/promoted/",
    r"/advertisement/",
    r"/native-ad/",
]


def clean_text(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def deduplicate_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    """Deduplicate sources by url_or_id and normalized title."""
    seen_ids = set()
    unique = []
    for s in sources:
        url_clean = s.url_or_id.strip().lower()
        title_clean = s.title.strip().lower()
        key = (url_clean, title_clean)
        if key not in seen_ids and url_clean not in seen_ids:
            seen_ids.add(key)
            seen_ids.add(url_clean)
            unique.append(s)
    return unique


def is_low_authority_or_sponsored(source: ResearchSource) -> bool:
    """Detect social media, sponsored ad content, and low-authority landing pages."""
    url = source.url_or_id.lower()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if any(domain == d or domain.endswith("." + d) for d in LOW_AUTHORITY_DOMAINS):
        return True

    for pat in SPONSORED_PATTERNS:
        if re.search(pat, url):
            return True

    title = source.title.lower()
    if any(flag in title for flag in ["sponsor content", "sponsored post", "advertisement"]):
        return True

    return False


def _compute_relevance_score(source: ResearchSource, query_tokens: set[str]) -> float:
    """Compute lexical domain-relevance score against query keywords."""
    if not query_tokens:
        return 1.0

    text_tokens = set(re.findall(r"\w+", (source.title + " " + source.content).lower()))
    overlap = len(query_tokens & text_tokens)

    base_score = float(overlap)
    if source.source_type == "arxiv":
        base_score += 2.5

    if is_low_authority_or_sponsored(source):
        base_score -= 10.0

    return base_score


def filter_and_rank_sources(
    sources: list[ResearchSource],
    query: str,
    top_k: int = 12,
) -> list[ResearchSource]:
    """
    Filter out low-authority or off-topic sources and rank by domain relevance.
    Ensures the synthesizer receives a clean, prioritized, authoritative source list.
    """
    if not sources:
        return []

    stopwords = {
        "a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "or", "is",
        "are", "was", "were", "what", "how", "why", "which", "where", "with"
    }
    query_tokens = set(re.findall(r"\w+", query.lower())) - stopwords

    scored_sources = []
    for s in sources:
        if is_low_authority_or_sponsored(s) and len(sources) > 5:
            continue

        score = _compute_relevance_score(s, query_tokens)
        scored_sources.append((score, s))

    scored_sources.sort(key=lambda x: x[0], reverse=True)
    ranked = [s for _, s in scored_sources]
    return ranked[:top_k]

