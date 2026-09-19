# 🔬 AI Research Assistant - Master Development Roadmap

A step-by-step, checkpoint-driven blueprint for building a modular, production-ready AI Research Assistant.

**Base project:** Krish Naik — Multi-Agent AI Research Platform with AWS Guardrails, LLM Gateway, Red Teaming, STM/LTM & Semantic Caching, extended with a Visual LLM agent

---

## 🧭 Architecture Overview

```
flowchart TD
    UserQuery["User Topic / Query"] --> Planner["1. Query Planner & Decomposer"]
    Planner --> SearchTools["2. Research & Retrieval Tools"]

    subgraph RetrievalLayer ["Data Retrieval Layer"]
        SearchTools --> Arxiv["ArXiv Tool (Academic Papers)"]
        SearchTools --> WebSearch["Web Search (Tavily / DuckDuckGo)"]
        SearchTools --> DocParser["Document / PDF Parser"]
    end

    RetrievalLayer --> Synthesizer["3. Synthesis & Reasoning Engine"]
    Synthesizer --> Verifier["3b. Verify Agent (self-critique / LLM-as-judge)"]
    Verifier --> FactCheck["4. Fact-Checker & Citation Engine"]
    FactCheck --> Exporter["4b. Markdown / PDF Exporter"]

    subgraph GatewayMemory ["Phase 4: Gateway, Memory & Evaluation"]
        Gateway["LLM Gateway (GPT-4o primary, Groq fallback)"]
        STM["Redis Short-Term Memory"]
        LTM["PostgreSQL + pgvector Long-Term Memory"]
        Cache["Semantic Caching"]
        Trace["LangSmith Tracing + LLM-as-Judge"]
    end

    subgraph VisualExt ["Phase 5: Visual LLM Extension"]
        VLM["Visual Analyst Agent (VLM)"]
        VisualVerify["Visual Verification vs. Source Figures"]
    end

    subgraph SecurityLayer ["Phase 6: Security & Red Teaming"]
        Guardrails["AWS Bedrock Guardrails"]
        RedTeam["PyRIT Red-Team Dashboard (incl. image-based attacks)"]
    end

    subgraph ServerLayer ["Phase 7: Infrastructure & Deployment"]
        Exporter --> APIServer["FastAPI Server / Background Workers"]
        APIServer --> Terraform["Terraform: ECS, RDS, ElastiCache, ALB, Secrets Manager"]
        Terraform --> CICD["GitHub Actions CI/CD (build, deploy, rollback)"]
        CICD --> WebUI["Interactive Web UI / Dashboard"]
    end
```

    Loading

---

## 📋 Step-by-Step Implementation Phases

### 🔹 Phase 1: Project Scaffolding & Environment Setup

- [x] Initialize modular folder hierarchy:

```text
research_assistant/
├── .github/workflows/  # Automated GitHub Actions CI pipeline
│   └── ci.yml
├── config/             # Configuration & environment loader
├── src/
│   ├── prompts/        # Versioned ChatPromptTemplates (Planner, Synthesizer, Verifier)
│   ├── chains/         # Composable LCEL chains (LLM factory, Planner, Synthesizer, Verifier)
│   ├── graphs/         # LangGraph StateGraph, nodes, and workflow execution
│   ├── tools/          # ArXiv, Web Search (Tavily/DDG), text cleaner, @tool wrappers
│   ├── models/         # Pydantic schemas & state models
│   ├── utils/          # Formatting, PDF/MD/JSON exports, logging
│   ├── agents/         # Backward-compatibility facades delegating to chains & graphs
│   └── server/         # API / Web server (Phase 7)
├── tests/              # Automated pytest suite (48 tests covering graphs, chains, tools, exporters)
├── data/               # Cache, saved reports, downloads
├── app.py              # Streamlit interactive dashboard
├── Dockerfile          # Multi-stage production container image
├── docker-compose.yml  # Multi-service stack (App, Redis STM, PostgreSQL+pgvector LTM)
├── .dockerignore       # Docker build exclusion rules
├── pyproject.toml      # Modern Python packaging, Ruff, and Pytest configuration
├── ARCHITECTURE.md     # Token-efficient architectural blueprint & Mermaid state machine
├── CONTRIBUTING.md     # Contributor guide, code standards, and PR checklist
├── .env.example        # Template for API keys
├── .env                # Local keys (Groq & Tavily)
├── .gitignore          # Environment & secret exclusion
├── requirements.txt    # Project dependencies
├── README.md           # Project documentation
└── plan.md             # This progress tracker
```

