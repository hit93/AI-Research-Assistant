from config.settings import settings
from src.models.schemas import WebSearchResult, ResearchSource
from src.tools.text_cleaner import clean_text
from src.utils.logger import get_logger

logger = get_logger("web_search_tool")

def search_tavily(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Search using Tavily Search API."""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(query=query, max_results=max_results)
        results = []
        for item in response.get("results", []):
            results.append(
                WebSearchResult(
                    title=clean_text(item.get("title", "")),
                    url=item.get("url", ""),
                    snippet=clean_text(item.get("content", "")),
                    score=float(item.get("score", 0.0)),
                )
            )
        logger.info(f"Tavily returned {len(results)} results for '{query}'")
        return results
    except Exception as e:
        logger.warning(f"Tavily search failed or key invalid: {e}. Falling back to DuckDuckGo.")
        return []

def search_duckduckgo(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Fallback search using DuckDuckGo (Free, zero-config)."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        raw_results = list(ddgs.text(keywords=query, max_results=max_results))
        results = []
        for item in raw_results:
            results.append(
                WebSearchResult(
                    title=clean_text(item.get("title", "")),
                    url=item.get("href", ""),
                    snippet=clean_text(item.get("body", "")),
                )
            )
        logger.info(f"DuckDuckGo returned {len(results)} results for '{query}'")
        return results
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []

def search_web(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Unified web search: tries Tavily if key configured, falls back to DuckDuckGo."""
    if not query.strip():
        return []
    
    if settings.TAVILY_API_KEY:
        results = search_tavily(query, max_results=max_results)
        if results:
            return results
            
    return search_duckduckgo(query, max_results=max_results)

def web_results_to_sources(results: list[WebSearchResult]) -> list[ResearchSource]:
    """Convert WebSearchResult items to unified ResearchSource schema."""
    return [
        ResearchSource(
            title=r.title,
            url_or_id=r.url,
            content=r.snippet,
            source_type="web",
        )
        for r in results
    ]
