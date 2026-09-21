"""HTML-First Research Report Exporter.

Renders research reports into standalone, responsive, interactive HTML with:
- Tailwind CSS styling & dark/light-friendly design tokens
- Client-side Mermaid.js diagram rendering (no unrendered code leaks)
- Clean comparative benchmark tables
- Interactive citation superscripts [N] that link smoothly to source reference cards
"""

import html
import re
from datetime import datetime
from pathlib import Path
from src.models.schemas import ResearchResult, SynthesisSection


def _slugify(text: str, max_length: int = 50) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    slug = text.strip("-")
    return slug[:max_length] if slug else "research-report"


def _format_markdown_inline(text: str) -> str:
    """Safely format basic inline markdown (bold, italic, code, citation links)."""
    # Escape HTML first
    escaped = html.escape(text)

    # Convert citation links [N] or [N, M] to anchor links
    def _cite_repl(m: re.Match) -> str:
        indices = m.group(1).split(",")
        links = []
        for idx in indices:
            idx = idx.strip()
            links.append(f'<a href="#ref-{idx}" class="text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer underline decoration-dotted">[{idx}]</a>')
        return "<sup>" + "".join(links) + "</sup>"

    escaped = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", _cite_repl, escaped)

    # Bold: **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    # Italic: *text*
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)

    # Inline code: `text`
    escaped = re.sub(r"`(.+?)`", r'<code class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 text-sm font-mono">\1</code>', escaped)

    return escaped


def _render_section_content(section: SynthesisSection) -> str:
    """Render a section's content handling paragraphs, tables, blockquotes, and Mermaid blocks."""
    raw = section.content
    rendered_parts: list[str] = []

    # Check for Mermaid code blocks
    mermaid_pattern = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
    parts = []
    last_end = 0

    for match in mermaid_pattern.finditer(raw):
        # Text before mermaid
        pre = raw[last_end:match.start()]
        if pre.strip():
            parts.append(("text", pre))
        parts.append(("mermaid", match.group(1).strip()))
        last_end = match.end()

    tail = raw[last_end:]
    if tail.strip():
        parts.append(("text", tail))

    if not parts:
        parts = [("text", raw)]

    for ptype, content in parts:
        if ptype == "mermaid":
            # Native mermaid rendering block
            rendered_parts.append(f"""
            <div class="my-6 p-4 rounded-xl border border-indigo-100 bg-indigo-50/30 overflow-x-auto">
                <div class="text-xs font-semibold uppercase tracking-wider text-indigo-700 mb-2">Architecture Diagram</div>
                <div class="mermaid text-center">
{html.escape(content)}
                </div>
            </div>
            """)
        else:
            # Render regular markdown / paragraphs
            blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
            for b in blocks:
                if b.startswith(">"):
                    clean_b = re.sub(r"^>\s*", "", b, flags=re.MULTILINE)
                    rendered_parts.append(f"""
                    <blockquote class="my-4 border-l-4 border-indigo-500 pl-4 py-2 bg-indigo-50/50 rounded-r-lg text-slate-700 italic">
                        {_format_markdown_inline(clean_b)}
                    </blockquote>
                    """)
                elif b.startswith("|") and "|" in b[1:]:
                    # Markdown table
                    rows = [r.strip() for r in b.split("\n") if r.strip()]
                    if len(rows) >= 2:
                        header_row = rows[0]
                        headers = [h.strip() for h in header_row.split("|")[1:-1]]
                        table_html = [
                            '<div class="my-6 overflow-x-auto rounded-xl border border-slate-200 shadow-xs">',
                            '<table class="w-full text-left text-sm text-slate-600">',
                            '<thead class="bg-slate-100/75 text-xs uppercase font-semibold text-slate-700 border-b border-slate-200">',
                            '<tr>',
                        ]
                        for h in headers:
                            table_html.append(f'<th class="px-4 py-3">{_format_markdown_inline(h)}</th>')
                        table_html.append('</tr></thead><tbody class="divide-y divide-slate-200 bg-white">')

                        data_rows = rows[2:] if len(rows) > 2 and "---" in rows[1] else rows[1:]
                        for dr in data_rows:
                            cells = [c.strip() for c in dr.split("|")[1:-1]]
                            table_html.append('<tr class="hover:bg-slate-50 transition-colors">')
                            for c in cells:
                                table_html.append(f'<td class="px-4 py-3">{_format_markdown_inline(c)}</td>')
                            table_html.append('</tr>')

                        table_html.append('</tbody></table></div>')
                        rendered_parts.append("".join(table_html))
                    else:
                        rendered_parts.append(f'<p class="my-3 text-slate-700 leading-relaxed">{_format_markdown_inline(b)}</p>')
                else:
                    rendered_parts.append(f'<p class="my-3 text-slate-700 leading-relaxed">{_format_markdown_inline(b)}</p>')

    # If structured comparative_table exists on section, render it
    if section.comparative_table and section.comparative_table.headers:
        ct = section.comparative_table
        table_html = [
            '<div class="my-6 overflow-x-auto rounded-xl border border-slate-200 shadow-xs">',
        ]
        if ct.caption:
            table_html.append(f'<div class="px-4 py-2 bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-500 uppercase tracking-wide">{html.escape(ct.caption)}</div>')
        table_html.extend([
            '<table class="w-full text-left text-sm text-slate-600">',
            '<thead class="bg-slate-100 text-xs uppercase font-semibold text-slate-700 border-b border-slate-200">',
            '<tr>',
        ])
        for h in ct.headers:
            table_html.append(f'<th class="px-4 py-3">{_format_markdown_inline(h)}</th>')
        table_html.append('</tr></thead><tbody class="divide-y divide-slate-200 bg-white">')

        for r in ct.rows:
            table_html.append('<tr class="hover:bg-slate-50 transition-colors">')
            for cell in r.cells:
                table_html.append(f'<td class="px-4 py-3">{_format_markdown_inline(cell)}</td>')
            table_html.append('</tr>')

        table_html.append('</tbody></table></div>')
        rendered_parts.append("".join(table_html))

    return "\n".join(rendered_parts)


