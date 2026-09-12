import streamlit as st
from config.settings import settings
from src.tools import (
    search_arxiv,
    papers_to_sources,
    search_web,
    web_results_to_sources,
    deduplicate_sources,
)

st.set_page_config(
    page_title="AI Research Assistant - Tools Explorer",
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
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">🔬 AI Research Assistant — Tools Explorer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Phase 2 Verification: Interactive ArXiv Academic Retrieval & Web Search</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Environment Status
    keys = settings.validate_keys()
    st.markdown("### 🔑 API Status")
    if keys["tavily"]:
        st.success("Tavily API: Connected (Primary Web)")
    else:
        st.info("Tavily API: Not Set (Using DuckDuckGo Fallback)")
        
    if keys["groq"]:
        st.success("Groq API: Connected (Phase 3 Ready)")
    else:
        st.warning("Groq API: Pending in .env")

    st.divider()
    st.subheader("Search Parameters")
    arxiv_max = st.slider("Max ArXiv Papers", min_value=1, max_value=10, value=3)
    web_max = st.slider("Max Web Results", min_value=1, max_value=10, value=3)
    
    st.divider()
    st.caption("Roadmap Status: Phase 2 (Tools & UI Explorer)")

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
            st.write("This deduplicated stream will feed directly into the **Groq Reasoning Agent** in Phase 3:")
            for idx, source in enumerate(all_sources, start=1):
                badge = "📘 ArXiv" if source.source_type == "arxiv" else "🌐 Web"
                st.markdown(f"**{idx}. [{badge}] {source.title}**")
                st.caption(f"Source: `{source.url_or_id}`")
                st.write(source.content[:300] + ("..." if len(source.content) > 300 else ""))
                st.divider()
else:
    st.info("💡 Enter a topic above and click **Search** to test the retrieval tools.")
