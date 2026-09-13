"""
LangChain Tool Wrappers — Exposes research tools as standard LangChain Tools.

Can be bound to ChatGroq or used in LangChain agent loops.
"""

from langchain_core.tools import tool
from src.tools.arxiv_tool import search_arxiv
from src.tools.web_search_tool import search_web


@tool
def arxiv_search(query: str, max_results: int = 3) -> str:
    """Search ArXiv for academic research papers by query topic, returning title, authors, summary, and links."""
    papers = search_arxiv(query, max_results=max_results)
    if not papers:
        return f"No papers found on ArXiv for query: '{query}'"
    return "\n\n".join(
        f"Title: {p.title}\nAuthors: {', '.join(p.authors)}\nPublished: {p.published}\nSummary: {p.summary}\nPDF: {p.pdf_url}"
        for p in papers
    )


@tool
def web_search(query: str, max_results: int = 3) -> str:
    """Search the web for current context, articles, and documentation by query topic."""
    results = search_web(query, max_results=max_results)
    if not results:
        return f"No web results found for query: '{query}'"
    return "\n\n".join(
        f"Title: {r.title}\nURL: {r.url}\nSnippet: {r.snippet}"
        for r in results
    )
