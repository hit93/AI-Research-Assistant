from pathlib import Path
import streamlit as st
from config.settings import settings
from src.tools import (
    search_arxiv,
    papers_to_sources,
    search_web,
    web_results_to_sources,
    deduplicate_sources,
)
from src.agents import run_research
from src.utils import (
    export_to_markdown,
    export_to_pdf,
    export_to_json,
    save_report,
    _extract_mermaid_blocks,
)
from src.memory.ltm import get_ltm


st.set_page_config(
    page_title="AI Research Assistant",
    page_icon="🔬",
    layout="wide",
)

# Custom Styling
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #8b949e;
        margin-bottom: 1.5rem;
    }
    .source-card {
        padding: 1.2rem;
        border-radius: 8px;
        background-color: #161b22;
        border: 1px solid #30363d;
        margin-bottom: 1rem;
    }
    .synthesis-section {
        padding: 1rem;
        border-left: 3px solid #58a6ff;
        margin-bottom: 1rem;
        background-color: rgba(88, 166, 255, 0.05);
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">🔬 AI Research Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Phase 4: Resilient LLM Gateway, Layered Memory & Semantic Caching</div>', unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_available_models() -> list[str]:
    """Fetch available models from Google AI Studio and Groq API."""
    gemini_models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
    ]
    groq_models = [
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
    ]

    if settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            live_models = [
                m.id for m in client.models.list().data
                if not any(sub in m.id for sub in ("whisper", "guard", "safeguard", "vision", "orpheus"))
            ]
            preferred = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "groq/compound", "groq/compound-mini"]
            models_set = set(live_models)
            ordered_list = [m for m in preferred if m in models_set]
            remainder = sorted(list(models_set - set(ordered_list)))
            groq_models = ordered_list + remainder
        except Exception:
            pass

    # If user has Gemini key configured, prioritize Gemini models at the top
    if settings.GEMINI_API_KEY:
        return gemini_models + groq_models
    return groq_models + gemini_models


# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=64)
    st.title("Research Engine")
    
    # Environment Status
    keys = settings.validate_keys()
    st.markdown("### 🔑 API Status")
    if keys.get("gemini"):
        st.success("Google AI Studio: Connected")
    else:
        st.info("Google AI Studio: Not Set (Add GEMINI_API_KEY to .env)")

    if keys["groq"]:
        st.success("Groq API: Connected")
    else:
        st.error("Groq API: Missing — Add GROQ_API_KEY to .env")

    if keys["tavily"]:
        st.success("Tavily API: Connected (Primary Web)")
    else:
        st.info("Tavily API: Not Set (Using DuckDuckGo Fallback)")

    if keys.get("langsmith"):
        st.success("LangSmith: Connected (Tracing Active)")
    elif keys.get("langsmith_configured"):
        st.warning(f"LangSmith: {keys.get('langsmith_msg', 'Invalid Key')} — Tracing Auto-Disabled")
    else:
        st.caption("LangSmith: Disabled")

    st.divider()

    # 🤖 Model Selection (Per Agent)
    st.subheader("🤖 Model Selection (Per Agent)")
    available_models = fetch_available_models()

    planner_default = next(
        (m for m in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"] if m in available_models and settings.GEMINI_API_KEY),
        next((m for m in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"] if m in available_models), available_models[0])
    )
    planner_def_idx = available_models.index(planner_default) if planner_default in available_models else 0
    selected_planner_model = st.selectbox(
        "🧠 Planner Agent",
        available_models,
        index=planner_def_idx,
        help="Decomposes research topic into targeted academic and web sub-queries.",
    )

    synth_default = next(
        (m for m in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"] if m in available_models and settings.GEMINI_API_KEY),
        next((m for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"] if m in available_models), available_models[0])
    )
    synth_def_idx = available_models.index(synth_default) if synth_default in available_models else 0
    selected_synth_model = st.selectbox(
        "⚗️ Synthesizer Agent",
        available_models,
        index=synth_def_idx,
        help="Generates comprehensive, multi-paragraph research findings grounded in RAG passages.",
    )

    verifier_default = next(
        (m for m in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"] if m in available_models and settings.GEMINI_API_KEY),
        next((m for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"] if m in available_models), available_models[0])
    )
    verifier_def_idx = available_models.index(verifier_default) if verifier_default in available_models else 0
    selected_verifier_model = st.selectbox(
        "⚖️ Verifier (Judge) Agent",
        available_models,
        index=verifier_def_idx,
        help="Independent LLM-as-judge that audits claims, checks citations, and assigns the quality score.",
    )

    improver_default = next(
        (m for m in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"] if m in available_models and settings.GEMINI_API_KEY),
        next((m for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"] if m in available_models), available_models[0])
    )
    improver_def_idx = available_models.index(improver_default) if improver_default in available_models else 0
    selected_improver_model = st.selectbox(
        "🛠️ Refiner / Improver Agent",
        available_models,
        index=improver_def_idx,
        help="Iteratively rewrites and elevates report sections when score is below 8/10.",
    )

    st.divider()

    st.subheader("⚡ Memory & Gateway (Phase 4)")
    st.caption(f"🛡️ **Fallback Model:** `{settings.FALLBACK_MODEL}`")
    st.caption(f"⚡ **Semantic Cache:** `{'Active' if settings.SEMANTIC_CACHE_ENABLED else 'Disabled'}`")
    st.caption(f"🧠 **STM / LTM:** `Redis & SQLite Active`")

    st.divider()
    st.subheader("⚡ Research Depth")
    depth_choice = st.radio(
        "Execution Mode",
        ["⚡ Quick Briefing (~15s, Lean)", "🔬 Deep Academic (Full Audit, ~60s)"],
        index=0,
        help="⚡ Quick Briefing: 3 targeted sub-queries, top 3 full-text sources, 1 fast verification pass (conserves API calls).\n🔬 Deep Academic: 5-7 sub-queries, selective full-text scraping, retry passes, multi-round claim audit."
    )
    is_quick_mode = "Quick" in depth_choice
    selected_research_mode = "quick" if is_quick_mode else "deep"

    st.divider()
    st.subheader("Search Parameters")
    def_papers = 2 if is_quick_mode else 3
    def_web = 2 if is_quick_mode else 3
    arxiv_max = st.slider("Max ArXiv Papers (per sub-query)", min_value=1, max_value=10, value=def_papers)
    web_max = st.slider("Max Web Results (per sub-query)", min_value=1, max_value=10, value=def_web)
    
    st.divider()

    # Mode selector
    mode = st.radio(
        "Research Mode",
        ["🧠 Full Research (LLM Pipeline)", "🔧 Tools Explorer (Manual)"],
        index=0,
    )
    
    st.divider()
    st.caption("Roadmap Status: Phase 4 (Gateway, Memory & Evaluation)")


# Main Query Input
col_input, col_btn = st.columns([5, 1])
with col_input:
    query = st.text_input(
        "Research Topic / Question",
        placeholder="e.g. Multi-Agent Systems in Healthcare or Quantum Computing in Drug Discovery",
        label_visibility="collapsed",
    )
with col_btn:
    search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# MODE 1: Full LLM Research Pipeline
# ═══════════════════════════════════════════════════════════════
if "🧠" in mode:
    has_cached = (
        "last_research_result" in st.session_state
        and st.session_state.get("last_full_query") == query
        and query.strip()
    )
    if search_clicked or has_cached:
        if not query.strip():
            st.warning("Please enter a search topic first.")
        elif not (keys.get("gemini") or keys["groq"]):
            st.error("🔑 A Gemini or Groq API key is required. Add `GEMINI_API_KEY` or `GROQ_API_KEY` to your `.env` file.")
        else:
            if search_clicked or not has_cached:
                st.session_state.last_full_query = query

                # Progress display
                progress_container = st.empty()
                progress_messages = []

                def on_progress(status: str, detail: str):
                    icons = {
                        "planning": "🧠",
                        "planned": "✅",
                        "retrieving": "🔍",
                        "retrieved": "📦",
                        "deduplicated": "🧹",
                        "synthesizing": "⚗️",
                        "synthesized": "✅",
                        "verifying": "🔎",
                        "verified": "✅",
                        "improving": "🛠️",
                        "improved": "✨",
                        "complete": "🏁",
                    }
                    icon = icons.get(status, "▸")
                    progress_messages.append(f"{icon} **{status.upper()}**: {detail}")
                    progress_container.markdown("\n\n".join(progress_messages))

                with st.spinner("Running full research pipeline..."):
                    result = run_research(
                        query=query,
                        max_papers=arxiv_max,
                        max_web=web_max,
                        on_progress=on_progress,
                        planner_model=selected_planner_model,
                        synthesizer_model=selected_synth_model,
                        verifier_model=selected_verifier_model,
                        improver_model=selected_improver_model,
                        research_mode=selected_research_mode,
                    )

                progress_container.empty()
                st.session_state.last_research_result = result
                st.session_state.saved_reports = save_report(result)
            else:
                result = st.session_state.last_research_result
                if "saved_reports" not in st.session_state:
                    st.session_state.saved_reports = save_report(result)

            # Cache Hit Banner
            if getattr(result, "is_cache_hit", False):
                st.info("⚡ **Served from Semantic Cache:** Query matched past research run. Bypassed search & LLM generation.")

            # Success banner
            score_info = ""
            if result.verification:
                score_info = f", Score: {result.verification.overall_score}/10"
            st.success(
                f"✅ Research complete in **{result.duration_seconds}s** — "
                f"{len(result.sources)} sources, {len(result.synthesis)} sections{score_info}"
            )
            if getattr(result, "errors", None):
                st.error("Pipeline errors were recorded; see Verification for the approval status.")
                with st.expander("Pipeline errors"):
                    for err in result.errors:
                        st.write(f"- {err}")


            # ── Multi-Format Report Export & Download Row ────────
            saved_paths = st.session_state.saved_reports
            pdf_filename = saved_paths.get("pdf", Path("report.pdf")).name
            md_filename = saved_paths.get("md", Path("report.md")).name
            json_filename = saved_paths.get("json", Path("report.json")).name

            col_pdf, col_md, col_json, col_info = st.columns([1.2, 1.4, 1.2, 2.2])
            with col_pdf:
                pdf_bytes = export_to_pdf(result)
                st.download_button(
                    label="📄 Download PDF",
                    data=pdf_bytes,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    use_container_width=True,
                )
            with col_md:
                md_content = export_to_markdown(result)
                st.download_button(
                    label="📝 Download Markdown",
                    data=md_content,
                    file_name=md_filename,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_json:
                json_content = export_to_json(result)
                st.download_button(
                    label="📊 Download JSON",
                    data=json_content,
                    file_name=json_filename,
                    mime="application/json",
                    use_container_width=True,
                )
            with col_info:
                st.caption(f"💾 *Auto-saved to `data/reports/{pdf_filename}`*")

            # Tabs for results
            tab_report, tab_plan, tab_sources, tab_verify, tab_history = st.tabs([
                "📝 Research Report",
                f"📋 Query Plan ({len(result.plan.sub_queries)} sub-queries)",
                f"📚 Sources ({len(result.sources)})",
                "✅ Verification Report",
                "🏛️ Memory History (LTM)",
            ])


            # ── Research Report Tab ───────────────────────────────────
            with tab_report:
                # Table of Contents expander at the top
                with st.expander("📑 Table of Contents", expanded=True):
                    for i, section in enumerate(result.synthesis, 1):
                        st.caption(f"{i}. {section.heading}")

                st.divider()

                for sec_idx, section in enumerate(result.synthesis, 1):
                    # Section header with blue left-border accent
                    st.markdown(
                        f"""<div style="border-left: 4px solid #2563eb; padding-left: 12px;
                        margin-bottom: 6px; margin-top: 12px;">
                        <h3 style="margin: 0; color: #0f172a;">
                            {sec_idx}. {section.heading}
                        </h3></div>""",
                        unsafe_allow_html=True,
                    )

                    # Extract Mermaid blocks from section content
                    mermaid_blocks = _extract_mermaid_blocks(section.content)

                    if mermaid_blocks:
                        for pre_text, mermaid_src, post_text in mermaid_blocks:
                            if pre_text.strip():
                                st.markdown(pre_text)
                            inner_src = mermaid_src
                            inner_src = inner_src.replace("```mermaid", "").replace("```", "").strip()
                            with st.expander("🔷 Architecture / Flow Diagram (Mermaid)", expanded=False):
                                st.code(inner_src, language="mermaid")
                                st.caption(
                                    "💡 Copy this code into "
                                    "[mermaid.live](https://mermaid.live) to render interactively."
                                )
                            if post_text.strip():
                                st.markdown(post_text)
                    else:
                        st.markdown(section.content)

                    # Referenced sources
                    if section.source_indices:
                        refs = []
                        for idx in section.source_indices:
                            if 0 <= idx < len(result.sources):
                                s = result.sources[idx]
                                refs.append(f"[{idx}] *{s.title}*")
                        if refs:
                            with st.expander("📎 Referenced Sources"):
                                for ref in refs:
                                    st.caption(ref)

                    st.divider()

            # ── Query Plan Tab ────────────────────────────────
            with tab_plan:
                if result.plan.reasoning:
                    st.info(f"**Strategy:** {result.plan.reasoning}")
                for i, sq in enumerate(result.plan.sub_queries, 1):
                    with st.container():
                        st.markdown(f"**{i}. {sq.question}**")
                        st.caption(
                            f"🔑 Keywords: {', '.join(sq.search_keywords)} | "
                            f"📂 Source: `{sq.source_type}`"
                        )
                        st.divider()

            # ── Sources Tab ───────────────────────────────────
            with tab_sources:
                for idx, source in enumerate(result.sources):
                    badge = "📘 ArXiv" if source.source_type == "arxiv" else "🌐 Web"
                    with st.container():
                        st.markdown(f"**[{idx}] {badge} — {source.title}**")
                        st.caption(f"Source: `{source.url_or_id}`")
                        if source.authors:
                            st.caption(f"Authors: {', '.join(source.authors)}")
                        with st.expander("View content"):
                            st.write(source.content)
                        st.divider()

            # ── Verification Report Tab ──────────────────────
            with tab_verify:
                if result.verification:
                    v = result.verification

                    # Score and approval banner
                    col_score, col_status = st.columns(2)
                    with col_score:
                        st.metric("Quality Score", f"{v.overall_score}/10")
                    with col_status:
                        if v.is_approved:
                            st.success("✅ Report Approved")
                        else:
                            st.warning("⚠️ Report Flagged for Review")

                    # Summary
                    st.markdown(f"**Assessment:** {v.summary}")

                    # Issues
                    if v.issues:
                        st.markdown(f"### Issues Found ({len(v.issues)})")
                        for issue in v.issues:
                            severity_colors = {
                                "low": "🟢", "medium": "🟡", "high": "🔴"
                            }
                            icon = severity_colors.get(issue.severity, "⚪")
                            with st.container():
                                st.markdown(
                                    f"{icon} **[{issue.severity.upper()}]** "
                                    f"*{issue.section_heading}*: {issue.issue}"
                                )
                                if issue.suggestion:
                                    st.caption(f"💡 Suggestion: {issue.suggestion}")
                                st.divider()
                    else:
                        st.info("✨ No issues found — the report passed verification cleanly.")
                else:
                    st.info("Verification was not performed for this research run.")

            # ── Long-Term Memory (LTM) Tab ───────────────────
            with tab_history:
                st.markdown("### 🏛️ Long-Term Memory (LTM) Archive")
                st.caption("Past research runs stored in SQLite / pgvector database (`data/cache/ltm.db`).")
                history = get_ltm().get_history(limit=10)
                if history:
                    for h in history:
                        col1, col2, col3 = st.columns([4, 1.2, 1.2])
                        with col1:
                            st.markdown(f"**{h['topic']}**")
                            if h.get("synthesis_summary"):
                                st.caption(h["synthesis_summary"][:150] + "...")
                        with col2:
                            score = h.get("score")
                            st.metric("Score", f"{score}/10" if score else "N/A")
                        with col3:
                            approved = h.get("approved")
                            st.caption("✅ Approved" if approved else "⚠️ Flagged")
                        st.divider()
                else:
                    st.info("No past research runs recorded in LTM yet.")

    else:
        st.info("💡 Enter a research topic above and click **Search** to run the full LLM research pipeline.")

        # Show recent LTM records on homepage
        history = get_ltm().get_history(limit=5)
        if history:
            with st.expander(f"📚 Recent Research Archive ({len(history)} past topics saved in LTM)"):
                for h in history:
                    st.markdown(f"• **{h['topic']}** (Score: `{h.get('score', 'N/A')}/10`)")



# ═══════════════════════════════════════════════════════════════
# MODE 2: Manual Tools Explorer (original Phase 2 UI)
# ═══════════════════════════════════════════════════════════════
else:
    if search_clicked or query:
        if not query.strip():
            st.warning("Please enter a search topic first.")
        else:
            with st.spinner("Querying research tools..."):
                # Execute retrievals
                arxiv_results = search_arxiv(query, max_results=arxiv_max)
                web_results = search_web(query, max_results=web_max)

                # Convert to unified schema & deduplicate
                arxiv_sources = papers_to_sources(arxiv_results)
                web_sources = web_results_to_sources(web_results)
                all_sources = deduplicate_sources(arxiv_sources + web_sources)

            tab_arxiv, tab_web, tab_unified = st.tabs([
                f"📚 ArXiv Papers ({len(arxiv_results)})",
                f"🌐 Web Results ({len(web_results)})",
                f"🧬 Unified Sources ({len(all_sources)})",
            ])

            with tab_arxiv:
                if not arxiv_results:
                    st.info("No ArXiv papers found for this query.")
                else:
                    for idx, paper in enumerate(arxiv_results, start=1):
                        with st.container():
                            st.markdown(f"### {idx}. {paper.title}")
                            st.caption(f"**Authors**: {', '.join(paper.authors) if paper.authors else 'Unknown'} | **Published**: {paper.published} | **ID**: `{paper.arxiv_id}`")
                            with st.expander("📄 View Abstract", expanded=True):
                                st.write(paper.summary)
                            if paper.pdf_url:
                                st.link_button("📥 Open PDF Link", paper.pdf_url)
                            st.divider()

            with tab_web:
                if not web_results:
                    st.info("No web results found.")
                else:
                    for idx, item in enumerate(web_results, start=1):
                        with st.container():
                            st.markdown(f"### {idx}. [{item.title}]({item.url})")
                            st.write(item.snippet)
                            st.caption(f"🔗 [Visit Source]({item.url})")
                            st.divider()

            with tab_unified:
                st.write("This deduplicated stream feeds into the **Groq Reasoning Agent** in Full Research mode:")
                for idx, source in enumerate(all_sources, start=1):
                    badge = "📘 ArXiv" if source.source_type == "arxiv" else "🌐 Web"
                    st.markdown(f"**{idx}. [{badge}] {source.title}**")
                    st.caption(f"Source: `{source.url_or_id}`")
                    st.write(source.content[:300] + ("..." if len(source.content) > 300 else ""))
                    st.divider()
    else:
        st.info("💡 Enter a topic above and click **Search** to test the retrieval tools.")
