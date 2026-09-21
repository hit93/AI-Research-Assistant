"""Multi-Format Research Report Exporter.

Supports exporting ResearchResult instances to:
- Markdown (.md)
- PDF (.pdf) with professional typography, headers, citations, and quality score badges
- JSON (.json) for machine-readable storage
- Automated persistence to data/reports/
"""

import html
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.models.schemas import ResearchResult


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert arbitrary text into a clean filesystem slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    slug = text.strip("-")
    return slug[:max_length] if slug else "research-report"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw 'Page X of Y' in footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer divider line
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(40, 35, letter[0] - 40, 35)

        # Left footer: Document info
        self.drawString(40, 22, "Technical Research Report | AI Research Assistant")

        # Right footer: Page numbers
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 40, 22, page_str)
        self.restoreState()


def export_to_markdown(result: ResearchResult) -> str:
    """Export a ResearchResult to GitHub-Flavored Markdown with claim-level verification audit and transparency header."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Transparency header metrics
    full_text_count = sum(1 for s in result.sources if getattr(s, "has_full_text", False))
    abstract_only_count = len(result.sources) - full_text_count
    subquery_count = len(result.plan.sub_queries) if result.plan else 0

    v = result.verification
    claims_verified = len(v.claims) if (v and v.claims) else (v.total_claims if v else 0)
    supported_pct = f"{v.supported_ratio:.1%}" if v else "N/A"
    revisions_performed = v.revisions_made if v else 0
    unresolved_count = len(v.unresolved_flags) if v else 0
    verdict_badge = "✅ PASSED (≥95% Grounded)" if (v and v.is_approved) else "⚠️ UNRESOLVED ISSUES REMAIN"

    md: list[str] = [
        f"# 🔬 Research Report: {result.query}",
        "",
        f"> **Generated:** {now_str} | **Duration:** {result.duration_seconds}s",
        f"> **Sources Analyzed:** {len(result.sources)} total ({full_text_count} full-text body, {abstract_only_count} abstract/snippet-only)",
        f"> **Sub-Queries Covered:** {subquery_count} | **Claims Verified:** {claims_verified} ({supported_pct} supported)",
        f"> **Revisions Performed:** {revisions_performed} | **Unresolved Flags:** {unresolved_count}",
        f"> **Verification Status:** {verdict_badge}",
    ]

    if v and v.summary:
        md.append(f"> **Evaluator Assessment:** {v.summary}")

    md.extend(["", "---", ""])

    # Table of Contents
    if result.synthesis:
        md.append("## 📑 Table of Contents")
        md.append("")
        for i, section in enumerate(result.synthesis, 1):
            anchor = section.heading.lower()
            anchor = re.sub(r"[^\w\s-]", "", anchor)
            anchor = re.sub(r"[\s]+", "-", anchor).strip("-")
            md.append(f"{i}. [{section.heading}](#{anchor})")
        md.extend(["", "---", ""])

    # Plan vs Coverage Table
    coverage_items = result.plan_coverage or (v.plan_coverage if v else [])
    if coverage_items:
        md.append("## 📋 Research Strategy & Sub-Query Coverage")
        md.append("")
        md.append("| # | Sub-Query | Target | Sources Found | Full-Text Available | Status | Notes |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, cov in enumerate(coverage_items, 1):
            sq = cov.sub_query
            stype = getattr(sq, "source_type", "both")
            q_text = getattr(sq, "question", str(sq))
            status_emoji = (
                "✅ Answered" if cov.status in ("sufficient", "Answered")
                else ("⚠️ Partial" if cov.status in ("partial", "Partial") else "❌ Gap")
            )
            entities_str = f" [Covered: {', '.join(cov.covered_entities)}]" if getattr(cov, "covered_entities", None) else ""
            notes = (cov.notes or ("Answered" if cov.status in ("sufficient", "Answered") else "Evidence gap")) + entities_str
            notes = notes.replace("|", "\\|")
            md.append(
                f"| {idx} | {q_text} | `{stype}` | {cov.sources_found_count} | {cov.full_text_count} | {status_emoji} | {notes} |"
            )
        md.extend(["", "---", ""])

    # Synthesized Sections
    md.append("## 📖 Synthesized Findings")
    md.append("")
    for section in result.synthesis:
        md.append(f"### {section.heading}")
        md.append("")
        md.append(section.content)
        md.append("")

        # Dynamically calculate referenced sources from actual in-text citations [N]
        cited_indices: set[int] = set()
        matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", section.content)
        for match in matches:
            for num_str in match.split(","):
                if num_str.strip().isdigit():
                    val = int(num_str.strip())
                    if 0 <= val < len(result.sources):
                        cited_indices.add(val)

        if cited_indices:
            refs = []
            for idx in sorted(list(cited_indices)):
                s = result.sources[idx]
                badge = "Full Text" if getattr(s, "has_full_text", False) else "Abstract"
                refs.append(f"[[{idx}] {s.title} ({badge})]({s.url_or_id})")
            md.append(f"**Referenced Sources:** {', '.join(refs)}")
            md.append("")
        md.append("")

    md.extend(["---", ""])

    # Claim-Level Verification Audit Table (Never single score badge)
    if v and v.claims:
        md.append("## 🔎 Claim-Level Verification Audit Table")
        md.append("")
        md.append("| Claim # | Section | Claim Statement | Status | Cited Source(s) | Verbatim Evidence Quote / Issue |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for c in v.claims:  # Print every claim, matching header row count
            c_text = c.claim_text.replace("|", "\\|")[:90] + ("..." if len(c.claim_text) > 90 else "")
            c_status = c.verification_status
            status_icon = "✅" if c_status == "SUPPORTED" else ("⚠️" if c_status == "PARTIAL" else ("🔍" if c_status == "UNVERIFIED" else "❌"))
            cited_str = ", ".join(f"[{i}]" for i in c.cited_source_indices) if c.cited_source_indices else "None"
            ev_quote = (
                f"\"{c.evidence_quote[:80]}...\"" if c.evidence_quote
                else ("; ".join(c.issues)[:80] if c.issues else "No verbatim evidence")
            ).replace("|", "\\|")
            md.append(f"| {c.claim_id} | {c.section_heading} | {c_text} | {status_icon} `{c_status}` | {cited_str} | {ev_quote} |")

        md.extend(["", "---", ""])

    # Explicit Unresolved Issues Section
    if v and v.unresolved_flags:
        md.append("## ⚠️ Unresolved Verification Issues")
        md.append("")
        md.append("> The following claims were flagged during adversarial verification and could not be fully grounded in retrieved source passages:")
        md.append("")
        for issue_claim in v.unresolved_flags:
            issue_detail = "; ".join(issue_claim.issues) if issue_claim.issues else "Unsupported by cited source text"
            cited_str = ", ".join(f"[{i}]" for i in issue_claim.cited_source_indices) if issue_claim.cited_source_indices else "UNCITED"
            md.append(f"- **[{issue_claim.verification_status}]** in `{issue_claim.section_heading}`: \"{issue_claim.claim_text}\"")
            md.append(f"  - *Cited*: {cited_str} | *Audit Issue*: {issue_detail}")
        md.extend(["", "---", ""])

    # Sources & Citations Section
    md.append("## 📚 Sources & Citations")
    md.append("")
    for idx, source in enumerate(result.sources):
        badge = "ArXiv Paper" if source.source_type == "arxiv" else "Web Source"
        full_text_flag = "Full Text Indexed" if getattr(source, "has_full_text", False) else "Abstract / Snippet Only"
        authors_str = f" | Authors: {', '.join(source.authors)}" if source.authors else ""
        pub_str = f" | Published: {source.published}" if source.published else ""
        tier_str = f" | Quality Tier: {getattr(source, 'source_tier', 2)}"
        md.append(
            f"**[{idx}] [{badge} - {full_text_flag}] [{source.title}]({source.url_or_id})**{authors_str}{pub_str}{tier_str}"
        )
        clean_content = source.content.replace("\n", " ").strip()
        excerpt = clean_content[:400] + ("..." if len(clean_content) > 400 else "")
        md.append(f"> {excerpt}")
        md.append("")

    return "\n".join(md)



def export_to_json(result: ResearchResult) -> str:
    """Serialize ResearchResult to pretty-printed JSON."""
    return result.model_dump_json(indent=2)


def _clean_math_text(text: str) -> str:
    """Clean up inline math / LaTeX markup like $S \\times S$ -> S × S for ReportLab compatibility."""
    text = re.sub(r"\$\\times\$", "×", text)
    text = re.sub(r"\\times", "×", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    return text


def _extract_mermaid_blocks(text: str) -> list[tuple[str, str, str]]:
    """Extract Mermaid code blocks from text.

    Returns a list of (pre_text, mermaid_source, post_text) tuples.
    Each tuple contains:
    - pre_text: text from the previous block end (or string start) up to this block
    - mermaid_source: the raw fenced block including ```mermaid ... ``` delimiters
    - post_text: text from this block end up to the next block start (or string end)

    If no Mermaid blocks are found, returns an empty list.
    """
    pattern = re.compile(r"```mermaid\n.*?```", re.DOTALL)
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    results: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        pre_start = matches[i - 1].end() if i > 0 else 0
        pre_text = text[pre_start:match.start()]
        mermaid_src = match.group(0)
        post_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        post_text = text[match.end():post_end]
        results.append((pre_text, mermaid_src, post_text))
    return results


def _parse_markdown_table_to_flowable(table_block: str, body_style: ParagraphStyle) -> Table | None:
    """Convert a Markdown table string into a styled ReportLab Table flowable."""
    lines = [l.strip() for l in table_block.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    rows: list[list[str]] = []
    for line in lines:
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            # Skip separator line like |---|---|
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            rows.append(cells)

    if not rows:
        return None

    header_style = ParagraphStyle(
        "TableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=body_style,
        fontSize=8.0,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )

    table_data = []
    for row_idx, row in enumerate(rows):
        formatted_row = []
        for cell in row:
            clean_cell = _clean_math_text(html.escape(cell))
            clean_cell = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_cell)
            clean_cell = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_cell)
            style = header_style if row_idx == 0 else cell_style
            formatted_row.append(Paragraph(clean_cell, style))
        table_data.append(formatted_row)

    num_cols = max(len(r) for r in table_data)
    col_width = 532 / max(num_cols, 1)

    t = Table(table_data, colWidths=[col_width] * num_cols)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ])
    )
    return t


def _build_callout_box(text: str, callout_style: ParagraphStyle) -> Table:
    """Build a highlighted callout box with green fill and left accent border."""
    box_style = ParagraphStyle(
        "CalloutBoxText",
        parent=callout_style,
        fontName="Helvetica",
        fontSize=9.0,
        leading=13,
        textColor=colors.HexColor("#15803d"),
    )
    clean_text = _clean_math_text(html.escape(text.lstrip(">").strip()))
    clean_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_text)
    clean_text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_text)

    p = Paragraph(clean_text, box_style)
    t = Table([[p]], colWidths=[532])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
            ("LINEBEFORE", (0, 0), (0, 0), 3.5, colors.HexColor("#22c55e")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcfce7")),
        ])
    )
    return t


def export_to_pdf(
    result: ResearchResult, output_path: str | Path | None = None
) -> bytes:
    """Export a ResearchResult into a styled, publication-ready PDF document."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=45,
    )

    base_styles = getSampleStyleSheet()

    # Custom typography & color palette
    c_primary = colors.HexColor("#0f172a")  # Slate 900
    c_secondary = colors.HexColor("#2563eb")  # Blue 600
    c_text = colors.HexColor("#334155")  # Slate 700
    c_muted = colors.HexColor("#64748b")  # Slate 500
    c_bg_box = colors.HexColor("#f8fafc")  # Slate 50
    c_border = colors.HexColor("#cbd5e1")  # Slate 300

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=c_primary,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=c_secondary,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "DocBody",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=c_text,
        spaceAfter=6,
    )

    callout_style = ParagraphStyle(
        "DocCallout",
        parent=base_styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12,
        textColor=c_muted,
        spaceAfter=4,
    )

    source_title_style = ParagraphStyle(
        "SourceTitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=c_primary,
        spaceAfter=2,
    )

    code_style = ParagraphStyle(
        "MermaidCode",
        parent=base_styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=2,
    )

    caption_style_fig = ParagraphStyle(
        "FigureCaption",
        parent=base_styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.0,
        leading=11,
        textColor=colors.HexColor("#64748b"),
        alignment=1,  # center
        spaceAfter=8,
    )

    story: list[Any] = []
    _figure_counter = 0  # tracks figure number across all sections

    # 1. Header / Title Banner Card
    safe_query = html.escape(result.query)
    banner_title_style = ParagraphStyle(
        "BannerTitle",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.white,
        alignment=0,
    )
    banner_sub_style = ParagraphStyle(
        "BannerSub",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#93c5fd"),
    )

    banner_content = [
        Paragraph(f"<b>{safe_query}</b>", banner_title_style),
        Spacer(1, 4),
        Paragraph("A Comprehensive Technical Review & Synthesis Report", banner_sub_style),
    ]
    banner_table = Table([[banner_content]], colWidths=[532])
    banner_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1e40af")),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ])
    )
    story.append(banner_table)
    story.append(Spacer(1, 8))

    # 2. Metadata Bar
    status_verdict = "APPROVED" if (result.verification and result.verification.is_approved) else "PUBLISHED REVIEW"
    meta_data = [
        [
            Paragraph(f"<b>Author:</b> AI Research Assistant", body_style),
            Paragraph(f"<b>Domain:</b> Technical Review", body_style),
            Paragraph(f"<b>Status:</b> {status_verdict}", body_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[180, 180, 172])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Executive Summary / Quality Score Badge
    if result.verification:
        v = result.verification
        status_text = "APPROVED" if v.is_approved else "REVIEW RECOMMENDED"
        status_color = colors.HexColor("#16a34a") if v.is_approved else colors.HexColor("#d97706")

        score_data = [
            [
                Paragraph("<b>Evaluation Verdict</b>", body_style),
                Paragraph(f"<font color='{status_color.hexval()}'><b>{status_text}</b></font>", body_style),
                Paragraph("<b>Quality Score</b>", body_style),
                Paragraph(f"<b>{v.overall_score} / 10</b>", body_style),
            ]
        ]
        score_table = Table(score_data, colWidths=[110, 150, 90, 82])
        score_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), c_bg_box),
                ("BOX", (0, 0), (-1, -1), 0.8, c_border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(score_table)
        if v.summary:
            safe_summary = html.escape(v.summary)
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>Evaluator Note:</b> {safe_summary}", callout_style))
        story.append(Spacer(1, 10))

    # 4. Synthesized Findings
    story.append(Paragraph("Synthesized Findings", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.0, color=c_secondary, spaceAfter=8))

    def _render_text_chunk(chunk: str) -> None:
        """Render a single text chunk (paragraph or table or callout) into story."""
        chunk = chunk.strip()
        if not chunk:
            return
        if chunk.startswith(">"):
            story.append(_build_callout_box(chunk, callout_style))
            return
        # Check for markdown table
        table_matches = list(re.finditer(r"((?:\|[^\n]+\|\n?)+)", chunk))
        if table_matches:
            last_idx = 0
            for match in table_matches:
                pre = chunk[last_idx:match.start()].strip()
                if pre:
                    safe_text = _clean_math_text(html.escape(pre))
                    safe_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe_text)
                    safe_text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", safe_text)
                    story.append(Paragraph(safe_text, body_style))
                tbl = _parse_markdown_table_to_flowable(match.group(1), body_style)
                if tbl:
                    story.append(Spacer(1, 4))
                    story.append(tbl)
                    story.append(Spacer(1, 6))
                last_idx = match.end()
            post = chunk[last_idx:].strip()
            if post:
                safe_text = _clean_math_text(html.escape(post))
                safe_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe_text)
                safe_text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", safe_text)
                story.append(Paragraph(safe_text, body_style))
        else:
            safe_text = _clean_math_text(html.escape(chunk))
            safe_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe_text)
            safe_text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", safe_text)
            story.append(Paragraph(safe_text, body_style))

    for section in result.synthesis:
        safe_heading = html.escape(section.heading)
        story.append(Paragraph(safe_heading, h2_style))

        raw_content = section.content.strip()
        mermaid_blocks = _extract_mermaid_blocks(raw_content)

        if mermaid_blocks:
            for pre_text, mermaid_src, post_text in mermaid_blocks:
                # Render pre-text
                for chunk in pre_text.split("\n\n"):
                    _render_text_chunk(chunk)

                # Render Mermaid block as styled monospace code box
                _figure_counter += 1
                inner_src = mermaid_src
                inner_src = inner_src.lstrip("```mermaid").rstrip("```").strip()
                # Escape and convert newlines for ReportLab XML
                safe_src = html.escape(inner_src).replace("\n", "<br/>")
                mermaid_table = Table(
                    [[Paragraph(safe_src, code_style)]],
                    colWidths=[532],
                )
                mermaid_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                story.append(Spacer(1, 6))
                story.append(mermaid_table)
                story.append(Paragraph(
                    f"Figure {_figure_counter}: Architecture / Flow Diagram (Mermaid)",
                    caption_style_fig,
                ))
                story.append(Spacer(1, 4))

                # Render post-text
                for chunk in post_text.split("\n\n"):
                    _render_text_chunk(chunk)
        else:
            # No Mermaid blocks — use original text/table rendering
            for chunk in raw_content.split("\n\n"):
                _render_text_chunk(chunk)

        # Cited source indices
        if section.source_indices:
            cited_names = []
            for idx in section.source_indices:
                if 0 <= idx < len(result.sources):
                    cited_names.append(f"[{idx}] {html.escape(result.sources[idx].title[:40])}...")
            if cited_names:
                story.append(
                    Paragraph(
                        f"<b>Referenced Citations:</b> {', '.join(cited_names)}",
                        callout_style,
                    )
                )
        story.append(Spacer(1, 6))

    # 4. Verification Issues (if flagged)
    if result.verification and result.verification.issues:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Quality Review & Auditor Notes", h1_style))
        story.append(HRFlowable(width="100%", thickness=0.6, color=c_border, spaceAfter=6))

        for issue in result.verification.issues:
            issue_block = [
                Paragraph(
                    f"<b>[{issue.severity.upper()}]</b> <i>{html.escape(issue.section_heading)}</i>: {html.escape(issue.issue)}",
                    body_style,
                )
            ]
            if issue.suggestion:
                issue_block.append(
                    Paragraph(f"<b>Suggestion:</b> {html.escape(issue.suggestion)}", callout_style)
                )
            story.append(KeepTogether(issue_block))
            story.append(Spacer(1, 4))

    # 5. Bibliography / Sources
    story.append(Spacer(1, 10))
    story.append(Paragraph("References & Citations", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.6, color=c_border, spaceAfter=8))

    for idx, source in enumerate(result.sources):
        badge = "ArXiv" if source.source_type == "arxiv" else "Web"
        safe_title = html.escape(source.title)
        safe_url = html.escape(source.url_or_id)
        authors_info = html.escape(", ".join(source.authors)) if source.authors else "Unknown"

        source_elements = [
            Paragraph(f"<b>[{idx}]</b> [{badge}] <b>{safe_title}</b>", source_title_style),
            Paragraph(f"<b>Authors:</b> {authors_info} &nbsp;|&nbsp; <b>URL/ID:</b> {safe_url}", callout_style),
        ]
        if source.content:
            clean_snippet = html.escape(source.content.replace("\n", " ").strip()[:400])
            source_elements.append(Paragraph(f'"{clean_snippet}..."', callout_style))

        story.append(KeepTogether(source_elements))
        story.append(Spacer(1, 6))

    # Build the document with custom canvas
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pdf_bytes)

    return pdf_bytes


