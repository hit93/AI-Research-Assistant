Here is the revised, concrete **`plan.md`** file. It directly integrates a **"Quality & Synthesis Remediation Phase"** that solves the 5/10 quality failures (hallucinated metrics, unrendered Mermaid syntax, missing tables, mismatched citations) and transitions to an **HTML-first / Headless export architecture**:

```markdown
# 🔬 AI Research Assistant - Master Development Roadmap

A step-by-step, checkpoint-driven blueprint for building a modular, production-ready AI Research Assistant.

**Base project:** Krish Naik — Multi-Agent AI Research Platform with AWS Guardrails, LLM Gateway, Red Teaming, STM/LTM & Semantic Caching, extended with an HTML-First Multi-Format Exporter and Visual LLM Agent.

---

## 🧭 Architecture Overview

```mermaid
flowchart TD
    User([User Query / Request]) --> UI[Streamlit UI / CLI / REST API]
    UI --> CacheCheck{"Semantic Cache Check\n(Similarity >= 0.85)"}

    CacheCheck -- "Cache Hit (0 tokens)" --> UI
    CacheCheck -- "Cache Miss" --> Orchestrator[Graph Orchestrator]

    subgraph LangGraphCore ["LangGraph StateGraph Execution Engine"]
        direction TB
        START((START)) --> PlanNode["plan_node\n(Decompose query into 3-5 sub-queries)"]
        PlanNode --> RetrieveNode["retrieve_node\n(Parallel ArXiv + Web retrieval)"]
        RetrieveNode --> SynthNode["synthesize_node\n(Grounded Structured Pydantic Synthesis)"]
        SynthNode --> VerifyNode["verify_node\n(LLM-as-Judge audit via 120B MoE)"]

        VerifyNode --> Decision{"route_after_verifier\n(Score < 8 & Revisions < Max?)"}
        Decision -- "Yes (< 8/10)" --> ImproveNode["improver (improve_node)\n(Refine ungrounded claims & citations)"]
        ImproveNode --> VerifyNode
        Decision -- "No (Approved / Max Reached)" --> END((END))
    end

    subgraph RemediationLayer ["Synthesis Grounding & Exporter Engine"]
        Validator["Schema Validator & Hallucination Pruner"]
        HTMLExport["Interactive HTML (Tailwind + Mermaid.js)"]
        PDFGen["Headless PDF Engine (Playwright / WeasyPrint)"]
    end

    subgraph GatewayMemory ["Gateway, Layered Memory & Observability"]
        Gateway["LLM Gateway\n(CircuitBreaker & Fallback Routing)"]
        STM["Redis Short-Term Memory\n(Session state & node transitions)"]
        LTM["SQLite / pgvector Long-Term Memory\n(Research archive & vector search)"]
        LangSmith["LangSmith Tracing & Evaluation"]
    end

    Orchestrator --> START
    PlanNode -.-> Gateway
    RetrieveNode --> SynthNode
    SynthNode -.-> Gateway
    VerifyNode -.-> Gateway
    ImproveNode -.-> Gateway
    END --> Validator
    Validator --> HTMLExport --> PDFGen --> UI
    END --> LTM
    END --> CacheCheck

