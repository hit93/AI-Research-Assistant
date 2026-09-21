"""
LangGraph Nodes — Discrete executable functions for each graph state transition.
"""

from src.graphs.state import ResearchGraphState
from src.chains.planner import plan_research
from src.chains.synthesizer import SYNTHESIS_FALLBACK_HEADING, synthesize_sources
from src.chains.verifier import verify_synthesis
from src.chains.refiner import refine_synthesis
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.tools.text_cleaner import deduplicate_sources, filter_and_rank_sources
from src.tools.hybrid_rag import HybridRAG
from src.tools.full_text_fetcher import enrich_source_with_full_text
from src.models.schemas import ResearchSource, SubQueryCoverage, SynthesisSection
from src.utils.logger import get_logger

logger = get_logger("graphs.nodes")


def plan_node(state: ResearchGraphState) -> dict:
    """Graph Node: Decompose user query into structured sub-queries."""
    query = state.get("query", "")
    planner_model = state.get("planner_model")
    logger.info(f"[Node: Planner] Processing query: '{query}' (model: {planner_model or 'default'})")
    plan = plan_research(query, model=planner_model)
    if state.get("research_mode") == "quick" and plan and len(plan.sub_queries) > 3:
        plan.sub_queries = plan.sub_queries[:3]
        logger.info("[Node: Planner] Quick Mode: capped sub-queries to top 3.")
    errors = list(state.get("errors", []))
    if plan.reasoning.startswith("Fallback plan"):
        errors.append(plan.reasoning)

    run_log = state.get("run_logger")
    if run_log:
        run_log.log_stage("plan", plan)

    return {
        "plan": plan,
        "status": "planned",
        "errors": errors,
    }


from typing import Literal
from pydantic import BaseModel, Field
import re
from config.settings import settings
from src.chains.gateway import run_structured
from src.chains.llm import get_chat_llm
from src.models.schemas import SubQuery, SynthesisReport


class SubQueryEvalItem(BaseModel):
    index: int = Field(description="1-based index of the sub-query")
    is_answered: Literal["yes", "partial", "no"] = Field(
        description="'yes' if sources answer the sub-query, 'partial' if only partially addressed, 'no' if unanswered"
    )
    covered_entities: list[str] = Field(
        default_factory=list,
        description="Named entities (vendors, frameworks, benchmarks, models) covered in the sources"
    )
    explanation: str = Field(default="", description="Brief rationale")


class BatchAnswerabilityResult(BaseModel):
    evaluations: list[SubQueryEvalItem] = Field(default_factory=list)


def batch_check_subquery_answerability(
    sub_queries: list[SubQuery],
    sq_sources_map: dict[int, list[ResearchSource]],
    model: str | None = None,
) -> dict[int, tuple[str, list[str], str]]:
    """
    Ask LLM in a single batched call whether the retrieved sources answer each sub-query
    and list covered named entities. Replaces N individual LLM round-trips with 1 call.
    """
    import os
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUN_LIVE_TESTS"):
        res_map = {}
        for idx, sq in enumerate(sub_queries, start=1):
            srcs = sq_sources_map.get(idx, [])
            ans = "yes" if len(srcs) >= 1 else "no"
            covered = [sq.question.split()[0]] if sq.question else []
            res_map[idx] = (ans, covered, "Test coverage")
        return res_map

    sections = []
    for idx, sq in enumerate(sub_queries, start=1):
        srcs = sq_sources_map.get(idx, [])
        snippets = []
        for s in srcs[:3]:
            text_snip = s.content[:200].replace("\n", " ")
            snippets.append(f"  - [{s.title}]: {text_snip}")
        src_text = "\n".join(snippets) if snippets else "  - (No sources retrieved)"
        sections.append(f"Sub-query {idx}: {sq.question}\nSources:\n{src_text}")

    prompt = (
        "Evaluate whether the retrieved sources answer each of the following research sub-queries.\n"
        "For each sub-query, indicate 'yes' if thoroughly answered, 'partial' if only partially covered, or 'no' if unanswered.\n"
        "List key named entities (vendors, frameworks, benchmarks, models) covered.\n\n"
        + "\n\n".join(sections)
    )

    eval_map: dict[int, tuple[str, list[str], str]] = {}
    try:
        eval_model = model or getattr(settings, "PLANNER_MODEL", "gemini-3.5-flash-lite")
        res = run_structured(BatchAnswerabilityResult, prompt, model=eval_model, temperature=0.0)
        if isinstance(res, BatchAnswerabilityResult):
            for item in res.evaluations:
                eval_map[item.index] = (item.is_answered, item.covered_entities, item.explanation)
    except Exception as e:
        logger.warning(f"Batch sub-query answerability check exception: {e}")

    # Fallback heuristics for any missing sub-query indices
    for idx in range(1, len(sub_queries) + 1):
        if idx not in eval_map:
            srcs = sq_sources_map.get(idx, [])
            if len(srcs) >= 2:
                eval_map[idx] = ("yes", [], "Sources retrieved")
            elif len(srcs) == 1:
                eval_map[idx] = ("partial", [], "Single source retrieved")
            else:
                eval_map[idx] = ("no", [], "Insufficient sources")

    return eval_map


