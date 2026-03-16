"""Score Orchestrator: Runs only Steps 1–2 (Fetch → Mega-Analysis, no documents)."""
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from agents import mega_analysis_agent
from tools.scraping_tools import fetch_url, extract_text_from_html, convert_to_markdown
from tools.analysis_tools import detect_language

console = Console()


def _python_scrape(job_url: str) -> str:
    """Pure Python scraping. Returns job_markdown."""
    fetch_result = fetch_url(job_url)
    if "error" in fetch_result:
        raise RuntimeError(f"Failed to fetch job URL: {fetch_result['error']}")
    html = fetch_result["html"]
    extract_result = extract_text_from_html(html, job_url)
    md_result = convert_to_markdown(extract_result["extracted_html"])
    return md_result["markdown"]


def run(
    job_url: str,
    cv_path: str,
    model: str = "claude-sonnet-4-6",
    lang_override: str | None = None,
    verbose: bool = False,
) -> dict:
    """Run Steps 1–2 and return a score report dict (no documents generated)."""

    cv_path_obj = Path(cv_path)
    if cv_path_obj.suffix.lower() == ".pdf":
        cv_markdown = None
        cv_pdf_bytes = cv_path_obj.read_bytes()
    else:
        cv_markdown = cv_path_obj.read_text(encoding="utf-8")
        cv_pdf_bytes = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        # ── Step 1: Python Pre-Processing (0 LLM calls) ───────────────────────
        task_scrape = progress.add_task("[1/2] Fetching job posting...", total=None)
        job_markdown = _python_scrape(job_url)
        lang_detected = detect_language(job_markdown)["language"]
        language = lang_override or lang_detected
        progress.update(
            task_scrape,
            description=f"[1/2] Fetched ({len(job_markdown)} chars, lang={language})",
            completed=1,
            total=1,
        )

        # ── Step 2: Mega-Analysis (1 Sonnet call) ─────────────────────────────
        task_analyze = progress.add_task("[2/2] Mega-Analysis...", total=None)
        mega = mega_analysis_agent.run(
            job_markdown, cv_markdown, cv_pdf_bytes=cv_pdf_bytes, language=language, model=model, verbose=verbose
        )
        if lang_override:
            mega.language = lang_override
        progress.update(
            task_analyze,
            description=f"[2/2] Fit-Score: {mega.gap.fit_score:.0f} | {mega.gap.recommendation}",
            completed=1,
            total=1,
        )

    return {
        "job_title": mega.job_data.title,
        "company": mega.job_data.company,
        "fit_score": mega.gap.fit_score,
        "recommendation": mega.gap.recommendation,
        "recommendation_reason": mega.gap.recommendation_reason,
        "top_arguments": mega.gap.top_arguments,
        "gap_notes": mega.gap.gap_notes,
        "requirements_mapped": mega.gap.requirements_mapped,
        "covered_domain_keywords": mega.gap.covered_domain_keywords,
        "ko_compensations": mega.gap.ko_compensations,
    }
