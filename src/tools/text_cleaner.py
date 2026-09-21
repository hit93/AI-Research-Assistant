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
    """Compute lexical domain-relevance score with tiering, full-text, and recency bonuses."""
    if not query_tokens:
        return 1.0

    text_to_check = (source.title + " " + (source.full_text[:3000] if source.has_full_text else source.content)).lower()
    text_tokens = set(re.findall(r"\w+", text_to_check))
    overlap = len(query_tokens & text_tokens)

    base_score = float(overlap)

    # Source tier ranking: tier 1 (primary/paper/standards/tech blogs) > tier 2 > tier 3 (aggregators)
    tier = getattr(source, "source_tier", 2)
    if tier == 1:
        base_score += 3.0
    elif tier == 3:
        base_score -= 2.0  # Wikipedia relegated to background

    # Full-text availability bonus
    if getattr(source, "has_full_text", False):
        base_score += 2.0

    # Recency bonus for fast-moving topics (recent years get boost)
    pub = (getattr(source, "published", "") or getattr(source, "published_date", "")).strip()
    if pub:
        for year in ["2026", "2025", "2024"]:
            if year in pub:
                base_score += 1.5
                break

    if is_low_authority_or_sponsored(source):
        base_score -= 10.0

    return base_score


def filter_and_rank_sources(
    sources: list[ResearchSource],
    query: str,
    top_k: int = 12,
) -> list[ResearchSource]:
    """
    Filter out low-authority sources, rank by domain relevance, quality tier, and recency,
    and enforce source diversity (capping any single source type to guarantee a balanced mix).
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

    # Diversity enforcement: cap any single source type (max 70% of top_k)
    max_per_type = max(1, int(top_k * 0.70))
    wiki_count = 0
    type_counts: dict[str, int] = {}
    ranked: list[ResearchSource] = []

    # First pass: authoritative and diverse
    for _, s in scored_sources:
        stype = s.source_type
        # Cap Wikipedia to at most 1 (background only)
        if "wikipedia.org" in s.url_or_id.lower():
            if wiki_count >= 1:
                continue
            wiki_count += 1

        if type_counts.get(stype, 0) < max_per_type:
            ranked.append(s)
            type_counts[stype] = type_counts.get(stype, 0) + 1
            if len(ranked) >= top_k:
                break

    # Second pass: fill remaining slots if needed
    if len(ranked) < top_k:
        for _, s in scored_sources:
            if s not in ranked:
                if "wikipedia.org" in s.url_or_id.lower() and wiki_count >= 1:
                    continue
                ranked.append(s)
                if len(ranked) >= top_k:
                    break

    return ranked


