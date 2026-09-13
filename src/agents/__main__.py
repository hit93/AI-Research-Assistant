"""
CLI entry point for the Research Assistant.

Usage:
    python -m src.agents --topic "Quantum Computing in Drug Discovery"
    python -m src.agents --topic "Transformers in NLP" --papers 5 --web 5
"""

import argparse
import sys

# Fix Windows console encoding for emoji/unicode output
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from src.agents.orchestrator import run_research


def main():
    parser = argparse.ArgumentParser(
        description="🔬 AI Research Assistant — Full Research Pipeline (Phase 3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--topic", "-t",
        type=str,
        required=True,
        help="The research topic or question to investigate",
    )
    parser.add_argument(
        "--papers", "-p",
        type=int,
        default=3,
        help="Max ArXiv papers per sub-query (default: 3)",
    )
    parser.add_argument(
        "--web", "-w",
        type=int,
        default=3,
        help="Max web results per sub-query (default: 3)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🔬 AI RESEARCH ASSISTANT — Full Pipeline Run")
    print("=" * 70)
    print(f"\n📋 Topic: {args.topic}")
    print(f"📚 Max papers/sub-query: {args.papers}")
    print(f"🌐 Max web results/sub-query: {args.web}")
    print("-" * 70)

    # Progress callback for CLI output
    def on_progress(status: str, detail: str):
        icons = {
            "planning": "🧠",
            "planned": "✅",
            "retrieving": "🔍",
            "retrieved": "📦",
            "deduplicated": "🧹",
            "synthesizing": "⚗️",
            "synthesized": "✅",
            "complete": "🏁",
        }
        icon = icons.get(status, "▸")
        print(f"  {icon} [{status.upper()}] {detail}")

    # Run the full pipeline
    result = run_research(
        query=args.topic,
        max_papers=args.papers,
        max_web=args.web,
        on_progress=on_progress,
    )

    # ── Print the research plan ───────────────────────────────
    print("\n" + "=" * 70)
    print("📋 RESEARCH PLAN")
    print("=" * 70)
    if result.plan.reasoning:
        print(f"\nStrategy: {result.plan.reasoning}\n")
    for i, sq in enumerate(result.plan.sub_queries, 1):
        print(f"  {i}. {sq.question}")
        print(f"     Keywords: {', '.join(sq.search_keywords)}")
        print(f"     Source: {sq.source_type}")
        print()

    # ── Print gathered sources ────────────────────────────────
    print("=" * 70)
    print(f"📚 SOURCES ({len(result.sources)} gathered)")
    print("=" * 70)
    for i, source in enumerate(result.sources):
        badge = "📘" if source.source_type == "arxiv" else "🌐"
        print(f"\n  [{i}] {badge} {source.title}")
        print(f"      {source.url_or_id}")

    # ── Print synthesized report ──────────────────────────────
    print("\n" + "=" * 70)
    print("📝 SYNTHESIZED RESEARCH REPORT")
    print("=" * 70)
    for section in result.synthesis:
        print(f"\n## {section.heading}")
        print("-" * 40)
        print(section.content)
        if section.source_indices:
            refs = ", ".join(f"[{i}]" for i in section.source_indices)
            print(f"\n  Sources: {refs}")

    # ── Footer ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"⏱  Completed in {result.duration_seconds}s")
    print(f"📊 {len(result.sources)} sources | {len(result.synthesis)} sections")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
