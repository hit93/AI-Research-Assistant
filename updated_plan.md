# Claim-Verified Research Agent: Plan v2 (from scratch)

**Research question:** Does claim-level verification reduce unsupported factual claims in AI-generated research reports?

**Principle:** measure first, build second. Every phase ends with a number, not a feature.

**Serves both tracks:** PhD (question, dataset, controlled experiment) and industry (deployed, tested, secured system).

---

## Architecture (target)

```
Question → Planner → Search → Retrieve (hybrid + rerank) → Analyse → Verify claims → Write → Report
                                                              ↑            │
                                                              └── revise ──┘ (bounded loop)
Cross-cutting: LLM gateway · cache · tracing · eval harness · untrusted-content boundary
```

Explicit state machine, no unbounded agent loops: `PLAN → SEARCH → RETRIEVE → ANALYSE → VERIFY → WRITE → FINALISE`.

---

## Phase 0: Scope & Setup

* [ ] One-page spec: research question, hypotheses, groups A/B/C/D, success metrics.
* [ ] Repo with `uv`, `pydantic-settings`, pytest, CI, Docker, structured logging.
* [ ] Fix stack: one primary LLM provider + one fallback; no framework until Phase 5.

**Exit:** spec written, CI green on an empty pipeline.

## Phase 1: Evaluation First

* [ ] Gold set v0: 30 questions (grow to 100 later). Per question: expected claims, gold sources, gold evidence (section/page), known contradictions.
* [ ] Dev / held-out test split. Never tune on test.
* [ ] Metrics harness: Recall@5/10, Precision@K, MRR, nDCG, claim support rates, citation accuracy, latency, tokens, cost.

**Exit:** `python -m eval.run` prints a metrics table for any pipeline config.

## Phase 2: Baselines

* [ ] **A:** LLM only.
* [ ] **B:** LLM + RAG built by hand (parser → chunker → embeddings → vector store → retriever → LLM).
* [ ] Record baseline numbers on the dev set.

**Exit:** A vs B table exists. Everything later is compared against it.

## Phase 3: Retrieval

* [ ] Chunking: naive vs semantic.
* [ ] Retrievers: BM25 vs dense vs hybrid (RRF), plus cross-encoder reranker.
* [ ] Source filtering (domain authority, off-topic pruning, dedup).

**Exit:** best configuration chosen from measured Recall/MRR/nDCG, not by inspection.

## Phase 4: Claim-Level Verifier (the contribution)

* [ ] Extract atomic single-fact claims from the draft.
* [ ] For each claim: find candidate sources, pick evidence with source, section and page.
* [ ] Labels: `SUPPORTED`, `NOT_FOUND`, `CONTRADICTED`; `SUPPORTED` requires the evidence quote to exist verbatim in the source.
* [ ] Full audit table in the report.
* [ ] **C:** citations only. **D:** citations + verifier that deletes or qualifies flagged claims.
* [ ] Human-audit ~50 claims to measure judge-vs-human agreement.

**Exit:** verifier agreement with human labels reported.

## Phase 5: Agent Orchestration

* [ ] Implement the state machine (LangGraph is fine now) with a max revision count.
* [ ] Planner decomposes into sub-queries; check whether retrieved sources answer each one; record evidence gaps instead of filling them.
* [ ] Sub-agent roles only where they measurably help (search, analyst, critic, writer).

**Exit:** full pipeline runs end to end; Group D matches the spec.

## Phase 6: Main Experiment

* [ ] Run A/B/C/D on the held-out test set (100 questions), same model and settings.
* [ ] Report with confidence intervals and a paired significance test.
* [ ] Report cost and latency alongside quality.
* [ ] 4–6 page write-up: question, method, results, limitations, including null results.

**Exit:** a written answer to the research question. This is your PhD proposal seed and CV number.

## Phase 7: Security & Robustness

* [ ] Treat web/document text as untrusted data, never as instructions.
* [ ] Adversarial suite: prompt injection, malicious pages, fake citations, conflicting documents, missing evidence, tool failures.
* [ ] Measure attack success rate with and without the verifier.
* [ ] Optional: Bedrock Guardrails, PyRIT, rate limiting.

**Exit:** injected instructions never change agent behaviour; fake sources get flagged.

## Phase 8: Production

* [ ] LLM gateway: streaming, timeouts, retries, fallback, circuit breaker, token accounting, semantic cache.
* [ ] FastAPI (`/research`, `/research/{id}`, download), job queue, HTML → PDF export.
* [ ] Terraform on AWS (ECS Fargate, RDS + pgvector, Redis, ALB), tracing and a metrics dashboard.
* [ ] Public live demo and README with the Phase 6 results table.

**Exit:** public URL works end to end.

## Phase 9: Optional Extensions 

Knowledge graph of papers, claims and contradictions · RL/bandit search policy · single vs multi-agent comparison · visual/figure verification.

---

## Study Track (parallel, non-blocking)

LLM foundations for interviews and PhD discussions: self-attention, causal masking, tokenization, positional encoding, sampling, KV cache. Optional: a tiny Transformer from scratch over a weekend.

---

## Carry over from the old project (ideas, not code)

Quote-in-source verification, atomic claim splitting, source authority filtering, batched answerability check, quota fast-failover in the gateway, Quick vs Deep modes.

---

## Tracker

| Phase | Milestone | Status |
| --- | --- | --- |
| 0 | Scope & setup | ⚪ |
| 1 | Evaluation harness + gold set | ⚪ |
| 2 | Baselines A/B | ⚪ |
| 3 | Retrieval | ⚪ |
| 4 | Claim verifier | ⚪ |
| 5 | Orchestration | ⚪ |
| 6 | Main experiment + write-up | ⚪ |
| 7 | Security | ⚪ |
| 8 | Production + demo | ⚪ |
| 9 | Optional extensions | ⚪ |