# 🔬 AI Research Assistant - Master Development Roadmap

A step-by-step, checkpoint-driven blueprint for building a modular, production-ready AI Research Assistant.

---

## 🧭 Architecture Overview

```mermaid
flowchart TD
    UserQuery["User Topic / Query"] --> Planner["1. Query Planner & Decomposer"]
    Planner --> SearchTools["2. Research & Retrieval Tools"]
    
    subgraph RetrievalLayer ["Data Retrieval Layer"]
        SearchTools --> Arxiv["ArXiv Tool (Academic Papers)"]
        SearchTools --> WebSearch["Web Search (Tavily / DuckDuckGo)"]
        SearchTools --> DocParser["Document / PDF Parser"]
    end

    RetrievalLayer --> Synthesizer["3. Synthesis & Reasoning Engine"]
    Synthesizer --> FactCheck["4. Fact-Checker & Citation Engine"]
    FactCheck --> Exporter["5. Markdown / PDF Exporter"]
    
    subgraph ServerLayer ["Phase 5: Deployment Layer (At the very end)"]
        Exporter --> APIServer["FastAPI Server / Background Workers"]
        APIServer --> WebUI["Interactive Web UI / Dashboard"]
    end
```

---

## 📋 Step-by-Step Implementation Phases

### 🔹 Phase 1: Project Scaffolding & Environment Setup
- [x] Initialize modular folder hierarchy:
  ```text
  research_assistant/
  ├── config/             # Configuration & environment loader
  ├── src/
  │   ├── tools/          # ArXiv, Web Search, Scrapers
  │   ├── agents/         # Planner, Researcher, Synthesizer
  │   ├── models/         # Pydantic schemas & state models
  │   ├── utils/          # Formatting, exports, logging
  │   └── server/         # API / Web server (Phase 5)
  ├── tests/              # Unit & integration tests
  ├── data/               # Cache, saved reports, downloads
  ├── .env.example        # Template for API keys
  ├── .env                # Local keys (Groq & Tavily)
  ├── .gitignore          # Environment & secret exclusion
  ├── requirements.txt    # Project dependencies
  ├── README.md           # Project documentation
  └── plan.md             # This progress tracker
  ```
- [x] Set up Python environment & dependency management (`uv` with `.venv`).
- [x] Implement robust configuration management with `pydantic-settings` / `python-dotenv`.
- [x] Set up structured logging for research tracking.

> ### 🏁 Checkpoint 1: Environment & Config Verification
> - [x] Config validator script passes: successfully loads API keys or warns with actionable messages.
> - [x] Project directory structure is cleanly initialized without errors.

---

### 🔹 Phase 2: Research Tools & Ingestion Engine
- [x] **ArXiv Research Tool**:
  - [x] Search papers by topic, title, or authors.
  - [x] Extract metadata: abstract, publication date, authors, PDF links, arXiv ID.
- [x] **Web Search Tool**:
  - [x] Integrate Tavily Search API or DuckDuckGo Search for general web & news context.
  - [x] Clean and strip boilerplate HTML content.
- [x] **Document & Content Normalization**:
  - [x] Implement text cleaning and abstract extraction from academic sources.
- [x] **Deduplication & Unified Schemas**:
  - [x] Unified `ResearchSource` model and duplicate pruning based on URL and title.
- [x] **Interactive Streamlit Explorer (`app.py`)**:
  - [x] Visual UI to search, browse, and inspect ArXiv & Web retrieval items live.

> ### 🏁 Checkpoint 2: Retrieval Tools Verification (PASSED)
> - [x] Independent test scripts verify ArXiv query returns parsed paper objects.
> - [x] Web search tool returns clean text snippets and source URLs.
> - [x] Mock queries confirm zero crashes on network failures or malformed responses.

---

### 🔹 Phase 3: Core LLM & Agentic Reasoning Workflow (Textbook LangChain & LangGraph)
- [x] Configure LLM provider abstraction via **LangChain** (`langchain-groq`, `ChatGroq`, extensible to OpenAI/Gemini).
- [x] **Modular Prompts Layer (`src/prompts/`)**:
  - [x] Versioned `ChatPromptTemplate` for query decomposition (`src/prompts/planner.py`).
  - [x] Versioned `ChatPromptTemplate` for source synthesis (`src/prompts/synthesizer.py`).
- [x] **Composable LCEL Chains Layer (`src/chains/`)**:
  - [x] Centralized ChatGroq factory (`src/chains/llm.py`).
  - [x] `planner_chain`: `planner_prompt | llm.with_structured_output(QueryPlan)`.
  - [x] `synthesizer_chain`: `synthesizer_prompt | llm.with_structured_output(SynthesisReport)`.