- [x] Set up Python environment & dependency management (`uv` with `.venv` and `pyproject.toml`).
- [x] Implement robust configuration management with `pydantic-settings` / `python-dotenv`.
- [x] Set up structured logging for research tracking.
- [x] Create developer ergonomics & management docs (`ARCHITECTURE.md`, `CONTRIBUTING.md`, `pyproject.toml`).
- [x] Scaffolding for Docker containerization (`Dockerfile`, `docker-compose.yml`, `.dockerignore`) and CI/CD (`.github/workflows/ci.yml`).

> ### 🏁 Checkpoint 1: Environment & Config Verification (PASSED)
>
> - [x] Config validator script passes: successfully loads API keys or warns with actionable messages.
> - [x] Project directory structure is cleanly initialized without errors.
> - [x] Modern development tooling, CI pipeline, and architecture documentation active.

---

### 🔹 Phase 2: Research Tools & Ingestion Engine

- [x] **ArXiv Research Tool**: search by topic/title/author; extract abstract, date, authors, PDF links, arXiv ID; resilient socket timeouts.
- [x] **Web Search Tool**: Tavily Search API primary, zero-config fallback to DuckDuckGo Search.
- [x] **Document & Content Normalization**: text cleaning and abstract extraction from academic sources.
- [x] **Deduplication & Unified Schemas**: unified `ResearchSource` model, dedup on normalized URL/title.
- [x] **Interactive Streamlit Explorer (`app.py`)**: manual browse/test of ArXiv & Web retrieval.

> ### 🏁 Checkpoint 2: Retrieval Tools Verification (PASSED)
>
> - [x] Independent test scripts verify ArXiv query returns parsed paper objects.
> - [x] Web search tool returns clean text snippets and source URLs.
> - [x] Mock queries confirm zero crashes on network failures or malformed responses.

---

### 🔹 Phase 3: Core LLM & Agentic Reasoning Workflow (Textbook LangChain & LangGraph)

- [x] Configure LLM provider abstraction via **LangChain** (`langchain-groq`, `ChatGroq`, extensible to OpenAI/Gemini/GPT-4o).
- [x] **Modular Prompts Layer (`src/prompts/`)**: versioned `ChatPromptTemplate` for query decomposition and source synthesis.
- [x] **Composable LCEL Chains Layer (`src/chains/`)**: `planner_chain`, `synthesizer_chain` with structured output binding.
- [x] **State Machine Graph Layer (`src/graphs/`)**: `ResearchGraphState`, nodes `plan_node` / `retrieve_node` / `synthesize_node` / `verify_node`, compiled `START → planner → retriever → synthesizer → verifier → END` with streaming callbacks.
- [x] **LangChain Tool Integration**: `@tool` wrappers for `arxiv_search` and `web_search`.
- [x] **Backward-Compatibility Facade Layer (`src/agents/`)**.
- [x] **Interactive Streamlit Integration (`app.py`)**: Full Research mode + Tools Explorer mode.
- [x] **Comprehensive Testing**: 36 unit tests, 100% passing, offline-mocked.
- [x] **Add a distinct Verify agent** (self-critique / LLM-as-judge, "did the summary/report actually follow from the sources") as its own graph node, rather than folding verification into the Synthesizer — closes the loop the roadmap milestone calls for (`START → planner → retriever → synthesizer → verifier → END`).
- [x] Split synthesis into distinct **Write** and **Verify** stages if the single `synthesize_node` still does both.
- [x] **Dedicated Verifier LLM** (`openai/gpt-oss-120b` via Groq): the Verify node uses a separate, more capable judge model configured via `VERIFIER_MODEL` in `.env`, distinct from the `GROQ_MODEL` used by the Planner and Synthesizer.
- [x] **Multi-Format Report Exporter (`src/utils/exporter.py`)**: Export verified research results into publication-ready PDF (ReportLab with custom typography, headers, citation tables, evaluator badges, and dynamic page numbering), GitHub-Flavored Markdown, and structured JSON. Includes auto-saving to `data/reports/`.
- [x] **Streamlit UI Download Action Bar**: One-click download buttons for `📄 Download PDF`, `📝 Download Markdown`, and `📊 Download JSON`, with auto-save confirmation and rerender caching.
- [x] **Comprehensive Testing Suite**: 41 unit tests covering agents, chains, graphs, tools, config, and PDF/Markdown/JSON exporters (100% passing).

