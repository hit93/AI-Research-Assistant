from typing import TypedDict, Any

class ResearchState(TypedDict, total=False):
    topic: str
    sub_questions: list[str]
    sources: list[dict[str, Any]]
    report: str
    errors: list[str]
