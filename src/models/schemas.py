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


# ── Phase 3: Agentic Pipeline Models ──────────────────────────

class SubQuery(BaseModel):
    """A single focused sub-question decomposed from the user's broad query."""
    question: str = Field(description="Focused research sub-question")
    search_keywords: list[str] = Field(default_factory=list, description="Targeted search terms")
    source_type: Literal["arxiv", "web", "both"] = Field(default="both", description="Where to search")


class QueryPlan(BaseModel):
    """The Planner agent's output: the original query broken into sub-queries."""
    original_query: str
    sub_queries: list[SubQuery] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Planner's rationale for the decomposition")


class SynthesisSection(BaseModel):
    """One section of the synthesized research report."""
    heading: str = Field(description="Section heading (e.g., 'Key Findings', 'Research Gaps')")
    content: str = Field(description="Synthesized narrative for this section")
    source_indices: list[int] = Field(default_factory=list, description="Indices into the source list")


class SynthesisReport(BaseModel):
    """Structured report output container for LangChain structured outputs."""
    sections: list[SynthesisSection] = Field(
        default_factory=list,
        description="Synthesized report sections covering findings, gaps, applications, etc.",
    )


class VerificationIssue(BaseModel):
    """A single issue found by the Verify agent during report review."""
    section_heading: str = Field(description="Which synthesis section this issue relates to")
    issue: str = Field(description="Description of the problem found")
    severity: Literal["low", "medium", "high"] = Field(
        default="medium", description="Impact level of the issue"
    )
    suggestion: str = Field(default="", description="How to fix or improve")


class VerificationResult(BaseModel):
    """The Verify agent's verdict on the synthesized report."""
    is_approved: bool = Field(default=True, description="Whether the report passes quality review")
    overall_score: int = Field(default=7, ge=1, le=10, description="Quality score from 1 (poor) to 10 (excellent)")
    issues: list[VerificationIssue] = Field(default_factory=list, description="Specific issues found")
    summary: str = Field(default="", description="Brief overall assessment of the report quality")


class ResearchResult(BaseModel):
    """The final output of a complete research run."""
    query: str
    plan: QueryPlan
    sources: list[ResearchSource] = Field(default_factory=list)
    synthesis: list[SynthesisSection] = Field(default_factory=list)
    verification: VerificationResult | None = None
    duration_seconds: float = 0.0


class ResearchState(BaseModel):
    """Mutable state passed through the orchestrator pipeline."""
    query: str
    plan: QueryPlan | None = None
    sources: list[ResearchSource] = Field(default_factory=list)
    synthesis: list[SynthesisSection] = Field(default_factory=list)
    status: str = "initialized"
    errors: list[str] = Field(default_factory=list)
