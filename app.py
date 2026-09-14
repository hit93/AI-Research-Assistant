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
)

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
st.markdown('<div class="sub-header">Phase 3: LLM-Powered Research Pipeline with Query Planning & Synthesis</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Environment Status
    keys = settings.validate_keys()
    st.markdown("### 🔑 API Status")
    if keys["groq"]:
        st.success("Groq API: Connected")
        st.caption(f"🤖 **Synthesizer:** `{settings.GROQ_MODEL}`")
        st.caption(f"⚖️ **Verifier:** `{settings.VERIFIER_MODEL}`")
    else:
        st.error("Groq API: Missing — Add GROQ_API_KEY to .env")

    if keys["tavily"]:
        st.success("Tavily API: Connected (Primary Web)")
    else:
        st.info("Tavily API: Not Set (Using DuckDuckGo Fallback)")

    st.divider()
    st.subheader("Search Parameters")
    arxiv_max = st.slider("Max ArXiv Papers (per sub-query)", min_value=1, max_value=10, value=3)
    web_max = st.slider("Max Web Results (per sub-query)", min_value=1, max_value=10, value=3)
    
    st.divider()

    # Mode selector
    mode = st.radio(
        "Research Mode",
        ["🧠 Full Research (LLM Pipeline)", "🔧 Tools Explorer (Manual)"],
        index=0,
    )
    
    st.divider()
    st.caption("Roadmap Status: Phase 3 (LLM Agentic Pipeline)")

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
        elif not keys["groq"]:
            st.error("🔑 Groq API key required for Full Research mode. Add `GROQ_API_KEY` to your `.env` file.")
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
                    )

                progress_container.empty()
                st.session_state.last_research_result = result
                st.session_state.saved_reports = save_report(result)
            else:
                result = st.session_state.last_research_result
                if "saved_reports" not in st.session_state:
                    st.session_state.saved_reports = save_report(result)

            # Success banner
            score_info = ""
            if result.verification:
                score_info = f", Score: {result.verification.overall_score}/10"
            st.success(
                f"✅ Research complete in **{result.duration_seconds}s** — "
                f"{len(result.sources)} sources, {len(result.synthesis)} sections{score_info}"
            )

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
            tab_report, tab_plan, tab_sources, tab_verify = st.tabs([
                "📝 Research Report",
                f"📋 Query Plan ({len(result.plan.sub_queries)} sub-queries)",
                f"📚 Sources ({len(result.sources)})",
                "✅ Verification Report",
            ])

            # ── Research Report Tab ───────────────────────────
            with tab_report:
                for section in result.synthesis:
                    st.markdown(f"### {section.heading}")
                    st.markdown(section.content)
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

    else:
        st.info("💡 Enter a research topic above and click **Search** to run the full LLM research pipeline.")


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