```

---

## 📋 Step-by-Step Implementation Phases

### 🔹 Phase 1: Project Scaffolding & Environment Setup

* [x] Initialize modular folder hierarchy (`src/`, `tests/`, `config/`, `data/`).
* [x] Set up Python environment & modern packaging (`pyproject.toml`, `uv`).
* [x] Implement robust configuration management with `pydantic-settings` / `.env`.
* [x] Structured logging, Docker scaffolding, and GitHub Actions CI baseline.

> ### 🏁 Checkpoint 1: Environment & Config Verification (PASSED)
> 
> 
> * [x] Config validator script passes and environment boots cleanly.
> 
> 

---

### 🔹 Phase 2: Research Tools & Ingestion Engine

* [x] **ArXiv Research Tool**: Search papers, extract abstracts, authors, and arXiv IDs.
* [x] **Web Search Tool**: Tavily Search API with DuckDuckGo fallback.
* [x] **Document Normalization**: HTML stripping and abstract extraction.
* [x] **Unified Source Schema**: Deduplication on normalized URL and title.

> ### 🏁 Checkpoint 2: Retrieval Tools Verification (PASSED)
> 
> 
> * [x] ArXiv and Web tools return clean, parsed research documents.
> 
> 

---

### 🔹 Phase 3: Core Reasoning, Graph & Baseline PDF Export

* [x] LangChain LCEL chains (`planner_chain`, `synthesizer_chain`).
* [x] LangGraph StateGraph with closed-loop refiner (`verify_node`, `improve_node`).
* [x] Dedicated verifier judge (`openai/gpt-oss-120b`).
* [x] Initial ReportLab PDF export utility.

> ### 🏁 Checkpoint 3: Pipeline Baseline (AUDITED)
> 
> 
> * [x] Graph runs end-to-end.
> * [!] **Audit Note**: Evaluator detected hallucinations, unrendered Mermaid strings, and missing tables in ReportLab output (Score: 5/10). *Remediation scheduled in Phase 3.5.*
> 
> 

---

### 🔹 Phase 3.5: Quality Remediation & HTML-First Export

Fix root causes of 5/10 audit failures: synthetic metrics, citation mismatches, unrendered Mermaid syntax, and empty tables.

* [x] **Step 3.5.1: Strict Factual Grounding in `synthesizer_prompt`**
* Add explicit negative constraints: strictly forbid estimating numerical figures, percentages, or ROI benchmarks unless explicitly present in the source text.
* Frame diagnostic tools (e.g., script coverage) strictly as decision-support diagnostic aids rather than outcome predictors.


* [x] **Step 3.5.2: Structured Pydantic Schema for Tables & Data**
* Define `ComparativeTable` schema (`headers: List[str]`, `rows: List[TableRow]`).
* Add fallback rule: if no empirical comparative data exists in context, omit the table field instead of generating blank headers or synthetic rows.


* [x] **Step 3.5.3: Automated Citation Verification Node (`src/chains/verifier.py`)**
* Extract all in-text `[N]` references and verify against `sources[N]`.
* Prune irrelevant domain sources (e.g., discard retail pricing or generic math arXiv papers from film reports).
* Verify every cited claim directly paraphrases context; flag ungrounded statistics as `REVISE`.


* [x] **Step 3.5.4: HTML-First Export Pipeline (`src/utils/html_exporter.py`)**
* Create responsive HTML report template with Tailwind CSS.
* Native client-side Mermaid rendering via `<script src="mermaid.min.js">` (resolves raw syntax leaks).
* Add interactive references: clickable anchor links `[1]` jumping to reference cards with title tooltips.


* [x] **Step 3.5.5: Headless HTML-to-PDF Converter (`src/utils/pdf_converter.py`)**
* Implement headless conversion via Playwright or WeasyPrint (`page.pdf(format='A4', print_background=True)`).
* Replace manual ReportLab coordinate math with standard CSS `@media print` rules.



> ### 🏁 Checkpoint 3.5: Remediation Verification (PASSED)
> 
> 
> * [x] Evaluator score improves from 5/10 to $\ge 8.5/10$.
> * [x] Zero ungrounded percentages or metrics in output text.
> * [x] Flow diagrams render natively as visual charts; tables render cleanly with responsive wrapping.
> * [x] 100% of cited indices `[N]` map to relevant retrieved documents.
> 
> 

---

### 🔹 Phase 4: Gateway, Memory & Evaluation

* [x] **LLM Gateway** (`src/chains/gateway.py`): Circuit breaker, retry logic, and fallback failover.
* [x] **Redis Short-Term Memory (STM)**: Session tracking with in-memory fallback.
* [x] **Long-Term Memory (LTM)**: SQLite/pgvector persistent run archive.
* [x] **Semantic Cache**: Cosine similarity caching ($\ge 0.85$ threshold) for 0-token instant queries.
* [x] **Hybrid RAG Engine**: BM25 + dense vector cosine similarity with Reciprocal Rank Fusion (RRF).
* [x] **Automated Test Suite**: 91 unit, mock, and integration tests passing.

---

### 🔹 Phase 4.5: Factual Grounding & Citation Integrity Remediation (COMPLETED)

* [x] **Step 4.5.1: Source Authority & Domain Relevance Filtering (`src/tools/text_cleaner.py`)**
  * Auto-suppression of social media domains (`linkedin.com`, `twitter.com`, `reddit.com`) and sponsored links (`/sponsored/`, `/native-ad/`).
  * Domain keyword overlap scoring against the query to prune off-topic papers.
  * Peer-reviewed primary literature boost (+2.5 for arXiv preprints).
  * 1-to-1 context alignment: capped at top 12 authoritative sources to eliminate prompt slicing desynchronization (`sources[:10]`).

* [x] **Step 4.5.2: In-Text Citation Synchronization (`src/chains/synthesizer.py`, `src/chains/refiner.py`)**
  * Implemented `_sync_section_citations()` to automatically bind regex in-text `[N]` citations to the structured Pydantic `source_indices` list.
  * Eliminated empty `source_indices: []` issues on sections containing inline citations.

* [x] **Step 4.5.3: Claim-Level & Quantitative Fact-Checker (`src/prompts/verifier.py`, `src/chains/verifier.py`)**
  * Refocused LLM-as-judge prompt on claim-level entailment and quantitative checking.
  * Mandatory verification of every number, percentage, and baseline multiplier against source text.
  * High-severity penalty for off-domain misattributions or unbacked metrics.

* [x] **Step 4.5.4: Grounding-Enforcing Refiner (`src/prompts/refiner.py`, `src/chains/refiner.py`)**
  * Injects targeted Hybrid RAG audit passages to bridge evidence gaps.
  * Explicit instructions to delete or qualify claims flagged as unbacked or hallucinated.

* [x] **Step 4.5.5: Gemini 3.x Provider Integration & Model Catalog Update**
  * Integrated `langchain-google-genai` into `.venv` and `requirements.txt`.
  * Updated active models in `app.py` to `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.5-flash`, and `gemini-3.8-flash` (retiring deprecated `gemini-2.5-*`).
  * Supported list response text parsing in `src/chains/llm.py`.

> ### 🏁 Checkpoint 4.5: Audit & Integrity Verification (PASSED)
> 
> * [x] 91/91 unit & integration tests passing (`pytest tests/`).
> * [x] Cleaned source pool free of social media / promotional links.
> * [x] Published documentation: `PIPELINE_ARCHITECTURE.md` and `CORE_LLM_RESEARCH.md`.

---

### 🔹 Phase 4.6: Resource Optimization, Latency Slasher & Systematic Evaluator Hardening (COMPLETED)

* [x] **Step 4.6.1: Quote-in-Source Substring Verification (`src/chains/verifier.py`)**
  * A claim is marked `SUPPORTED` only if its verbatim evidence quote exists as an exact substring in the cited source text (normalized for whitespace and case).
  * If the quote is missing, empty, or not found in the source, the claim is marked `UNVERIFIED` and counted as not supported in the pass/fail ratio.

* [x] **Step 4.6.2: Single-Fact Atomic Claim Splitting & Full Audit Table (`src/chains/verifier.py`, `src/utils/exporter.py`)**
  * Split compound sentences into single-fact atomic claims during claim extraction.
  * Print every claim in the audit table without slicing (`[:30]` truncation removed); header claim counts match table row counts identically.

* [x] **Step 4.6.3: Sub-Query Answerability Verification & Targeted Retries (`src/graphs/nodes.py`)**
  * Evaluates whether retrieved sources answer each sub-query and identifies covered entities (vendors, frameworks, benchmarks).
  * Auto-triggers a targeted retry search if partial or unanswered; records explicit evidence gaps in the report rather than hallucinated filler.

* [x] **Step 4.6.4: Irrelevant Source Pruning Across Plan & Overclaim Softening (`src/graphs/nodes.py`)**
  * Discards any source that scores below relevance threshold for every sub-query across the entire plan.
  * Regex-detects promotional buzzwords ("revolutionized", "seamlessly", "definitive", "unprecedented", "robust foundation") and softens them into objective scientific prose while attributing vendor figures ("NVIDIA states...", "IBM reports...").

* [x] **Step 4.6.5: Single-Call Batched Answerability Check (`src/graphs/nodes.py`)**
  * Replaced 6 to 9 individual LLM calls in retrieval with 1 single batched structured evaluation call (`batch_check_subquery_answerability`).

* [x] **Step 4.6.6: Selective Full-Text Scraping (`src/graphs/nodes.py`)**
  * Replaced indiscriminate 20+ URL scraping with prioritized scraping queue (arXiv preprints and top technical domains first).
  * Budget-capped to top 3 sources in Quick Mode and top 6 in Deep Mode, slashing 60% of network calls and token context bloat.

* [x] **Step 4.6.7: Research Depth Modes in UI (`app.py`)**
  * Added Execution Mode toggle in Streamlit sidebar: ⚡ Quick Briefing (~15s, 3–4 calls) vs 🔬 Deep Academic (~60s, full audit).

* [x] **Step 4.6.8: Zero-Wait Quota Fast-Failover & Sub-Query Guardrail (`src/chains/gateway.py`, `src/chains/planner.py`)**
  * `is_daily_quota_exhausted()` detects 429 daily caps instantly, bypassing retries and tripping the circuit breaker in < 1.5s rather than 35s, slashing research runtime from 260s to 70s.
  * Planner guardrail ensures `sub_queries` is never empty, eliminating 0-source starvation.

> ### 🏁 Checkpoint 4.6: Efficiency & Verification Hardening (PASSED)
> 
> * [x] 99/99 unit & integration tests passing (`uv run pytest tests/`).
> * [x] Verified zero unquoted/unverified claims marked as supported.
> * [x] Total LLM calls in standard deep run cut from ~16 to 4–5 calls.
> * [x] Runtime reduced from 260.8s to 70.2s with instant failover on limits.

---

### 🔹 Phase 5: Visual LLM Extension

Give the pipeline eyes. A Visual Analyst agent reads figures, charts, and diagrams from sources.

* [ ] Build standalone **Visual Analyst agent** (`src/chains/visual_analyst.py`) supporting GPT-4o Vision and Qwen-VL.
* [ ] PDF figure extraction: convert visual source pages to images and feed directly into the synthesizer.
* [ ] Extend LLM-as-judge rubric to cross-check numeric claims against source visual charts.

> ### 🏁 Checkpoint 5: Visual LLM Verification
> 
> * [ ] Visual Analyst accurately interprets extracted charts.
> * [ ] Verifier flags discrepancies between written claims and source charts.

---

### 🔹 Phase 6: Security & Red Teaming

* [ ] AWS Bedrock Guardrails integration (PII masking, content filtering).
* [ ] PyRIT automated red-teaming harness (prompt injection, XPIA, jailbreaks).
* [ ] Token-bucket rate limiting on API endpoints.

> ### 🏁 Checkpoint 6: Security Verification
> 
> * [ ] Zero leaked prompt structures under adversarial injection suites.

---

### 🔹 Phase 7: Infrastructure & Production Deployment

* [x] Containerization baseline (`Dockerfile`, `docker-compose.yml`).
* [ ] Terraform IaC for AWS stack (ECS Fargate, RDS PostgreSQL/pgvector, ElastiCache Redis, ALB).
* [ ] FastAPI production endpoints (`/api/research`, `/api/research/{job_id}`, `/api/research/{job_id}/download`).
* [ ] End-to-end deployment documentation and live demo recording.

---

## 📌 Progress Tracker

| Step | Milestone | Status | Notes / Blockers |
| --- | --- | --- | --- |
| **Phase 1** | Project Setup & Management | 🟢 Completed | Modular layout, packaging, config loader |
| **Phase 2** | Research Tools (ArXiv + Web) | 🟢 Completed | ArXiv + Tavily / DDG tools, text cleaner |
| **Phase 3** | Reasoning Pipeline & ReportLab Export | 🟢 Completed | StateGraph baseline, ReportLab & HTML exporters |
| **Phase 3.5** | Quality Remediation & Grounding | 🟢 Completed | Negative constraints, tables, HTML+Mermaid export |
| **Phase 4** | Gateway, Memory & Hybrid RAG | 🟢 Completed | STM, LTM, Semantic Cache, CircuitBreaker |
| **Phase 4.5** | Grounding & Citation Integrity | 🟢 Completed | Authority filtering, citation sync, claim auditor |
| **Phase 4.6** | **Resource Optimization & Evaluator Hardening** | 🟢 Completed | Quote-in-source, batch answerability, selective scraping, fast failover; 99/99 tests passing |
| **Phase 5** | Visual LLM Extension | ⚪ Queued | VLM Visual Analyst agent, figure QA |
| **Phase 6** | Security & Red Teaming | ⚪ Queued | Bedrock Guardrails, PyRIT adversarial harness |
| **Phase 7** | Cloud Infrastructure & FastAPI | 🟡 In Progress | Container ready; FastAPI & Terraform pending |
```