> ### 🏁 Checkpoint 3: CLI, Web Research Run & PDF Export Verification (PASSED)
>
> - [x] CLI execution verified: `python -m src.agents --topic "Quantum Machine Learning"`.
> - [x] LangGraph StateGraph pipeline verified: 5 sub-queries decomposed, 4 sources retrieved, 6 synthesized sections generated with citations.
> - [x] Streamlit Web execution verified: live end-to-end run on `localhost:8502`.
> - [x] Resilient ArXiv timeout and error recovery verified.
> - [x] Verify agent runs as a discrete node and can reject/flag a report before it reaches the user.
> - [x] Verifier uses `openai/gpt-oss-120b` (120B MoE, 131K context window) as a dedicated judge model, independently configurable via `VERIFIER_MODEL` env var.
> - [x] Multi-format export verified: instantaneous PDF/MD/JSON downloads in Streamlit and auto-save to `data/reports/`. 41/41 tests passing.

---

### 🔹 Phase 4: Gateway, Memory & Evaluation 🎯 Next Up

Make the pipeline production-shaped: a resilient model gateway, layered memory, and automated evaluation.

- [ ] **LLM Gateway** (TensorZero-style) in front of the agents — GPT-4o primary, Groq fallback, with retry/timeout/circuit-breaker logic.
- [ ] **Redis short-term memory (STM)** for session/conversation state across a single research run.
- [ ] **PostgreSQL + pgvector long-term memory (LTM)** so past research topics are retrievable across sessions (HNSW/IVFFlat indexing, cosine/dot-product similarity).
- [ ] **Semantic caching** — skip the full pipeline on near-duplicate topics via similarity-threshold cache hits.
- [ ] **LangSmith tracing + LLM-as-judge scoring** — observability and a reliable automated quality rubric.

> ### 🏁 Checkpoint 4: Gateway & Memory Verification
>
> - [ ] Gateway fails over to Groq automatically when the primary provider errors or times out.
> - [ ] STM persists conversation state within a session; LTM retrieves relevant past research across sessions.
> - [ ] Semantic cache correctly short-circuits near-duplicate queries without a full re-run.
> - [ ] LangSmith trace + LLM-as-judge score is produced for every run.

---

### 🔹 Phase 5: Visual LLM Extension

Give the pipeline eyes. A Visual Analyst agent reads figures, charts, and screenshots from source material instead of treating everything as text — directly reusable across the CV research-assistant portfolio work.

- [ ] Pick a VLM (GPT-4o vision, or open-source Qwen-VL/LLaVA) and build a standalone **Visual Analyst agent** that answers questions about a single image.
- [ ] Wire the Visual Analyst into the pipeline: convert PDF pages/figures from sources into images, route the visually-relevant ones through the VLM, merge findings into the Synthesizer's input.
- [ ] Add a **visual verification step**: the Verify agent cross-checks numeric/factual claims in the written report against the actual source figures (extends the LLM-as-judge rubric to score visual faithfulness, not just text accuracy).

> ### 🏁 Checkpoint 5: Visual LLM Verification
>
> - [ ] Visual Analyst agent correctly answers a structured visual QA prompt on a standalone test image.
> - [ ] Pipeline correctly identifies which source pages are "visual enough" to route to the VLM.
> - [ ] Verify agent flags at least one deliberately mismatched numeric claim against a source figure in a test run.