def export_to_html(result: ResearchResult, output_path: Path | str | None = None) -> str:
    """
    Export a ResearchResult to interactive, responsive HTML with Tailwind and Mermaid.js.
    """
    now_str = datetime.now().strftime("%B %d, %Y - %H:%M:%S")

    # Score badge
    score_badge = ""
    if result.verification:
        v = result.verification
        badge_color = "bg-emerald-100 text-emerald-800 border-emerald-300" if v.is_approved else "bg-amber-100 text-amber-800 border-amber-300"
        score_badge = f"""
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold border {badge_color}">
            <span>{ '✓ Approved' if v.is_approved else '⚠ Flagged' }</span>
            <span>•</span>
            <span>Score: {v.overall_score}/10</span>
        </div>
        """

    # TOC Links
    toc_items = []
    sections_html = []
    for i, sec in enumerate(result.synthesis, start=1):
        anchor_id = f"sec-{i}"
        toc_items.append(f"""
        <li>
            <a href="#{anchor_id}" class="text-slate-600 hover:text-indigo-600 transition-colors flex items-center gap-2 py-1 text-sm">
                <span class="text-indigo-500 font-mono text-xs">{i}.</span>
                <span>{html.escape(sec.heading)}</span>
            </a>
        </li>
        """)

        rendered_sec = _render_section_content(sec)
        sections_html.append(f"""
        <article id="{anchor_id}" class="scroll-mt-8 bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs mb-8">
            <h2 class="text-2xl font-bold text-slate-900 border-b border-slate-100 pb-3 mb-4 flex items-center justify-between">
                <span>{html.escape(sec.heading)}</span>
                <span class="text-xs font-mono text-slate-400 font-normal">Section {i}</span>
            </h2>
            <div class="prose prose-slate max-w-none">
                {rendered_sec}
            </div>
        </article>
        """)

    # References / Sources
    references_html = []
    for idx, s in enumerate(result.sources):
        badge = "📘 ArXiv" if s.source_type == "arxiv" else "🌐 Web"
        authors = html.escape(", ".join(s.authors)) if s.authors else "Unknown Authors"
        preview = html.escape(s.content[:300] + ("..." if len(s.content) > 300 else ""))

        references_html.append(f"""
        <div id="ref-{idx}" class="scroll-mt-8 p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition-colors">
            <div class="flex items-start justify-between gap-4">
                <div>
                    <span class="inline-block px-2 py-0.5 rounded text-xs font-mono font-bold bg-indigo-100 text-indigo-800 mb-1">[{idx}]</span>
                    <span class="text-xs text-slate-500 ml-1">{badge}</span>
                    <h4 class="font-semibold text-slate-900 text-base mt-1">
                        <a href="{html.escape(s.url_or_id)}" target="_blank" rel="noopener" class="hover:text-indigo-600 underline decoration-dotted">
                            {html.escape(s.title)}
                        </a>
                    </h4>
                    <p class="text-xs text-slate-500 mt-0.5">Authors: {authors}</p>
                </div>
            </div>
            <p class="text-xs text-slate-600 mt-2 italic line-clamp-3">"{preview}"</p>
        </div>
        """)

    full_html = f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report: {html.escape(result.query)}</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Mermaid.js CDN for Native Client-Side Diagram Rendering -->
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
    </script>
    <style>
        @media print {{
            .no-print {{ display: none !important; }}
            article {{ break-inside: avoid; page-break-inside: avoid; }}
        }}
    </style>
