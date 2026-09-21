"""Headless HTML-to-PDF Converter.

Converts HTML reports to print-ready PDF using Playwright (if installed)
or falls back smoothly to ReportLab rendering.
"""

from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger("utils.pdf_converter")


def convert_html_to_pdf(
    html_path: Path | str,
    output_pdf_path: Path | str,
) -> bool:
    """
    Convert an HTML file to PDF via Playwright headless Chromium.
    Returns True on success, False if Playwright is unavailable or fails.
    """
    in_path = Path(html_path).resolve()
    out_path = Path(output_pdf_path).resolve()

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        logger.info(f"Converting HTML to PDF via Playwright: {in_path} -> {out_path}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(in_path.as_uri(), wait_until="networkidle")
            # Wait for client-side Mermaid diagrams to render if present
            try:
                page.wait_for_selector(".mermaid svg", timeout=3000)
            except Exception:
                pass  # Diagram might not exist in this particular report
            page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
            )
            browser.close()
        logger.info("Playwright PDF conversion completed successfully.")
        return True
    except ImportError:
        logger.debug("Playwright not installed; skipping headless browser PDF generation.")
        return False
    except Exception as e:
        logger.warning(f"Playwright PDF conversion failed ({e}).")
        return False
