"""PDF rendering: Jinja2 templates → WeasyPrint → PDF bytes."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from models.document import ApplicationDocuments
from utils.config import TEMPLATES_DIR


def render_pdf(documents: ApplicationDocuments, output_path: Path) -> None:
    """Render the application documents to a PDF file."""
    jinja_env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    jinja_env.filters['zip'] = zip

    context = {
        "anschreiben": documents.anschreiben,
        "lebenslauf": documents.lebenslauf,
        "referenzprojekte": documents.referenzprojekte,
        "language": documents.language,
        "job_title": documents.job_title,
        "company_name": documents.company_name,
    }

    html_string = jinja_env.get_template("combined.html").render(**context)

    # base_url is CRITICAL for resolving relative font paths
    pdf_bytes = HTML(
        string=html_string,
        base_url=str(TEMPLATES_DIR),
    ).write_pdf()

    output_path.write_bytes(pdf_bytes)
