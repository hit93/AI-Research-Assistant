import socket
import arxiv
from src.models.schemas import AcademicPaper, ResearchSource
from src.utils.logger import get_logger

logger = get_logger("arxiv_tool")

def search_arxiv(query: str, max_results: int = 5, timeout_seconds: float = 8.0) -> list[AcademicPaper]:
    """Search ArXiv for research papers and return structured metadata with resilient timeout."""
    if not query.strip():
        return []
    
    prev_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_seconds)
    try:
        client = arxiv.Client(page_size=max_results, delay_seconds=0.5, num_retries=1)
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers = []
        for result in client.results(search):
            paper = AcademicPaper(
                title=result.title.replace("\n", " ").strip(),
                authors=[author.name for author in result.authors],
                summary=result.summary.replace("\n", " ").strip(),
                published=result.published.strftime("%Y-%m-%d") if result.published else "",
                arxiv_id=result.entry_id.split("/abs/")[-1],
                pdf_url=result.pdf_url or "",
            )
            papers.append(paper)
        logger.info(f"ArXiv returned {len(papers)} papers for query: '{query}'")
        return papers
    except Exception as e:
        logger.warning(f"ArXiv query timed out or failed for '{query}': {e}")
        return []
    finally:
        socket.setdefaulttimeout(prev_timeout)

def papers_to_sources(papers: list[AcademicPaper]) -> list[ResearchSource]:
    """Convert AcademicPaper items to unified ResearchSource schema."""
    return [
        ResearchSource(
            title=p.title,
            url_or_id=p.pdf_url or f"arxiv:{p.arxiv_id}",
            content=p.summary,
            source_type="arxiv",
            authors=p.authors,
            published=p.published,
        )
        for p in papers
    ]
