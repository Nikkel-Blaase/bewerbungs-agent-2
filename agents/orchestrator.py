"""Orchestrator: Coordinates the full application pipeline."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from slugify import slugify
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from agents import scraper_agent, analyzer_agent, gap_assessment_agent, skill_translation_agent, writer_agent, cv_agent, referenz_agent
from models.document import ApplicationDocuments
from pdf.renderer import render_pdf
from utils.config import OUTPUT_DIR, ROOT_DIR, WRITING_SAMPLES_DIR

console = Console()


def run(
    job_url: str,
    cv_path: str,
    output_dir: Path = OUTPUT_DIR,
    model: str = "claude-sonnet-4-6",
    lang_override: str | None = None,
    verbose: bool = False,
) -> Path:
    """Run the full pipeline and return the path to the generated PDF."""

    cv_markdown = Path(cv_path).read_text(encoding="utf-8")
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Load writing samples (optional)
    writing_samples_text = None
    sample_files = sorted(
        f for f in WRITING_SAMPLES_DIR.iterdir()
        if f.is_file() and f.suffix in (".txt", ".md") and not f.name.startswith(".")
    )
    if sample_files:
        parts = []
        for f in sample_files:
            parts.append(f"### {f.name}\n{f.read_text(encoding='utf-8').strip()}")
        writing_samples_text = "\n\n".join(parts)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        _FAST_MODEL = "claude-haiku-4-5-20251001"

        # ── Step 1: Scrape ────────────────────────────────────────────────────
        task_scrape = progress.add_task("[1/6] Scraping job posting...", total=None)
        try:
            scraper_output = scraper_agent.run(job_url, model=_FAST_MODEL, verbose=verbose)
        except RuntimeError as e:
            progress.stop()
            console.print(f"[red]Scraping failed:[/red] {e}")
            raise
        progress.update(task_scrape, description=f"[1/6] Scraped: {scraper_output.job_title} @ {scraper_output.company_name}", completed=1, total=1)

        # ── Step 2: Analyze ───────────────────────────────────────────────────
        task_analyze = progress.add_task("[2/6] Analyzing job & CV...", total=None)
        analysis = analyzer_agent.run(
            scraper_output.raw_markdown, cv_markdown, model=model, verbose=verbose
        )
        if lang_override:
            analysis.language = lang_override
        progress.update(task_analyze, description=f"[2/6] Language: {analysis.language} | Fit analyzed", completed=1, total=1)

        if verbose:
            console.print(f"\n  Language: [bold]{analysis.language}[/bold]")
            console.print(f"  Matching skills: {', '.join(analysis.mapping.matching_skills[:5])}")
            console.print(f"  Key selling points: {len(analysis.mapping.key_selling_points)}")

        # ── Step 3: Gap Assessment ────────────────────────────────────────────
        task_gap = progress.add_task("[3/6] Gap Assessment...", total=None)
        gap_assessment = gap_assessment_agent.run(analysis, model=model, verbose=verbose, job_url=job_url)
        progress.update(
            task_gap,
            description=f"[3/6] Fit-Score: {gap_assessment.fit_score:.0f} | {gap_assessment.recommendation}",
            completed=1,
            total=1,
        )

        if verbose:
            console.print(f"\n  Fit-Score: [bold]{gap_assessment.fit_score:.0f}[/bold]")
            console.print(f"  Empfehlung: {gap_assessment.recommendation}")
            console.print(f"  Top-Argumente: {len(gap_assessment.top_arguments)}")

        # ── Step 4: Skill Translation ─────────────────────────────────────────
        task_skill = progress.add_task("[4/6] Translating transferable skills...", total=None)
        skill_translation = skill_translation_agent.run(analysis, gap_assessment, model=model, verbose=verbose)
        progress.update(
            task_skill,
            description=f"[4/6] {len(skill_translation.translations)} translations | {skill_translation.strong_count} stark",
            completed=1,
            total=1,
        )

        if verbose:
            console.print(f"\n  Skill-Übersetzungen: [bold]{len(skill_translation.translations)}[/bold]")
            console.print(f"  Stark: {skill_translation.strong_count} | Riskant: {len(skill_translation.risky_translations)}")
            if skill_translation.narrative_frame:
                console.print(f"  Narrative: {skill_translation.narrative_frame}")

        # ── Step 5: Write Anschreiben + CV + Referenz in parallel ────────────
        task_write = progress.add_task("[5/6] Generating documents (parallel)...", total=None)

        anschreiben_data = None
        lebenslauf_data = None
        referenzprojekte_data = None
        errors = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_writer = executor.submit(writer_agent.run, analysis, gap_assessment, model, verbose, writing_samples_text, skill_translation)
            future_cv = executor.submit(cv_agent.run, analysis, gap_assessment, _FAST_MODEL, verbose)
            future_referenz = executor.submit(referenz_agent.run, analysis, gap_assessment, _FAST_MODEL, verbose)

            for future in as_completed([future_writer, future_cv, future_referenz]):
                try:
                    result = future.result()
                    if future == future_writer:
                        anschreiben_data = result
                    elif future == future_cv:
                        lebenslauf_data = result
                    else:
                        referenzprojekte_data = result
                except Exception as e:
                    errors.append(str(e))

        if errors:
            progress.stop()
            raise RuntimeError(f"Document generation failed: {'; '.join(errors)}")

        progress.update(task_write, description="[5/6] Anschreiben + Lebenslauf + Referenz generated", completed=1, total=1)

        # ── Step 6: Render PDF ────────────────────────────────────────────────
        task_pdf = progress.add_task("[6/6] Rendering PDF...", total=None)

        # Detect photo in project root
        photo_path = None
        for ext in ("jpg", "jpeg", "png"):
            candidate = ROOT_DIR / f"photo.{ext}"
            if candidate.exists():
                photo_path = str(candidate)
                break
        if photo_path and anschreiben_data:
            anschreiben_data.photo_path = photo_path

        documents = ApplicationDocuments(
            anschreiben=anschreiben_data,
            lebenslauf=lebenslauf_data,
            referenzprojekte=referenzprojekte_data,
            language=analysis.language,
            job_title=analysis.job_data.title,
            company_name=analysis.job_data.company,
        )

        slug = slugify(f"{analysis.job_data.company}-{analysis.job_data.title}")[:60]
        score_str = f"score{gap_assessment.fit_score:.0f}"
        output_path = output_dir / f"{slug}_{score_str}_application.pdf"

        render_pdf(documents, output_path)
        progress.update(task_pdf, description=f"[6/6] PDF saved: {output_path.name}", completed=1, total=1)

    console.print(f"\n[bold green]Done![/bold green] Application saved to: [cyan]{output_path}[/cyan]")

    score = gap_assessment.fit_score
    color = "green" if score >= 70 else "yellow" if score >= 40 else "red"
    console.print(Panel(
        f"[bold {color}]Fit-Score: {score:.0f} / 100[/bold {color}]\n"
        f"Empfehlung: {gap_assessment.recommendation}\n"
        f"{gap_assessment.recommendation_reason}",
        title="Gap Assessment",
        border_style=color,
    ))

    return output_path
