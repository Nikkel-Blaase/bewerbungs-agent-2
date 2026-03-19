"""Orchestrator: Coordinates the full application pipeline (4 LLM calls)."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from slugify import slugify
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from agents import mega_analysis_agent, cv_referenz_agent, writer_agent
from learning.application_log import save_application, build_lessons_context
from models.document import ApplicationDocuments
from tools.scraping_tools import fetch_url, extract_text_from_html, convert_to_markdown, fetch_company_context
from tools.analysis_tools import detect_language
from utils.config import OUTPUT_DIR, ROOT_DIR, WRITING_SAMPLES_DIR, JOBS_DIR
from utils.render_markdown import render_markdown

console = Console()

_HAIKU = "claude-haiku-4-5-20251001"


def _python_scrape(job_url: str) -> tuple[str, str, str]:
    """Pure Python scraping — zero LLM calls. Returns (job_markdown, slug, html)."""
    fetch_result = fetch_url(job_url)
    if "error" in fetch_result:
        raise RuntimeError(f"Failed to fetch job URL: {fetch_result['error']}")
    html = fetch_result["html"]
    extract_result = extract_text_from_html(html, job_url)
    md_result = convert_to_markdown(extract_result["extracted_html"])
    job_markdown = md_result["markdown"]

    # Save to jobs/ for reuse
    raw_slug = job_url.split("?")[0].rstrip("/").split("/")[-1]
    slug = slugify(raw_slug or "job")[:60]
    job_file = JOBS_DIR / f"{slug}.md"
    job_file.write_text(job_markdown, encoding="utf-8")

    return job_markdown, slug, html


def run(
    job_url: str,
    cv_path: str,
    output_dir: Path = OUTPUT_DIR,
    model: str = "claude-sonnet-4-6",
    lang_override: str | None = None,
    verbose: bool = False,
) -> Path:
    """Run the full pipeline and return the path to the generated Markdown file."""

    cv_path_obj = Path(cv_path)
    if cv_path_obj.suffix.lower() == ".pdf":
        cv_markdown = None
        cv_pdf_bytes = cv_path_obj.read_bytes()
    else:
        cv_markdown = cv_path_obj.read_text(encoding="utf-8")
        cv_pdf_bytes = None
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

        # ── Step 1: Python Pre-Processing (0 LLM calls) ───────────────────────
        task_scrape = progress.add_task("[1/4] Fetching job posting...", total=None)
        job_markdown, _slug, job_html = _python_scrape(job_url)
        lang_detected = detect_language(job_markdown)["language"]
        language = lang_override or lang_detected

        company_context = None
        try:
            company_context = fetch_company_context(job_url, job_html)
        except Exception:
            pass

        scrape_desc = f"[1/4] Fetched ({len(job_markdown)} chars, lang={language}"
        scrape_desc += ", +company research)" if company_context else ", no company research)"
        progress.update(task_scrape, description=scrape_desc, completed=1, total=1)

        # ── Step 2: Mega-Analysis (1 Sonnet call) ─────────────────────────────
        task_analyze = progress.add_task("[2/4] Mega-Analysis (job + CV + gap + skills)...", total=None)
        lessons_context = build_lessons_context()
        mega = mega_analysis_agent.run(
            job_markdown, cv_markdown, cv_pdf_bytes=cv_pdf_bytes,
            company_context=company_context, language=language, model=model, verbose=verbose,
            lessons_context=lessons_context,
        )
        if lang_override:
            mega.language = lang_override
        progress.update(
            task_analyze,
            description=(
                f"[2/4] {mega.job_data.title} @ {mega.job_data.company} "
                f"| Score: {mega.gap.fit_score:.0f} | {mega.gap.recommendation}"
            ),
            completed=1,
            total=1,
        )

        if verbose:
            console.print(f"\n  Language: [bold]{mega.language}[/bold]")
            console.print(f"  Fit-Score: [bold]{mega.gap.fit_score:.0f}[/bold] | {mega.gap.recommendation}")
            console.print(f"  Skill-Übersetzungen: {len(mega.skill_translations.translations)}")
            console.print(f"  Top-Argumente: {len(mega.gap.top_arguments)}")
            if mega.pm_archetype:
                arch = mega.pm_archetype
                console.print(f"  PM-Archetyp: [bold]{arch.primary}[/bold] (Konfidenz: {arch.confidence})")
            if lessons_context:
                console.print(f"  [Lernhistorie] Kontext geladen ({len(lessons_context)} chars)")

        # ── Step 3: Parallel document generation (2 calls) ───────────────────
        task_write = progress.add_task("[3/4] Generating documents (parallel)...", total=None)

        anschreiben_data = None
        lebenslauf_data = None
        referenzprojekte_data = None
        errors = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_writer = executor.submit(
                writer_agent.run, mega, model, verbose, writing_samples_text, lessons_context
            )
            future_cv_ref = executor.submit(
                cv_referenz_agent.run, mega, _HAIKU, verbose
            )

            for future in as_completed([future_writer, future_cv_ref]):
                try:
                    result = future.result()
                    if future == future_writer:
                        anschreiben_data = result
                    else:
                        lebenslauf_data, referenzprojekte_data = result
                except Exception as e:
                    errors.append(str(e))

        if errors:
            progress.stop()
            raise RuntimeError(f"Document generation failed: {'; '.join(errors)}")

        progress.update(
            task_write,
            description="[3/4] Anschreiben + Lebenslauf + Referenz generated",
            completed=1,
            total=1,
        )

        # ── Step 4: Render Markdown ───────────────────────────────────────────
        task_render = progress.add_task("[4/4] Rendering Markdown...", total=None)

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
            language=mega.language,
            job_title=mega.job_data.title,
            company_name=mega.job_data.company,
        )

        company_slug = slugify(f"{mega.job_data.company}-{mega.job_data.title}")[:60]
        score_str = f"score{mega.gap.fit_score:.0f}"
        output_path = output_dir / f"{company_slug}_{score_str}_application.md"

        render_markdown(documents, output_path, language=mega.language)
        save_application(mega, job_url)
        progress.update(
            task_render,
            description=f"[4/4] Saved: {output_path.name}",
            completed=1,
            total=1,
        )

    console.print(f"\n[bold green]Done![/bold green] Application saved to: [cyan]{output_path}[/cyan]")

    score = mega.gap.fit_score
    color = "green" if score >= 70 else "yellow" if score >= 40 else "red"

    archetype_line = ""
    if mega.pm_archetype:
        archetype_line = f"PM-Archetyp: {mega.pm_archetype.primary.capitalize()} (Konfidenz: {mega.pm_archetype.confidence})\n"

    console.print(Panel(
        f"[bold {color}]Fit-Score: {score:.0f} / 100[/bold {color}]\n"
        f"{archetype_line}"
        f"Empfehlung: {mega.gap.recommendation}\n"
        f"{mega.gap.recommendation_reason}",
        title="Gap Assessment",
        border_style=color,
    ))

    return output_path