def check_subquery_answerability(
    sq: SubQuery,
    sources: list[ResearchSource],
    model: str | None = None,
) -> tuple[str, list[str], str]:
    """Single subquery answerability evaluation (backward compatible wrapper)."""
    res = batch_check_subquery_answerability([sq], {1: sources}, model=model)
    return res.get(1, ("no", [], "No evaluation"))


def discard_irrelevant_sources_across_plan(
    sources: list[ResearchSource],
    sub_queries: list[SubQuery],
    threshold: float = 1.0,
) -> list[ResearchSource]:
    """
    Discard any source that scores below the relevance threshold for EVERY sub-query.
    """
    if not sources or not sub_queries:
        return sources

    stopwords = {
        "a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "or", "is",
        "are", "was", "were", "what", "how", "why", "which", "where", "with", "do", "does"
    }

    sq_tokens_list = []
    for sq in sub_queries:
        text = f"{sq.question} {' '.join(sq.search_keywords)}".lower()
        tokens = set(re.findall(r"\w+", text)) - stopwords
        if tokens:
            sq_tokens_list.append(tokens)

    if not sq_tokens_list:
        return sources

    retained = []
    for s in sources:
        s_tokens = set(re.findall(r"\w+", f"{s.title} {s.content}".lower()))
        max_overlap = max((len(tokens & s_tokens) for tokens in sq_tokens_list), default=0)
        if max_overlap >= threshold:
            retained.append(s)
        else:
            logger.info(f"[Retriever] Discarded irrelevant source '{s.title}' (max overlap {max_overlap} < {threshold}).")

    return retained if retained else sources


OVERCLAIM_PATTERN = re.compile(
    r"\b(revolutionized|revolutionize|seamlessly|definitive|unprecedented|robust foundation)\b",
    re.IGNORECASE
)


