#!/usr/bin/env python3
"""Bewerbungs-Agent CLI – generate job applications from a URL + CV."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from collections import Counter

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

ROOT_DIR = Path(__file__).parent


@click.group()
def cli():
    """Bewerbungs-Agent – Multi-Agent Job Application System powered by Claude."""


# ── apply subcommand ──────────────────────────────────────────────────────────

@cli.command("apply")
@click.option("--url", required=True, help="URL of the job posting.")
@click.option(
    "--cv",
    required=False,
    default=None,
    type=click.Path(dir_okay=False),
    help="Path to CV (.md or .pdf). Defaults to CV-Input.md in project root.",
)
@click.option(
    "--output",
    default="./output",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Output directory for the generated Markdown.",
)
@click.option(
    "--lang",
    default=None,
    type=click.Choice(["de", "en"]),
    help="Override language detection (auto by default).",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model to use.",
)
@click.option("--verbose", is_flag=True, help="Show detailed agent reasoning.")
@click.option("--open", "open_pdf", is_flag=True, help="Open the Markdown file after generation.")
def apply_cmd(url: str, cv: str | None, output: str, lang: str | None, model: str, verbose: bool, open_pdf: bool):
    """Generate a tailored job application (cover letter + CV) as Markdown."""

    if cv is None:
        cv = str(ROOT_DIR / "CV-Input.md")

    console.print(
        Panel(
            "[bold]Bewerbungs-Agent[/bold]\n"
            "Multi-Agent Job Application System",
            subtitle="powered by Claude",
            border_style="blue",
        )
    )

    try:
        from agents.orchestrator import run
    except ImportError as e:
        console.print(f"[red]Import error:[/red] {e}")
        console.print("Run: [cyan]pip install -r requirements.txt[/cyan]")
        sys.exit(1)

    try:
        pdf_path = run(
            job_url=url,
            cv_path=cv,
            output_dir=Path(output),
            model=model,
            lang_override=lang,
            verbose=verbose,
        )
    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted.[/yellow]")
        sys.exit(130)

    if open_pdf:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(pdf_path)], check=True)
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(pdf_path)], check=True)
            else:
                subprocess.run(["start", str(pdf_path)], shell=True, check=True)
        except Exception as e:
            console.print(f"[yellow]Could not open PDF:[/yellow] {e}")


# ── score subcommand ──────────────────────────────────────────────────────────

@cli.command("score")
@click.option("--url", required=True, help="URL of the job posting.")
@click.option(
    "--cv",
    required=False,
    default=None,
    type=click.Path(dir_okay=False),
    help="Path to CV (.md or .pdf). Defaults to CV-Input.md in project root.",
)
@click.option(
    "--lang",
    default=None,
    type=click.Choice(["de", "en"]),
    help="Override language detection (auto by default).",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model to use.",
)
@click.option("--verbose", is_flag=True, help="Show detailed agent reasoning.")
def score_cmd(url: str, cv: str | None, lang: str | None, model: str, verbose: bool):
    """Berechne den Fit-Score für eine Stelle ohne Bewerbungsunterlagen zu erstellen."""

    if cv is None:
        cv = str(ROOT_DIR / "CV-Input.md")

    console.print(
        Panel(
            "[bold]Bewerbungs-Agent — Score-Fit[/bold]\n"
            "Schnelle Bewertung ohne Dokumentengenerierung",
            subtitle="powered by Claude",
            border_style="blue",
        )
    )

    try:
        from agents.score_orchestrator import run
    except ImportError as e:
        console.print(f"[red]Import error:[/red] {e}")
        console.print("Run: [cyan]pip install -r requirements.txt[/cyan]")
        sys.exit(1)

    try:
        result = run(
            job_url=url,
            cv_path=cv,
            model=model,
            lang_override=lang,
            verbose=verbose,
        )
    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted.[/yellow]")
        sys.exit(130)

    _print_score_report(result)


def _print_score_report(result: dict) -> None:
    """Render the score report to the console."""
    job_title = result["job_title"]
    company = result["company"]
    fit_score = result["fit_score"]
    recommendation = result["recommendation"]
    recommendation_reason = result["recommendation_reason"]
    top_arguments = result["top_arguments"]
    gap_notes = result["gap_notes"]
    requirements_mapped = result["requirements_mapped"]

    # Header panel
    console.print()
    console.print(
        Panel(
            f"[bold]Score-Fit: {job_title} @ {company}[/bold]",
            border_style="blue",
        )
    )

    # Fit-Score with color
    score_color = "green" if fit_score >= 70 else "yellow" if fit_score >= 45 else "red"
    console.print()
    console.print(
        f"  Fit-Score: [bold {score_color}]{fit_score:.0f} / 100[/bold {score_color}]"
        f"   →   [bold]{recommendation}[/bold]"
    )
    console.print()

    # Requirements breakdown table
    counts: Counter = Counter()
    for req in requirements_mapped:
        counts[req.category] += 1

    category_order = ["direkt", "übersetzbar", "lücke", "ko_luecke_kompensiert", "ko_luecke_unkompensierbar"]
    category_labels = {
        "direkt": "direkt",
        "übersetzbar": "übersetzbar",
        "lücke": "lücke",
        "ko_luecke_kompensiert": "ko_kompensiert",
        "ko_luecke_unkompensierbar": "ko_unkompensierbar",
    }
    category_colors = {
        "direkt": "green",
        "übersetzbar": "cyan",
        "lücke": "yellow",
        "ko_luecke_kompensiert": "magenta",
        "ko_luecke_unkompensierbar": "red",
    }

    table = Table(title="Anforderungen", show_header=True, header_style="bold")
    table.add_column("Kategorie", style="bold", min_width=18)
    table.add_column("", min_width=20)
    table.add_column("Anzahl", justify="right", min_width=6)

    max_count = max(counts.values(), default=1)
    bar_max = 12

    for cat in category_order:
        count = counts.get(cat, 0)
        if count == 0:
            continue
        label = category_labels[cat]
        color = category_colors[cat]
        bar_len = max(1, round(count / max_count * bar_max))
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        table.add_row(label, bar, str(count))

    console.print(table)
    console.print()

    # Top arguments
    if top_arguments:
        console.print("  [bold]Top-Argumente:[/bold]")
        for arg in top_arguments:
            console.print(f"    [green]•[/green]  {arg}")
        console.print()

    # Gap notes
    if gap_notes:
        console.print("  [bold]Lücken:[/bold]")
        for note in gap_notes:
            console.print(f"    [yellow]⚠[/yellow]  {note}")
        console.print()

    # Recommendation reason
    console.print(
        Panel(
            f"[italic]{recommendation_reason}[/italic]",
            title="Empfehlung",
            border_style=score_color,
        )
    )


if __name__ == "__main__":
    cli()