</head>
<body class="bg-slate-50 text-slate-900 font-sans antialiased min-h-screen">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <!-- Header -->
        <header class="mb-10 bg-white p-8 rounded-3xl border border-slate-200 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-6 mb-6">
                <div>
                    <span class="text-xs font-semibold tracking-wider text-indigo-600 uppercase">AI Research Assistant Report</span>
                    <h1 class="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">{html.escape(result.query)}</h1>
                </div>
                {score_badge}
            </div>
            <div class="flex flex-wrap items-center justify-between text-xs text-slate-500 gap-y-2">
                <div>Generated on <span class="font-medium text-slate-700">{now_str}</span></div>
                <div class="flex items-center gap-4">
                    <span>⏱ {result.duration_seconds}s</span>
                    <span>📚 {len(result.sources)} Sources</span>
                    <span>📑 {len(result.synthesis)} Sections</span>
                </div>
            </div>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-4 gap-8">
            <!-- Table of Contents Sidebar -->
            <aside class="no-print lg:col-span-1">
                <div class="sticky top-6 p-5 bg-white rounded-2xl border border-slate-200 shadow-xs">
                    <h3 class="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">Contents</h3>
                    <ul class="space-y-1">
                        {"".join(toc_items)}
                        <li>
                            <a href="#sources-section" class="text-slate-600 hover:text-indigo-600 transition-colors flex items-center gap-2 py-1 text-sm font-medium">
                                <span class="text-indigo-500 font-mono text-xs">#</span>
                                <span>References</span>
                            </a>
                        </li>
                    </ul>
                </div>
            </aside>

            <!-- Main Content -->
            <main class="lg:col-span-3">
                {"".join(sections_html)}

                <!-- References Section -->
                <section id="sources-section" class="scroll-mt-8 bg-white p-6 sm:p-8 rounded-2xl border border-slate-200 shadow-xs mb-8">
                    <h2 class="text-2xl font-bold text-slate-900 border-b border-slate-100 pb-3 mb-6">References & Sources</h2>
                    <div class="space-y-4">
                        {"".join(references_html)}
                    </div>
                </section>
            </main>
        </div>
    </div>
</body>
</html>
"""

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(full_html, encoding="utf-8")

    return full_html
