"""Score Orchestrator: Runs only Steps 1–3 (Scrape → Analyze → Gap Assessment)."""
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from agents import scraper_agent, analyzer_agent, gap_assessment_agent

console = Console()

_FAST_MODEL = "claude-haiku-4-5-20251001"


def run(
    job_url: str,
    cv_path: str,
    model: str = "claude-sonnet-4-6",
    lang_override: str | None = None,
    verbose: bool = False,
) -> dict:
    """Run Steps 1–3 and return a score report dict (no PDF)."""

    cv_markdown = Path(cv_path).read_text(encoding="utf-8")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        # ── Step 1: Scrape ────────────────────────────────────────────────────
        task_scrape = progress.add_task("[1/3] Scraping job posting...", total=None)
        try:
            scraper_output = scraper_agent.run(job_url, model=_FAST_MODEL, verbose=verbose)
        except RuntimeError as e:
            progress.stop()
            console.print(f"[red]Scraping failed:[/red] {e}")
            raise
        progress.update(
            task_scrape,
            description=f"[1/3] Scraped: {scraper_output.job_title} @ {scraper_output.company_name}",
            completed=1,
            total=1,
        )

        # ── Step 2: Analyze ───────────────────────────────────────────────────
        task_analyze = progress.add_task("[2/3] Analyzing job & CV...", total=None)
        analysis = analyzer_agent.run(
            scraper_output.raw_markdown, cv_markdown, model=model, verbose=verbose
        )
        if lang_override:
            analysis.language = lang_override
        progress.update(
            task_analyze,
            description=f"[2/3] Language: {analysis.language} | Fit analyzed",
            completed=1,
            total=1,
        )

        # ── Step 3: Gap Assessment ────────────────────────────────────────────
        task_gap = progress.add_task("[3/3] Gap Assessment...", total=None)
        gap_assessment = gap_assessment_agent.run(
            analysis, model=model, verbose=verbose, job_url=job_url
        )
        progress.update(
            task_gap,
            description=f"[3/3] Fit-Score: {gap_assessment.fit_score:.0f} | {gap_assessment.recommendation}",
            completed=1,
            total=1,
        )

    return {
        "job_title": analysis.job_data.title,
        "company": analysis.job_data.company,
        "fit_score": gap_assessment.fit_score,
        "recommendation": gap_assessment.recommendation,
        "recommendation_reason": gap_assessment.recommendation_reason,
        "top_arguments": gap_assessment.top_arguments,
        "gap_notes": gap_assessment.gap_notes,
        "requirements_mapped": gap_assessment.requirements_mapped,
        "covered_domain_keywords": gap_assessment.covered_domain_keywords,
        "ko_compensations": gap_assessment.ko_compensations,
    }