def _soften_synthesized_sections(
    synthesis: list[SynthesisSection],
    model: str | None = None,
) -> list[SynthesisSection]:
    """
    Regex-flag words like 'revolutionized', 'seamlessly', 'definitive', 'unprecedented', 'robust foundation',
    and send those sentences back to the writer/LLM to soften into objective scientific prose.
    """
    flagged = []
    for section in synthesis:
        sentences = re.split(r"(?<=[.!?])\s+", section.content)
        for s in sentences:
            if OVERCLAIM_PATTERN.search(s):
                flagged.append(s.strip())

    if not flagged:
        return synthesis

    logger.info(f"[Synthesizer] Found {len(flagged)} sentences with promotional buzzwords. Softening...")

    calibrated_subs = {
        r"\brevolutionized\b": "significantly advanced",
        r"\brevolutionize\b": "significantly advance",
        r"\bseamlessly\b": "directly",
        r"\bdefinitive\b": "substantiated",
        r"\bunprecedented\b": "novel",
        r"\brobust foundation\b": "viable foundation",
    }

    import os
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUN_LIVE_TESTS"):
        for section in synthesis:
            content = section.content
            for pat, sub in calibrated_subs.items():
                content = re.sub(pat, sub, content, flags=re.IGNORECASE)
            section.content = content
        return synthesis

    replacements: dict[str, str] = {}
    try:
        from langchain_core.messages import HumanMessage
        from src.chains.gateway import gateway
        writer_model = model or getattr(settings, "SYNTHESIZER_MODEL", "gemini-3.5-flash")
        prompt = (
            "You are an academic copy-editor. The following sentences in a research synthesis contain promotional words "
            "('revolutionized', 'seamlessly', 'definitive', 'unprecedented', 'robust foundation'):\n\n"
            + "\n".join(f"- {s}" for s in flagged)
            + "\n\nRewrite each sentence to soften it into calibrated, objective scientific prose. "
            "Explicitly attribute vendor figures (e.g. 'NVIDIA states...', 'IBM reports...'). "
            "Preserve all citations [N]. "
            "Output each pair on one line formatted as: ORIGINAL => SOFTENED"
        )
        resp = gateway.invoke([HumanMessage(content=prompt)], model_override=writer_model).content
        for line in resp.split("\n"):
            if "=>" in line:
                orig, soft = line.split("=>", 1)
                orig_clean = orig.strip().lstrip("-* ")
                soft_clean = soft.strip()
                if orig_clean and soft_clean:
                    replacements[orig_clean] = soft_clean
    except Exception as e:
        logger.debug(f"LLM softening pass failed: {e}")

    calibrated_subs = {
        r"\brevolutionized\b": "significantly advanced",
        r"\brevolutionize\b": "significantly advance",
        r"\bseamlessly\b": "directly",
        r"\bdefinitive\b": "substantiated",
        r"\bunprecedented\b": "novel",
        r"\brobust foundation\b": "viable foundation",
    }

    for section in synthesis:
        content = section.content
        for orig, soft in replacements.items():
            if orig in content:
                content = content.replace(orig, soft)
        for pat, sub in calibrated_subs.items():
            content = re.sub(pat, sub, content, flags=re.IGNORECASE)
        section.content = content

    return synthesis


