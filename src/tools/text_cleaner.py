import re
from bs4 import BeautifulSoup
from src.models.schemas import ResearchSource

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
        key = (s.url_or_id.strip().lower(), s.title.strip().lower())
        if key not in seen_ids and s.url_or_id.strip() not in seen_ids:
            seen_ids.add(key)
            seen_ids.add(s.url_or_id.strip())
            unique.append(s)
    return unique