- [x] **State Machine Graph Layer (`src/graphs/` via LangGraph)**:
  - [x] `ResearchGraphState` TypedDict state schema (`src/graphs/state.py`).
  - [x] Graph nodes: `plan_node`, `retrieve_node`, `synthesize_node` (`src/graphs/nodes.py`).
  - [x] Compiled `StateGraph`: `START -> planner -> retriever -> synthesizer -> END` with live stream callbacks (`src/graphs/graph.py`).
- [x] **LangChain Tool Integration**:
  - [x] Added `@tool` wrappers for `arxiv_search` and `web_search` in `src/tools/langchain_tools.py`.
- [x] **Backward-Compatibility Facade Layer (`src/agents/`)**:
  - [x] Re-exports and adapters preserving compatibility for `app.py` (Streamlit) and CLI (`python -m src.agents`).
- [x] **Interactive Streamlit Integration (`app.py`)**:
  - [x] Full Research mode with live progress indicator callback.
  - [x] Tabbed UI displaying Synthesized Report, Query Plan breakdown, and Sources cards.
- [x] **Comprehensive Testing & Educational Docs**:
  - [x] 26 unit tests across `tests/test_graphs.py`, `tests/test_agents.py`, and `tests/test_config.py` (100% passing).
  - [x] Created `PHASE3_EXPLAINED.md` deep dive into the reasoning pipeline.

> ### 🏁 Checkpoint 3: CLI & Web Research Run Verification (PASSED)
> - [x] CLI execution verified: `python -m src.agents --topic "Quantum Machine Learning"`.
> - [x] LangGraph StateGraph pipeline verified: 5 sub-queries decomposed, 4 sources retrieved, 6 synthesized sections generated with citations.
> - [x] Streamlit Web execution verified: live end-to-end run on `localhost:8502`.
> - [x] Resilient ArXiv timeout and error recovery verified.

---

### 🔹 Phase 4: Citation Engine, Fact-Checking & Report Generation (🎯 Next Up)
- [ ] **Citation & Attribution Engine**:
  - [ ] Standardize citation format (inline brackets `[1]`, Markdown footnotes `[^1]`, or academic bibliography).
  - [ ] Validate every claim maps to an extracted source link with author and publication metadata.
  - [ ] Source reference linker connecting report claims directly to raw excerpts.
- [ ] **Quality & Hallucination Guard**:
  - [ ] Cross-check generated report against retrieved excerpts for factual consistency.
  - [ ] Flag ungrounded assertions or hallucinated sources.
- [ ] **Multi-Format Report Exporter**:
  - [ ] Export comprehensive research report to Markdown (`.md`).
  - [ ] Export to formatted PDF and structured JSON summaries.
  - [ ] Auto-save reports with query slug & timestamp to `data/reports/`.
- [ ] **UI Download Integration**:
  - [ ] Integrate Markdown and PDF download buttons in the Streamlit app.

> ### 🏁 Checkpoint 4: Report Quality & Export Verification
> - [ ] Automated verification: Report contains executive summary, literature review, findings, and bibliography.
> - [ ] Output file saved successfully in `data/reports/` with working citation links.
> - [ ] Streamlit UI export buttons allow single-click download of `.md` and `.pdf` reports.

---

### 🔹 Phase 5: Server & Interactive Interface (Final Phase)
- [ ] **Backend API (FastAPI)**:
  - [ ] `POST /api/research`: Trigger async research job with topic & depth options.
  - [ ] `GET /api/research/{job_id}`: Stream progress / check status.
  - [ ] `GET /api/research/{job_id}/download`: Download report as PDF/Markdown.
- [ ] **Interactive User Interface**:
  - [x] Streamlit Dashboard (Mode 1 & Mode 2 already operational in `app.py`).
  - [ ] Real-time WebSocket or streaming progress updates for background jobs.
  - [ ] Interactive report viewer with markdown rendering and download buttons.
- [ ] **Production Readiness**:
  - [ ] Dockerfile containerization.
  - [ ] Caching layer (SQLite / Redis) to avoid repeated API spend on identical queries.

> ### 🏁 Checkpoint 5: Full System End-to-End Verification
> - [ ] Server starts with `python -m src.server.main` without warnings.
> - [ ] User can enter research prompt in UI/API, view real-time research progress, and download the finished report.

---

## 📌 Progress Tracker
 
| Step | Milestone | Status | Notes / Blockers |
| :--- | :--- | :---: | :--- |
| **Step 1** | Project Setup & Environment | 🟢 Completed | Directory scaffold, config loader & tests pass |
| **Step 2** | Research Tools (ArXiv + Web) | 🟢 Completed | ArXiv + Tavily / DDG tools & tests pass (5/5) |
| **Step 3** | Reasoning & Agentic Pipeline | 🟢 Completed | Groq LLM client, Planner, Synthesizer, CLI + Streamlit UI verified |
| **Step 4** | Citations & Report Exporter | 🟡 Next Up | Citation engine, fact-checking, Markdown & PDF export |
| **Step 5** | Server & Production Deployment | ⚪ Pending | FastAPI endpoints, background worker, Docker, caching |


