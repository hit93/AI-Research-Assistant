from typing import Literal
from pydantic import BaseModel, Field

class AcademicPaper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    summary: str
    published: str
    arxiv_id: str
    pdf_url: str

class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float = 0.0

class ResearchSource(BaseModel):
    title: str
    url_or_id: str
    content: str
    source_type: Literal["arxiv", "web"]
    authors: list[str] = Field(default_factory=list)
    published: str = ""