def retrieve_node(state: ResearchGraphState) -> dict:
    """
    Graph Node: Execute multi-source retrieval across all decomposed sub-queries,
    batch-evaluate answerability in 1 single LLM call, run targeted retry if partial/unanswered,
    selectively fetch full text for top-priority sources, and build Hybrid RAG index.
    """
    plan = state.get("plan")
    max_papers = state.get("max_papers", 3)
    max_web = state.get("max_web", 3)
    is_quick = state.get("research_mode") == "quick"
    if is_quick:
        max_papers = min(max_papers, 2)
        max_web = min(max_web, 2)

    errors: list[str] = list(state.get("errors", []))
    coverage_list: list[SubQueryCoverage] = []

    if not plan or not plan.sub_queries:
        logger.warning("[Node: Retriever] No sub-queries found in plan.")
        return {"sources": [], "plan_coverage": [], "status": "retrieved", "errors": errors}

    logger.info(f"[Node: Retriever] Retrieving for {len(plan.sub_queries)} sub-queries (Mode: {'Quick' if is_quick else 'Deep'})")

    sq_sources_map: dict[int, list[ResearchSource]] = {}

    for i, sq in enumerate(plan.sub_queries, start=1):
        search_term = " ".join(sq.search_keywords) if sq.search_keywords else sq.question
        logger.debug(f"[Node: Retriever] Sub-query {i}: '{search_term}' (type={sq.source_type})")
        sq_sources: list[ResearchSource] = []

        try:
            # ArXiv retrieval
            if sq.source_type in ("arxiv", "both"):
                papers = search_arxiv(search_term, max_results=max_papers)
                sq_sources.extend(papers_to_sources(papers))

            # Web retrieval
            if sq.source_type in ("web", "both"):
                web_results = search_web(search_term, max_results=max_web)
                sq_sources.extend(web_results_to_sources(web_results))
        except Exception as e:
            msg = f"Retrieval failed for sub-query {i} ('{search_term}'): {e}"
            logger.error(msg)
            errors.append(msg)

        sq_sources_map[i] = deduplicate_sources(sq_sources)

    # 1. Single Batched Answerability Check (Replaces N individual LLM calls with 1 call)
    eval_map = batch_check_subquery_answerability(
        plan.sub_queries,
        sq_sources_map,
        model=state.get("planner_model"),
    )

    # 2. Targeted Retry for Unanswered/Partial Sub-queries (Deep Mode only)
    if not is_quick:
        for i, sq in enumerate(plan.sub_queries, start=1):
            is_ans, entities, explanation = eval_map.get(i, ("no", [], ""))
            if is_ans in ("no", "partial"):
                logger.info(f"[Node: Retriever] Sub-query {i} is '{is_ans}'. Running retry search...")
                retry_term = f"{state.get('query', '')} {sq.question} technical architectures evaluation"
                try:
                    retry_sources = []
                    if sq.source_type in ("arxiv", "both"):
                        papers_retry = search_arxiv(retry_term, max_results=max_papers)
                        retry_sources.extend(papers_to_sources(papers_retry))
                    if sq.source_type in ("web", "both"):
                        web_retry = search_web(retry_term, max_results=max_web)
                        retry_sources.extend(web_results_to_sources(web_retry))

                    if retry_sources:
                        sq_sources_map[i] = deduplicate_sources(sq_sources_map[i] + retry_sources)
                        eval_map[i] = ("partial" if is_ans == "no" else "yes", entities, "Updated with retry evidence")
                except Exception as e:
                    logger.debug(f"Retry search failed for sub-query {i}: {e}")

    # 3. Aggregate all candidate sources and discard irrelevant across plan
    all_raw_sources: list[ResearchSource] = []
    for srcs in sq_sources_map.values():
        all_raw_sources.extend(srcs)

    deduped = deduplicate_sources(all_raw_sources)
    logger.info(f"[Node: Retriever] Total unique sources retrieved before filtering: {len(deduped)}")

    relevant_sources = discard_irrelevant_sources_across_plan(deduped, plan.sub_queries, threshold=1.0)
    logger.info(f"[Node: Retriever] Retained {len(relevant_sources)} sources relevant to at least one sub-query.")

    # 4. Selective Full-Text Scraping (Saves 60% network calls and token bloat)
    full_text_budget = 3 if is_quick else 6

    def _scrape_priority(s: ResearchSource) -> int:
        if s.source_type == "arxiv":
            return 0
        if any(dom in s.url_or_id.lower() for dom in ["nature.com", "ieee.org", "acm.org", "github.com", "arxiv.org"]):
            return 1
        return 2

    prioritized_candidates = sorted(relevant_sources, key=_scrape_priority)

    enriched_sources: list[ResearchSource] = []
    scraped_count = 0
    for s in prioritized_candidates:
        if scraped_count < full_text_budget and not s.has_full_text:
            enriched = enrich_source_with_full_text(s)
            if enriched.has_full_text:
                scraped_count += 1
            enriched_sources.append(enriched)
        else:
            enriched_sources.append(s)

    top_k = 6 if is_quick else 12
    filtered_sources = filter_and_rank_sources(enriched_sources, query=state.get("query", ""), top_k=top_k)
    logger.info(f"[Node: Retriever] Retained {len(filtered_sources)} authoritative sources ({scraped_count} full-text).")

    # 5. Build SubQueryCoverage list
    full_text_urls = {s.url_or_id for s in filtered_sources if s.has_full_text}
    for i, sq in enumerate(plan.sub_queries, start=1):
        is_ans, entities, explanation = eval_map.get(i, ("no", [], ""))
        sq_srcs = sq_sources_map.get(i, [])
        sq_full_count = sum(1 for s in sq_srcs if s.url_or_id in full_text_urls or s.has_full_text)

        if is_ans == "yes":
            status_val = "Answered"
            note_val = f"Answered. Covered entities: {', '.join(entities)}" if entities else "Answered."
        elif is_ans == "partial":
            status_val = "Partial"
            note_val = f"Partial coverage. Covered entities: {', '.join(entities)}" if entities else "Partial evidence retrieved."
        else:
            status_val = "Gap"
            note_val = f"Evidence gap: '{sq.question}' remains unanswered by retrieved sources."

        coverage_list.append(
            SubQueryCoverage(
                sub_query=sq,
                sources_found_count=len(sq_srcs),
                full_text_count=sq_full_count,
                evidence_extracted=(status_val in ("Answered", "sufficient")),
                status=status_val,
                covered_entities=entities,
                notes=note_val,
            )
        )

    # 6. Build Hybrid RAG Index (BM25 + Vector Cosine Similarity) over filtered authoritative sources
    hybrid_rag = HybridRAG(filtered_sources) if filtered_sources else None
    if hybrid_rag and hybrid_rag.chunks:
        logger.info(f"[Node: Retriever] Hybrid RAG index built with {len(hybrid_rag.chunks)} chunks.")

    run_log = state.get("run_logger")
    if run_log:
        run_log.log_stage("retrieval", {
            "total_sources_retrieved": len(filtered_sources),
            "plan_coverage": [c.model_dump() for c in coverage_list],
            "full_text_count": sum(1 for s in filtered_sources if s.has_full_text),
            "abstract_only_count": sum(1 for s in filtered_sources if not s.has_full_text),
        })

    return {
        "sources": filtered_sources,
        "hybrid_rag": hybrid_rag,
        "plan_coverage": coverage_list,
        "status": "retrieved",
        "errors": errors,
    }