def save_report(
    result: ResearchResult,
    output_dir: Path | str = "data/reports",
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """Auto-save research report to disk in markdown, HTML, PDF, and/or JSON formats.

    Args:
        result: The ResearchResult instance.
        output_dir: Target directory path (defaults to 'data/reports').
        formats: List of formats to export ('md', 'html', 'pdf', 'json'). Defaults to all 4.

    Returns:
        Dictionary mapping format string to generated Path.
    """
    if formats is None:
        formats = ["md", "html", "pdf", "json"]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(result.query)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{slug}_{timestamp}"

    saved_paths: dict[str, Path] = {}

    if "md" in formats:
        md_path = out_dir / f"{base_name}.md"
        md_content = export_to_markdown(result)
        md_path.write_text(md_content, encoding="utf-8")
        saved_paths["md"] = md_path

    if "html" in formats:
        from src.utils.html_exporter import export_to_html
        html_path = out_dir / f"{base_name}.html"
        export_to_html(result, output_path=html_path)
        saved_paths["html"] = html_path

    if "json" in formats:
        json_path = out_dir / f"{base_name}.json"
        json_content = export_to_json(result)
        json_path.write_text(json_content, encoding="utf-8")
        saved_paths["json"] = json_path

    if "pdf" in formats:
        pdf_path = out_dir / f"{base_name}.pdf"
        # Try headless HTML-to-PDF conversion first if HTML is generated
        pdf_done = False
        if "html" in saved_paths:
            from src.utils.pdf_converter import convert_html_to_pdf
            pdf_done = convert_html_to_pdf(saved_paths["html"], pdf_path)
        if not pdf_done:
            export_to_pdf(result, output_path=pdf_path)
        saved_paths["pdf"] = pdf_path

    return saved_paths
