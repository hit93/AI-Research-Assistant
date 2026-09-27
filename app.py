"""
AI Research Assistant — Streamlit App
Chatbot-style architecture: Generate reports, then chat with them to edit and explain.
"""

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
from src.security import (
    guardrails_engine,
    global_rate_limiter,
    RedTeamHarness,
    RedTeamReport,
)


# ─────────────────────────────────────────────────────────────
# Page Config & Global Styles
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Research Assistant",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  .main-header {
      font-size: 2rem;
      font-weight: 700;
      background: linear-gradient(135deg, #60a5fa, #a78bfa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.1rem;
  }
  .sub-header {
      color: #64748b;
      font-size: 0.9rem;
      margin-bottom: 1.2rem;
  }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_available_models() -> list[str]:
    """Fetch available models from Google AI Studio and Groq API."""
    gemini_models = [
        "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
        "gemini-3.5-flash", "gemini-3.5-flash-lite",
        "gemini-3.6-flash", "gemini-3.7-flash",
    ]
    groq_models = [
        "openai/gpt-oss-120b", "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b", "groq/compound", "groq/compound-mini",
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
            groq_models = [m for m in preferred if m in models_set] + sorted(list(models_set - set(preferred)))
        except Exception:
            pass
    if settings.GEMINI_API_KEY:
        return gemini_models + groq_models
    return groq_models + gemini_models


def _report_to_context_text(result) -> str:
    """Convert a ResearchResult to a single text block for the chat LLM context."""
    topic = result.plan.sub_queries[0].question if result.plan.sub_queries else "Unknown Topic"
    lines = [f"# Research Report: {topic}\n"]
    for i, section in enumerate(result.synthesis, 1):
        lines.append(f"\n## Section {i}: {section.heading}\n")
        lines.append(section.content)
        lines.append("\n")
    if result.verification:
        v = result.verification
        lines.append(f"\n---\n**Quality Score:** {v.overall_score}/10 | **Approved:** {v.is_approved}\n")
        lines.append(f"**Assessment:** {v.summary}\n")
    return "\n".join(lines)


def _build_chat_system_prompt(report_context: str, query: str) -> str:
    """Build the system prompt that injects the report as LLM context."""
    return f"""You are an expert AI research assistant and scientific editor embedded inside a research report workflow.

The user has generated a research report on: \"{query}\"

Full report content:
---
{report_context}
---

Your responsibilities:
1. EXPLAIN any section, concept, term, or claim from the report clearly when asked.
2. EDIT sections on request: rewrite, improve, expand, summarize, or restructure. Output the full revised section text when editing.
3. ANSWER questions about the research content, methodology, sources, or findings.
4. CRITIQUE sections and suggest improvements when asked.
5. GENERATE new content: bullet summaries, key takeaways, executive summaries on request.

When providing an edited section, always start with: "**EDITED SECTION \u2014 [section name]:**"
Use markdown formatting. Be concise yet thorough. Ground edits in the actual research content."""


def _stream_chat_response(messages: list[dict], model: str) -> str:
    """Send multi-turn message history to LLM and return the response string."""
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from src.chains.llm import get_chat_llm

    lc_messages = []
    for m in messages:
        if m["role"] == "system":
            lc_messages.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    llm = get_chat_llm(temperature=0.4, max_tokens=4096, model=model)
    response = llm.invoke(lc_messages)
    return response.content if hasattr(response, "content") else str(response)


def _render_section(section, sec_idx: int, sources: list):
    """Render a single synthesized report section."""
    st.markdown(
        f"""<div style="border-left:4px solid #2563eb;padding-left:14px;
        margin-bottom:4px;margin-top:14px;">
        <h3 style="margin:0;color:#f1f5f9;">{sec_idx}. {section.heading}</h3></div>""",
        unsafe_allow_html=True,
    )
    mermaid_blocks = _extract_mermaid_blocks(section.content)
    if mermaid_blocks:
        for pre_text, mermaid_src, post_text in mermaid_blocks:
            if pre_text.strip():
                st.markdown(pre_text)
            inner = mermaid_src.replace("```mermaid", "").replace("```", "").strip()
            with st.expander("🔷 Diagram (Mermaid)", expanded=False):
                st.code(inner, language="mermaid")
                st.caption("Copy into [mermaid.live](https://mermaid.live) to render.")
            if post_text.strip():
                st.markdown(post_text)
    else:
        st.markdown(section.content)
    if section.source_indices:
        refs = [f"[{idx}] *{sources[idx].title}*" for idx in section.source_indices if 0 <= idx < len(sources)]
        if refs:
            with st.expander("📎 Referenced Sources"):
                for ref in refs:
                    st.caption(ref)
    st.divider()


# ─────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "last_research_result" not in st.session_state:
    st.session_state.last_research_result = None
if "last_full_query" not in st.session_state:
    st.session_state.last_full_query = ""
if "chat_model" not in st.session_state:
    st.session_state.chat_model = None


# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
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

    # 🤖 Model Selection
    st.subheader("🤖 Pipeline Models")
    available_models = fetch_available_models()

    gemini_prefs = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"]
    groq_prefs   = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

    def _pick(prefs):
        for m in prefs:
            if m in available_models:
                return m
        return available_models[0]

    primary_prefs  = gemini_prefs if settings.GEMINI_API_KEY else groq_prefs
    verifier_prefs = (["gemini-3.6-flash"] + gemini_prefs) if settings.GEMINI_API_KEY else groq_prefs

    selected_planner_model  = st.selectbox("🧠 Planner",    available_models,
        index=available_models.index(_pick(primary_prefs)),
        help="Decomposes the research topic into sub-queries.")
    selected_synth_model    = st.selectbox("⚗️ Synthesizer", available_models,
        index=available_models.index(_pick(primary_prefs)),
        help="Generates the full report sections.")
    selected_verifier_model = st.selectbox("⚖️ Verifier",    available_models,
        index=available_models.index(_pick(verifier_prefs)),
        help="Scores and audits the report.")
    selected_improver_model = st.selectbox("🛠️ Refiner",     available_models,
        index=available_models.index(_pick(verifier_prefs)),
        help="Rewrites sections below the score threshold.")

    # Chat model for report editor
    st.markdown("---")
    st.subheader("💬 Chat Model")
    selected_chat_model = st.selectbox(
        "🤖 Report Chat LLM", available_models,
        index=available_models.index(_pick(primary_prefs)),
        help="LLM used in the Chat tab to explain and edit your report.",
    )
    st.session_state.chat_model = selected_chat_model

    st.divider()
    st.subheader("⚡ Research Depth")
    depth_choice = st.radio(
        "Mode",
        ["⚡ Quick (~15s)", "🔬 Deep (~60s)"],
        index=0,
        help="Quick: 3 sub-queries, fast pass. Deep: 5-7 sub-queries, full multi-round audit."
    )
    is_quick_mode = "Quick" in depth_choice
    selected_research_mode = "quick" if is_quick_mode else "deep"

    st.divider()
    st.subheader("🔍 Search Params")
    def_n = 2 if is_quick_mode else 3
    arxiv_max = st.slider("Max ArXiv Papers", 1, 10, def_n)
    web_max   = st.slider("Max Web Results",  1, 10, def_n)

    st.divider()
    st.subheader("🛡️ Security")
    st.caption(f"🔒 PII Masker: **{'Active' if settings.ENABLE_PII_MASKING else 'Off'}**")
    st.caption(f"🛡️ Guardrails: **{'Active' if settings.ENABLE_GUARDRAILS else 'Off'}**")
    st.caption(f"⏱️ Rate Limiter: **{'Active' if settings.RATE_LIMIT_ENABLED else 'Off'}**")

    st.divider()
    st.subheader("🗂️ Navigation")
    mode = st.radio(
        "App Mode",
        ["🔬 Research & Chat", "🔧 Tools Explorer", "🛡️ Security Audit"],
        index=0,
    )
    st.caption("Phase 6 — Security + Chatbot Editor")


# ═══════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════
st.markdown('<div class="main-header">🔬 AI Research Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Generate research reports, then chat to edit, explain, and improve any section.</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# MODE 1: Research + Chatbot Report Editor
# ═══════════════════════════════════════════════════════════════
if "🔬" in mode:
    # Query input row
    col_q, col_btn = st.columns([5, 1])
    with col_q:
        query = st.text_input(
            "Research Topic",
            placeholder="e.g. Multi-Agent Systems in Healthcare or Quantum Key Distribution",
            label_visibility="collapsed",
            key="main_query_input",
        )
    with col_btn:
        search_clicked = st.button("🔍 Generate", type="primary", use_container_width=True)

    result = st.session_state.last_research_result
    has_cached = (
        result is not None
        and st.session_state.last_full_query == query
        and bool(query.strip())
    )

    if search_clicked or has_cached:
        if not query.strip():
            st.warning("Enter a research topic above.")
        elif not (keys.get("gemini") or keys["groq"]):
            st.error("🔑 Add `GEMINI_API_KEY` or `GROQ_API_KEY` to your `.env` file.")
        else:
            if search_clicked and not has_cached:
                st.session_state.last_full_query = query
                st.session_state.chat_messages = []  # Reset chat for new report

                progress_container = st.empty()
                progress_messages: list[str] = []

                def on_progress(status: str, detail: str):
                    icons = {
                        "planning": "🧠", "planned": "✅",
                        "retrieving": "🔍", "retrieved": "📦",
                        "deduplicated": "🧹",
                        "synthesizing": "⚗️", "synthesized": "✅",
                        "verifying": "🔎", "verified": "✅",
                        "improving": "🛠️", "improved": "✨",
                        "complete": "🏁",
                    }
                    icon = icons.get(status, "▸")
                    progress_messages.append(f"{icon} **{status.upper()}**: {detail}")
                    progress_container.markdown("\n\n".join(progress_messages))

                with st.spinner("Running research pipeline..."):
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

            elif has_cached:
                result = st.session_state.last_research_result
                if "saved_reports" not in st.session_state:
                    st.session_state.saved_reports = save_report(result)

            if result is None:
                st.error("Research pipeline returned no result.")
                st.stop()

            if getattr(result, "is_cache_hit", False):
                st.info("⚡ **Served from Semantic Cache** — bypassed search & LLM generation.")

            score_info = f", Score: {result.verification.overall_score}/10" if result.verification else ""
            st.success(
                f"✅ Complete in **{result.duration_seconds}s** — "
                f"{len(result.sources)} sources, {len(result.synthesis)} sections{score_info}"
            )
            if getattr(result, "errors", None):
                with st.expander("⚠️ Pipeline errors"):
                    for err in result.errors:
                        st.write(f"- {err}")

            # Export row
            saved_paths = st.session_state.get("saved_reports", {})
            col_pdf, col_md, col_json, col_info = st.columns([1.2, 1.4, 1.2, 2.2])
            with col_pdf:
                st.download_button("📄 PDF", export_to_pdf(result),
                    file_name=saved_paths.get("pdf", Path("report.pdf")).name,
                    mime="application/pdf", use_container_width=True)
            with col_md:
                st.download_button("📝 Markdown", export_to_markdown(result),
                    file_name=saved_paths.get("md", Path("report.md")).name,
                    mime="text/markdown", use_container_width=True)
            with col_json:
                st.download_button("📊 JSON", export_to_json(result),
                    file_name=saved_paths.get("json", Path("report.json")).name,
                    mime="application/json", use_container_width=True)
            with col_info:
                st.caption("💾 *Auto-saved to `data/reports/`*")

            # ── Main tabs ──
            tab_report, tab_chat, tab_plan, tab_sources, tab_verify, tab_history = st.tabs([
                "📝 Report",
                "💬 Chat · Edit & Explain",
                f"📋 Query Plan ({len(result.plan.sub_queries)} sub-queries)",
                f"📚 Sources ({len(result.sources)})",
                "✅ Verification",
                "🏛️ Memory (LTM)",
            ])

            # ── Report Tab ──
            with tab_report:
                with st.expander("📑 Table of Contents", expanded=True):
                    for i, section in enumerate(result.synthesis, 1):
                        st.caption(f"{i}. {section.heading}")
                st.divider()
                for sec_idx, section in enumerate(result.synthesis, 1):
                    _render_section(section, sec_idx, result.sources)

            # ── Chat · Edit & Explain Tab ──
            with tab_chat:
                report_context = _report_to_context_text(result)
                system_prompt  = _build_chat_system_prompt(report_context, query)

                st.markdown("""
> 💡 **Chat with your report.** Ask the AI to:
> - **Explain** a section: *"Explain the methodology section"*
> - **Edit** content: *"Rewrite the Introduction to be more concise"*
> - **Expand**: *"Add a section on ethical implications"*
> - **Summarise**: *"Give me a 3-bullet executive summary"*
> - **Critique**: *"What are the weaknesses of this report?"*
""")

                # Quick-action chips
                st.markdown("#### ⚡ Quick Actions")
                qa_cols = st.columns(4)
                quick_actions = [
                    ("📋 Executive Summary",   "Give me a 3-bullet executive summary of this entire report."),
                    ("🔍 Explain Methodology", "Explain the research methodology used in this report in simple terms."),
                    ("✏️ Improve Introduction", "Rewrite the Introduction section to be more compelling and concise."),
                    ("⚠️ Weaknesses",           "What are the key limitations and weaknesses of this research report?"),
                ]
                for col, (label, prompt) in zip(qa_cols, quick_actions):
                    if col.button(label, use_container_width=True, key=f"qa_{label}"):
                        st.session_state.chat_messages.append({"role": "user", "content": prompt})
                        with st.spinner("Thinking..."):
                            msgs = [{"role": "system", "content": system_prompt}] + st.session_state.chat_messages
                            reply = _stream_chat_response(msgs, st.session_state.chat_model)
                        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
                        st.rerun()

                st.divider()

                # Chat history display
                if not st.session_state.chat_messages:
                    st.info("👋 Start a conversation below — ask anything about your report.")
                else:
                    for msg in st.session_state.chat_messages:
                        if msg["role"] == "user":
                            with st.chat_message("user", avatar="🧑‍💻"):
                                st.markdown(msg["content"])
                        else:
                            with st.chat_message("assistant", avatar="🤖"):
                                st.markdown(msg["content"])

                if st.session_state.chat_messages:
                    if st.button("🗑️ Clear conversation", key="clear_chat"):
                        st.session_state.chat_messages = []
                        st.rerun()

                # Chat input
                user_input = st.chat_input(
                    "Ask about the report, request edits, or ask for explanations...",
                    key="chat_input_main",
                )
                if user_input:
                    # Input guardrails
                    if settings.ENABLE_GUARDRAILS:
                        guard_res = guardrails_engine.evaluate_input(user_input, source_type="CHAT_MESSAGE")
                        if guard_res.is_blocked:
                            st.error("🛡️ Message blocked by security guardrails. Please rephrase.")
                            st.stop()
                        safe_input = guard_res.sanitized_text
                    else:
                        safe_input = user_input

                    st.session_state.chat_messages.append({"role": "user", "content": safe_input})

                    with st.spinner("Thinking..."):
                        msgs = [{"role": "system", "content": system_prompt}] + st.session_state.chat_messages
                        reply = _stream_chat_response(msgs, st.session_state.chat_model)

                    # Output guardrails
                    if settings.ENABLE_GUARDRAILS:
                        out_res = guardrails_engine.evaluate_output(reply)
                        reply = out_res.sanitized_text

                    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
                    st.rerun()

            # ── Query Plan Tab ──
            with tab_plan:
                if result.plan.reasoning:
                    st.info(f"**Strategy:** {result.plan.reasoning}")
                for i, sq in enumerate(result.plan.sub_queries, 1):
                    st.markdown(f"**{i}. {sq.question}**")
                    st.caption(f"🔑 Keywords: {', '.join(sq.search_keywords)} | 📂 Source: `{sq.source_type}`")
                    st.divider()

            # ── Sources Tab ──
            with tab_sources:
                for idx, source in enumerate(result.sources):
                    badge = "📘 ArXiv" if source.source_type == "arxiv" else "🌐 Web"
                    st.markdown(f"**[{idx}] {badge} — {source.title}**")
                    st.caption(f"Source: `{source.url_or_id}`")
                    if source.authors:
                        st.caption(f"Authors: {', '.join(source.authors)}")
                    with st.expander("View content"):
                        st.write(source.content)
                    st.divider()

            # ── Verification Tab ──
            with tab_verify:
                if result.verification:
                    v = result.verification
                    col_score, col_status = st.columns(2)
                    with col_score:
                        st.metric("Quality Score", f"{v.overall_score}/10")
                    with col_status:
                        st.success("✅ Approved") if v.is_approved else st.warning("⚠️ Flagged")
                    st.markdown(f"**Assessment:** {v.summary}")
                    if v.issues:
                        st.markdown(f"### Issues ({len(v.issues)})")
                        sev_icons = {"low": "🟢", "medium": "🟡", "high": "🔴"}
                        for issue in v.issues:
                            icon = sev_icons.get(issue.severity, "⚪")
                            st.markdown(f"{icon} **[{issue.severity.upper()}]** *{issue.section_heading}*: {issue.issue}")
                            if issue.suggestion:
                                st.caption(f"💡 {issue.suggestion}")
                            st.divider()
                    else:
                        st.info("✨ Report passed verification cleanly.")
                else:
                    st.info("Verification was not performed.")

            # ── LTM History Tab ──
            with tab_history:
                st.markdown("### 🏛️ Long-Term Memory Archive")
                st.caption("Past runs stored in SQLite (`data/cache/ltm.db`).")
                history = get_ltm().get_history(limit=10)
                if history:
                    for h in history:
                        col1, col2, col3 = st.columns([4, 1.2, 1.2])
                        with col1:
                            st.markdown(f"**{h['topic']}**")
                            if h.get("synthesis_summary"):
                                st.caption(h["synthesis_summary"][:150] + "...")
                        with col2:
                            st.metric("Score", f"{h.get('score', 'N/A')}/10")
                        with col3:
                            st.caption("✅ Approved" if h.get("approved") else "⚠️ Flagged")
                        st.divider()
                else:
                    st.info("No past runs in LTM yet.")

    else:
        st.info("💡 Enter a research topic above and click **Generate** to create a report. Then use the **Chat** tab to edit or explain any section.")
        history = get_ltm().get_history(limit=5)
        if history:
            with st.expander(f"📚 Recent Research Archive ({len(history)} topics)"):
                for h in history:
                    st.markdown(f"• **{h['topic']}** (Score: `{h.get('score', 'N/A')}/10`)")


# ═══════════════════════════════════════════════════════════════
# MODE 2: Tools Explorer
# ═══════════════════════════════════════════════════════════════
elif "🔧" in mode:
    st.markdown("## 🔧 Manual Tools Explorer")
    col_q2, col_btn2 = st.columns([5, 1])
    with col_q2:
        query = st.text_input("Search Topic",
            placeholder="e.g. Transformer attention mechanisms",
            label_visibility="collapsed", key="tools_query")
    with col_btn2:
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True, key="tools_search_btn")

    if search_clicked and query.strip():
        with st.spinner("Querying tools..."):
            arxiv_results = search_arxiv(query, max_results=arxiv_max)
            web_results   = search_web(query, max_results=web_max)
            arxiv_sources = papers_to_sources(arxiv_results)
            web_sources   = web_results_to_sources(web_results)
            all_sources   = deduplicate_sources(arxiv_sources + web_sources)

        tab_a, tab_w, tab_u = st.tabs([
            f"📚 ArXiv ({len(arxiv_results)})",
            f"🌐 Web ({len(web_results)})",
            f"🧬 Unified ({len(all_sources)})",
        ])
        with tab_a:
            for idx, paper in enumerate(arxiv_results, 1):
                st.markdown(f"### {idx}. {paper.title}")
                st.caption(f"**Authors**: {', '.join(paper.authors) if paper.authors else 'Unknown'} | **Published**: {paper.published}")
                with st.expander("📄 Abstract", expanded=True):
                    st.write(paper.summary)
                if paper.pdf_url:
                    st.link_button("📥 PDF", paper.pdf_url)
                st.divider()
        with tab_w:
            for idx, item in enumerate(web_results, 1):
                st.markdown(f"### {idx}. [{item.title}]({item.url})")
                st.write(item.snippet)
                st.divider()
        with tab_u:
            for idx, source in enumerate(all_sources, 1):
                badge = "📘 ArXiv" if source.source_type == "arxiv" else "🌐 Web"
                st.markdown(f"**{idx}. [{badge}] {source.title}**")
                st.caption(f"`{source.url_or_id}`")
                st.write(source.content[:300] + ("..." if len(source.content) > 300 else ""))
                st.divider()
    elif not query.strip() if 'query' in dir() else True:
        st.info("💡 Enter a topic above and click Search.")


# ═══════════════════════════════════════════════════════════════
# MODE 3: Security Audit (PyRIT Red-Teaming)
# ═══════════════════════════════════════════════════════════════
else:
    st.markdown("## 🛡️ PyRIT Adversarial Security & Red-Teaming Dashboard")
    st.write(
        "Execute automated penetration scans against **Direct Prompt Injection**, "
        "**Delimiter Smuggling**, **XPIA**, **DAN Jailbreaks**, **PII Exfiltration**, "
        "and **Prompt Leaks** using the **100% Local Guardrails Engine**."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Local Guardrails", "Active" if settings.ENABLE_GUARDRAILS else "Disabled")
    with col2:
        st.metric("PII Masking", "Active" if settings.ENABLE_PII_MASKING else "Disabled")
    with col3:
        st.metric("Rate Limiting", "10 req/s" if settings.RATE_LIMIT_ENABLED else "Disabled")

    st.divider()

    custom_probe = st.text_area(
        "🔬 Custom Adversarial Payload (Optional)",
        placeholder="Enter a prompt injection or jailbreak string to test...",
        height=100,
    )

    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
        run_full_suite = st.button("🚀 Run PyRIT Full Benchmark (8 Vectors)", type="primary", use_container_width=True)
    with col_r2:
        test_custom = st.button("🧪 Test Custom Payload", use_container_width=True)

    if test_custom and custom_probe.strip():
        with st.spinner("Evaluating..."):
            res = guardrails_engine.evaluate_input(custom_probe)
        if res.is_blocked:
            st.error(f"❌ BLOCKED — Action: `{res.action}`")
        elif res.action == "ANONYMIZED":
            st.warning(f"⚠️ ANONYMIZED — `{res.sanitized_text}`")
        else:
            st.success("✅ PASSED — No critical violations.")
        if res.violations:
            st.markdown("#### Violations:")
            for v in res.violations:
                st.markdown(f"- **{v.category}** | **{v.severity}** | {v.description}")

    if run_full_suite or "last_redteam_report" in st.session_state:
        if run_full_suite:
            with st.spinner("Running PyRIT benchmark..."):
                harness = RedTeamHarness(engine=guardrails_engine)
                report = harness.run_suite()
                st.session_state["last_redteam_report"] = report
        else:
            report = st.session_state["last_redteam_report"]
        st.markdown(report.to_markdown())