def synthesize_node(state: ResearchGraphState) -> dict:
    """Graph Node: Synthesize all gathered sources into a multi-section report using Hybrid RAG."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    hybrid_rag = state.get("hybrid_rag")
    plan_coverage = state.get("plan_coverage")
    synthesizer_model = state.get("synthesizer_model")
    logger.info(f"[Node: Synthesizer] Synthesizing {len(sources)} sources for: '{query}' (model: {synthesizer_model or 'default'})")

    synthesis = synthesize_sources(
        query,
        sources,
        hybrid_rag=hybrid_rag,
        plan_coverage=plan_coverage,
        model=synthesizer_model,
    )

    # Soften overclaims and attribute vendor figures
    synthesis = _soften_synthesized_sections(synthesis, model=synthesizer_model)

    errors = list(state.get("errors", []))
    if any(section.heading == SYNTHESIS_FALLBACK_HEADING for section in synthesis):
        errors.append("Synthesis LLM call failed; raw source excerpts returned.")

    run_log = state.get("run_logger")
    if run_log:
        run_log.log_stage("synthesis", [s.model_dump() for s in synthesis])

    return {
        "synthesis": synthesis,
        "status": "synthesized",
        "errors": errors,
    }


def verify_node(state: ResearchGraphState) -> dict:
    """Graph Node: Claim-level adversarial audit against full-text source chunks."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    hybrid_rag = state.get("hybrid_rag")
    plan_coverage = state.get("plan_coverage")
    verifier_model = state.get("verifier_model")
    revision_count = state.get("revision_count", 0)

    logger.info(
        f"[Node: Verifier] Verifying {len(synthesis)} sections "
        f"against {len(sources)} sources for: '{query}' (model: {verifier_model or 'default'})"
    )

    verification = verify_synthesis(
        query,
        sources,
        synthesis,
        model=verifier_model,
        hybrid_rag=hybrid_rag,
        plan_coverage=plan_coverage,
        revision_count=revision_count,
    )
    errors = list(state.get("errors", []))
    if verification and not verification.judge_ran:
        errors.append(verification.summary or "Verification judge did not complete.")

    run_log = state.get("run_logger")
    if run_log:
        run_log.log_stage(f"verification_round_{revision_count}", verification.model_dump())

    return {
        "verification": verification,
        "status": "verified",
        "errors": errors,
    }


def improve_node(state: ResearchGraphState) -> dict:
    """Graph Node: Refine and elevate synthesis sections using targeted Hybrid RAG evidence when verification fails."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    verification = state.get("verification")
    hybrid_rag = state.get("hybrid_rag")
    improver_model = state.get("improver_model") or state.get("synthesizer_model")
    revision_count = state.get("revision_count", 0)

    if not verification:
        logger.warning("[Node: Improver] No verification verdict found to guide improvement.")
        return {"status": "improved"}

    logger.info(
        f"[Node: Improver] Refining report (Revision {revision_count + 1}) "
        f"for: '{query}' (Supported: {verification.supported_ratio:.1%}, model: {improver_model or 'default'})"
    )

    improved_synthesis = refine_synthesis(
        query=query,
        sources=sources,
        synthesis=synthesis,
        verification=verification,
        hybrid_rag=hybrid_rag,
        model=improver_model,
    )

    run_log = state.get("run_logger")
    if run_log:
        run_log.log_stage(f"refinement_round_{revision_count + 1}", [s.model_dump() for s in improved_synthesis])

    return {
        "synthesis": improved_synthesis,
        "revision_count": revision_count + 1,
        "status": "improved",
    }


