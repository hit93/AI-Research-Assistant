from src.tools.text_cleaner import clean_text, deduplicate_sources
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.models.schemas import AcademicPaper, WebSearchResult, ResearchSource

def test_clean_text():
    dirty_html = "<div><p>Hello   World!</p><br/><span>AI Research</span></div>"
    cleaned = clean_text(dirty_html)
    assert cleaned == "Hello World! AI Research"
    assert clean_text("") == ""

def test_deduplicate_sources():
    sources = [
        ResearchSource(title="Paper A", url_or_id="https://arxiv.org/abs/1", content="Intro", source_type="arxiv"),
        ResearchSource(title="Paper A", url_or_id="https://arxiv.org/abs/1", content="Duplicate", source_type="arxiv"),
        ResearchSource(title="Paper B", url_or_id="https://arxiv.org/abs/2", content="Content", source_type="arxiv"),
    ]
    unique = deduplicate_sources(sources)
    assert len(unique) == 2
    assert unique[0].title == "Paper A"
    assert unique[1].title == "Paper B"

def test_arxiv_search():
    results = search_arxiv(query="Transformers in Deep Learning", max_results=2)
    assert isinstance(results, list)
    if results:
        paper = results[0]
        assert isinstance(paper, AcademicPaper)
        assert len(paper.title) > 0
        assert len(paper.summary) > 0
        assert len(paper.arxiv_id) > 0
        
        # Test conversion to unified ResearchSource
        sources = papers_to_sources(results)
        assert len(sources) == len(results)
        assert sources[0].source_type == "arxiv"

def test_web_search():
    results = search_web(query="machine learning tutorial", max_results=2)
    assert isinstance(results, list)
    if results:
        item = results[0]
        assert isinstance(item, WebSearchResult)
        assert len(item.title) > 0
        assert item.url.startswith("http")
        
        # Test conversion to unified ResearchSource
        sources = web_results_to_sources(results)
        assert len(sources) == len(results)
        assert sources[0].source_type == "web"

def test_empty_query_resilience():
    assert search_arxiv("") == []
    assert search_web("") == []

if __name__ == "__main__":
    test_clean_text()
    test_deduplicate_sources()
    test_empty_query_resilience()
    print("Running live network tests for Checkpoint 2...")
    test_arxiv_search()
    test_web_search()
    print("All Phase 2 retrieval tool tests passed successfully!")