---

### 🔹 Phase 6: Security & Red Teaming

Prove the guardrails hold — the part of the project that differentiates a toy demo from something defensible in an interview.

- [ ] Add **AWS Bedrock Guardrails** for input/output filtering, plus API authentication and rate limiting (token bucket / sliding window).
- [ ] Stand up a **PyRIT red-team dashboard** running jailbreak, XPIA (cross-prompt injection), crescendo, and skeleton-key attacks — including adversarial prompts hidden inside images, given the new Visual Analyst agent.

> ### 🏁 Checkpoint 6: Guardrail & Red-Team Verification
>
> - [ ] Guardrails block a documented set of jailbreak/prompt-injection test cases.
> - [ ] Red-team dashboard reports pass/fail results across all four attack classes, including at least one image-hidden-text injection attempt.
> - [ ] Rate limiting and API auth verified against unauthenticated/over-limit requests.

---

### 🔹 Phase 7: Infrastructure & Deployment

Ship it like a real platform: infrastructure as code, CI/CD, and a demo you can put in front of recruiters or a PhD panel.

- [x] **Containerization Baseline**: Production multi-stage `Dockerfile`, `docker-compose.yml` (App, Redis, pgvector), and `.dockerignore`.
- [x] **GitHub Actions CI/CD Baseline**: Automated linting (`ruff`) and multi-version Python test runner (`.github/workflows/ci.yml`).
- [ ] **Terraform**: provision the AWS stack — ECS, RDS, ElastiCache, ALB, Secrets Manager, ECR, VPC.
- [ ] **CD Deployment & Rollback**: automatic build, deploy, and rollback on failure (blue-green or equivalent).
- [ ] **Backend API (FastAPI)**:
  - [ ] `POST /api/research`: trigger async research job with topic & depth options.
  - [ ] `GET /api/research/{job_id}`: stream progress / check status.
  - [ ] `GET /api/research/{job_id}/download`: download report as PDF/Markdown (delegating to `src/utils/exporter.py`).
- [ ] End-to-end testing on the deployed system, project documentation, short demo recording, portfolio/LinkedIn writeup.

> ### 🏁 Checkpoint 7: Full System End-to-End Verification
>
> - [ ] Server starts with `python -m src.server.main` without warnings.
> - [ ] User can enter a research prompt via UI/API, view real-time progress, and download the finished report (MD/PDF/JSON).
> - [ ] Terraform apply provisions the full stack cleanly; GitHub Actions deploys and can roll back on a forced failure.

---

## 📌 Progress Tracker

| Step | Milestone | Status | Notes / Blockers |
|------|-----------|--------|-------------------|
| **Step 1** | Project Setup & Management | 🟢 Completed | Directory scaffold, pyproject.toml, ARCHITECTURE.md, CONTRIBUTING.md, config loader |
| **Step 2** | Research Tools (ArXiv + Web) | 🟢 Completed | ArXiv + Tavily / DDG tools & tests pass (5/5) |
| **Step 3** | Reasoning & Agentic Pipeline + PDF Exporter | 🟢 Completed | Groq LLM client, Planner, Synthesizer, Verifier (LLM-as-judge), ReportLab PDF/MD/JSON exporter & Streamlit downloads; 48 tests |
| **Step 4** | Gateway, Memory & Evaluation | 🎯 Next Up | LLM gateway w/ fallback, Redis STM, pgvector LTM, semantic caching, LangSmith + LLM-as-judge |
| **Step 5** | Visual LLM Extension | ⚪ Pending | VLM Visual Analyst agent, multimodal RAG wiring, visual verification |
| **Step 6** | Security & Red Teaming | ⚪ Pending | AWS Bedrock guardrails, PyRIT red-team dashboard incl. image-based attacks |
| **Step 7** | Infrastructure & Deployment | 🟡 In Progress | Dockerfile, docker-compose.yml, GitHub Actions CI workflow initialized; Terraform & FastAPI pending |