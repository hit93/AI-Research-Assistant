"""
End-to-end pipeline test for Research Assistant.
Tests: source filtering, synthesizer, verifier (claim-level), citation audit.
Topic: "ai in drug discovery"
"""
import sys
import os
import re
import textwrap

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

from src.graphs.state import ResearchGraphState
from src.graphs.nodes import plan_node, retrieve_node, synthesize_node, verify_node
from src.tools.text_cleaner import is_low_authority_or_sponsored

QUERY = "ai in drug discovery"
SEP = "=" * 70


def banner(title: str):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Planner
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 1: PLANNER")
state: ResearchGraphState = {
    "query": QUERY,
    "plan": None,
    "sources": [],
    "synthesis": [],
    "verification": None,
    "hybrid_rag": None,
    "status": "init",
    "errors": [],
    "revision_count": 0,
    "max_papers": 3,
    "max_web": 3,
    "planner_model": None,
    "synthesizer_model": None,
    "verifier_model": None,
    "improver_model": None,
}

plan_result = plan_node(state)
state.update(plan_result)
plan = state["plan"]
print(f"[OK] Plan generated: {len(plan.sub_queries)} sub-queries")
for i, sq in enumerate(plan.sub_queries):
    print(f"   [{i}] {sq.question[:85]} (type={sq.source_type})")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Retriever + Source Filtering
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 2: RETRIEVER + AUTHORITY FILTERING")
retrieve_result = retrieve_node(state)
state.update(retrieve_result)
sources = state["sources"]
print(f"[OK] Sources retained after filter_and_rank_sources: {len(sources)}")

for i, s in enumerate(sources):
    low = is_low_authority_or_sponsored(s)
    flag = "[LOW-AUTH!]" if low else "[OK]"
    print(f"   [{i:02d}] {flag} [{s.source_type:6}] {s.title[:60]}")
    print(f"          URL: {s.url_or_id[:72]}")

if state["errors"]:
    print(f"\n[WARN] Retrieval errors:")
    for e in state["errors"]:
        print(f"   - {e[:100]}")

social_leaks = [s for s in sources if is_low_authority_or_sponsored(s)]
if social_leaks:
    print(f"\n[FAIL] {len(social_leaks)} low-authority source(s) passed filtering!")
    for s in social_leaks:
        print(f"   - {s.url_or_id}")
else:
    print(f"\n[PASS] Zero low-authority/social media sources in final list.")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Synthesizer
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 3: SYNTHESIZER")
synth_result = synthesize_node(state)
state.update(synth_result)
synthesis = state["synthesis"]
print(f"[OK] Sections synthesized: {len(synthesis)}")

oob_count = 0
for sec in synthesis:
    idx_str = ", ".join(f"[{i}]" for i in sec.source_indices) or "none"
    print(f"\n  Section: {sec.heading}")
    print(f"    Declared sources: {idx_str}")
    preview = sec.content[:130].replace("\n", " ")
    print(f"    Preview:          {preview}...")

    for match in re.findall(r"\[(\d+)\]", sec.content):
        idx = int(match)
        if idx >= len(sources):
            print(f"    [FAIL] OOB citation [{idx}] — only {len(sources)} sources available!")
            oob_count += 1

if oob_count == 0:
    print(f"\n[PASS] All inline citations are in-bounds (0..{len(sources)-1}).")
else:
    print(f"\n[FAIL] {oob_count} out-of-bounds citation(s) detected!")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Verifier (claim-level)
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 4: VERIFIER (CLAIM-LEVEL)")
verify_result = verify_node(state)
state.update(verify_result)
verification = state["verification"]

print(f"  Score:     {verification.overall_score}/10")
print(f"  Approved:  {verification.is_approved}")
print(f"  Judge ran: {verification.judge_ran}")
print(f"  Summary:   {verification.summary[:250]}")

if verification.issues:
    print(f"\n  Issues ({len(verification.issues)} total):")
    for issue in verification.issues:
        sev_icon = "[HIGH]" if issue.severity == "high" else "[LOW] "
        print(f"\n  {sev_icon} Section: '{issue.section_heading}'")
        print(f"     Issue:      {textwrap.fill(issue.issue, 68, subsequent_indent='                 ')}")
        print(f"     Suggestion: {textwrap.fill(issue.suggestion, 68, subsequent_indent='                 ')}")
else:
    print("\n  [PASS] No issues flagged by verifier.")

# ─────────────────────────────────────────────────────────────────────────────
# FINAL VERDICT
# ─────────────────────────────────────────────────────────────────────────────
banner("FINAL VERDICT")
score = verification.overall_score
high_count = sum(1 for i in verification.issues if i.severity == "high")
low_count  = sum(1 for i in verification.issues if i.severity == "low")

if verification.is_approved and score >= 8:
    verdict = "APPROVED"
elif score >= 5:
    verdict = "NEEDS REVISION — refiner would be triggered"
else:
    verdict = "REJECTED — severe issues"

print(f"  Verdict:              {verdict}")
print(f"  Score:                {score}/10")
print(f"  High-severity issues: {high_count}")
print(f"  Low-severity issues:  {low_count}")
print(f"  Total sources:        {len(sources)}")
print(f"  Total sections:       {len(synthesis)}")
print(f"  OOB citations:        {oob_count}")
print(f"  Social-media leaks:   {len(social_leaks)}")

if state.get("errors"):
    print(f"\n  Pipeline errors: {len(state['errors'])}")
    for e in state["errors"]:
        print(f"    - {e[:110]}")
