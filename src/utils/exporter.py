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
        self.drawString(40, 22, "AI Research Assistant | Verified Academic Report")

        # Right footer: Page numbers
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 40, 22, page_str)
        self.restoreState()


def export_to_markdown(result: ResearchResult) -> str:
    """Export a ResearchResult to GitHub-Flavored Markdown."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md: list[str] = [
        f"# 🔬 Research Report: {result.query}",
        "",
        f"> **Generated:** {now_str} | **Duration:** {result.duration_seconds}s | **Sources Analyzed:** {len(result.sources)}",
    ]

    if result.verification:
        v = result.verification
        badge = "✅ Approved" if v.is_approved else "⚠️ Flagged for Review"
        md.append(f"> **Verification Verdict:** {badge} (Score: {v.overall_score}/10)")
        if v.summary:
            md.append(f"> **Evaluator Assessment:** {v.summary}")

    md.extend(["", "---", ""])

    # Executive Plan Section
    if result.plan and result.plan.sub_queries:
        md.append("## 📋 Query Decomposition & Research Strategy")
        if result.plan.reasoning:
            md.append(f"*{result.plan.reasoning}*\n")
        for i, sq in enumerate(result.plan.sub_queries, 1):
            keywords = ", ".join(sq.search_keywords) if sq.search_keywords else "N/A"
            md.append(f"- **Sub-Query {i}**: {sq.question}")
            md.append(f"  - *Target*: `{sq.source_type}` | *Keywords*: {keywords}")
        md.extend(["", "---", ""])

    # Synthesized Sections
    md.append("## 📖 Synthesized Findings")
    md.append("")
    for section in result.synthesis:
        md.append(f"### {section.heading}")
        md.append("")
        md.append(section.content)
        md.append("")
        if section.source_indices:
            refs = []
            for idx in section.source_indices:
                if 0 <= idx < len(result.sources):
                    s = result.sources[idx]
                    refs.append(f"[[{idx}] {s.title}]({s.url_or_id})")
            if refs:
                md.append(f"**Referenced Sources:** {', '.join(refs)}")
                md.append("")
        md.append("")

    md.extend(["---", ""])

    # Verification / Critique Section
    if result.verification and result.verification.issues:
        md.append("## 🔎 Evaluation & Fact-Check Notes")
        md.append("")
        for issue in result.verification.issues:
            md.append(
                f"- **[{issue.severity.upper()}]** `{issue.section_heading}`: {issue.issue}"
            )
            if issue.suggestion:
                md.append(f"  - *Suggestion*: {issue.suggestion}")
        md.extend(["", "---", ""])

    # Bibliography / Sources Section
    md.append("## 📚 Sources & Citations")
    md.append("")
    for idx, source in enumerate(result.sources):
        badge = "ArXiv" if source.source_type == "arxiv" else "Web"
        authors_str = f" | Authors: {', '.join(source.authors)}" if source.authors else ""
        pub_str = f" | Published: {source.published}" if source.published else ""
        md.append(
            f"**[{idx}] [{badge}] [{source.title}]({source.url_or_id})**{authors_str}{pub_str}"
        )
        # Excerpt
        clean_content = source.content.replace("\n", " ").strip()
        excerpt = clean_content[:280] + ("..." if len(clean_content) > 280 else "")
        md.append(f"> {excerpt}")
        md.append("")

    return "\n".join(md)


def export_to_json(result: ResearchResult) -> str:
    """Serialize ResearchResult to pretty-printed JSON."""
    return result.model_dump_json(indent=2)


def export_to_pdf(
    result: ResearchResult, output_path: str | Path | None = None
) -> bytes:
    """Export a ResearchResult into a styled, publication-ready PDF document.

    Args:
        result: The research result data model.
        output_path: Optional path to save the generated PDF file.

    Returns:
        The raw bytes of the generated PDF.
    """
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

    title_style = ParagraphStyle(
        "DocTitle",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=c_primary,
        alignment=0,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=c_muted,
        spaceAfter=12,
    )

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
        fontSize=9,
        leading=13,
        textColor=c_primary,
    )

    story: list[Any] = []

    # 1. Header / Title Block
    safe_query = html.escape(result.query)
    story.append(Paragraph(f"Research Report: {safe_query}", title_style))

    now_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")
    meta_text = (
        f"<b>Generated:</b> {now_str} &nbsp;|&nbsp; "
        f"<b>Duration:</b> {result.duration_seconds:.1f}s &nbsp;|&nbsp; "
        f"<b>Sources:</b> {len(result.sources)}"
    )
    story.append(Paragraph(meta_text, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_secondary, spaceAfter=10))

    # 2. Executive Summary / Quality Score Badge
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
        score_table = Table(score_data, colWidths=[110, 150, 90, 80])
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

    # 3. Synthesized Findings
    story.append(Paragraph("Synthesized Findings", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.6, color=c_border, spaceAfter=6))

    for section in result.synthesis:
        safe_heading = html.escape(section.heading)
        story.append(Paragraph(safe_heading, h2_style))

        # Split content into paragraphs for clean typography
        paragraphs = section.content.split("\n\n")
        for p_text in paragraphs:
            cleaned = p_text.strip()
            if not cleaned:
                continue
            safe_text = html.escape(cleaned)
            # Support bold markup from markdown
            safe_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe_text)
            safe_text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", safe_text)
            story.append(Paragraph(safe_text, body_style))

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
            clean_snippet = html.escape(source.content.replace("\n", " ").strip()[:200])
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
    """Auto-save research report to disk in markdown, PDF, and/or JSON formats.

    Args:
        result: The ResearchResult instance.
        output_dir: Target directory path (defaults to 'data/reports').
        formats: List of formats to export ('md', 'pdf', 'json'). Defaults to all 3.

    Returns:
        Dictionary mapping format string to generated Path.
    """
    if formats is None:
        formats = ["md", "pdf", "json"]

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

    if "json" in formats:
        json_path = out_dir / f"{base_name}.json"
        json_content = export_to_json(result)
        json_path.write_text(json_content, encoding="utf-8")
        saved_paths["json"] = json_path

    if "pdf" in formats:
        pdf_path = out_dir / f"{base_name}.pdf"
        export_to_pdf(result, output_path=pdf_path)
        saved_paths["pdf"] = pdf_path

    return saved_paths
