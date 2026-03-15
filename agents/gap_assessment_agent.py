"""GapAssessmentAgent: Evaluates career-changer fit for PM roles."""
import json
from urllib.parse import urlparse
from anthropic import Anthropic
from models.document import AnalyzerOutput, GapAssessmentOutput, RequirementMapping
from utils.config import get_api_key, messages_create_with_retry
from tools.scraping_tools import fetch_url, extract_text_from_html, convert_to_markdown

RESEARCH_COMPANY_WEBSITE_TOOL = {
    "name": "research_company_website",
    "description": "Fetch the company website and extract domain context: product areas, technology, customer segments, market positioning.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Company website URL (not the job posting URL)"}
        },
        "required": ["url"],
    },
}

SUBMIT_GAP_ASSESSMENT_TOOL = {
    "name": "submit_gap_assessment",
    "description": "Submit the completed gap assessment. Call this as the final step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "requirements_mapped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": ["direkt", "übersetzbar", "lücke", "ko_luecke_kompensiert", "ko_luecke_unkompensierbar"],
                        },
                        "translation_suggestion": {"type": "string"},
                        "compensation_note": {"type": "string"},
                    },
                    "required": ["requirement", "category"],
                },
            },
            "fit_score": {
                "type": "number",
                "description": "Overall fit score from 0 to 100",
            },
            "recommendation": {
                "type": "string",
                "enum": ["bewerben", "bewerben_mit_hinweis", "nicht_empfohlen"],
            },
            "recommendation_reason": {"type": "string"},
            "top_arguments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 strongest arguments for the cover letter",
            },
            "gap_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Gaps that should be addressed proactively in the cover letter",
            },
            "covered_domain_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Company domain keywords (from website research) that are covered by the candidate's profile",
            },
            "ko_compensations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ready-made offensive formulations for K.O. gaps — to be used directly in the cover letter",
            },
        },
        "required": [
            "requirements_mapped",
            "fit_score",
            "recommendation",
            "recommendation_reason",
            "top_arguments",
            "gap_notes",
        ],
    },
}

SYSTEM_PROMPT = """Du bist ein ehrlicher Karriereberater für Quereinsteiger ins Product Management.

Deine Aufgabe: Bewerte, wie gut ein Bewerber ohne klassischen PM-Hintergrund die Anforderungen einer PM-Stelle erfüllt.

## Kategorien für jede Anforderung:

**direkt** – Der Bewerber erfüllt die Anforderung bereits vollständig durch nachgewiesene Erfahrung oder Kenntnisse.

**übersetzbar** – Der Bewerber hat keine direkte PM-Erfahrung darin, aber relevante übertragbare Fähigkeiten aus anderen Bereichen. Liefere eine konkrete translation_suggestion: Welche spezifische Erfahrung aus dem Lebenslauf lässt sich wie übersetzen?

**lücke** – Die Anforderung ist weder direkt noch übersetzbar abgedeckt. Liefere eine compensation_note: Wie kann der Bewerber diese Lücke im Anschreiben proaktiv adressieren oder kompensieren (z.B. Weiterbildungsbereitschaft, komplementäre Stärke)?

**ko_luecke_kompensiert** – K.O.-Anforderung (Formulierungen wie "erfolgreich abgeschlossen", "zwingend erforderlich", "Voraussetzung", "mindestens X Jahre", "verhandlungssicher", "fließend") die der Bewerber nicht erfüllt, aber durch eine übertragbare Stärke oder alternativen Weg kompensieren kann. Liefere in ko_compensations eine fertige offensive Formulierung für das Anschreiben — ehrlich, aber als alternativen Weg positioniert, mit konkretem Beleg.

**ko_luecke_unkompensierbar** – K.O.-Anforderung ohne realistische Kompensationsmöglichkeit. Setze recommendation = "nicht_empfohlen".

## Fit-Score-Logik (0–100):
- Zähle: direkt × 3 Punkte, übersetzbar × 1.5 Punkte, lücke × 0 Punkte, ko_luecke_kompensiert × 0.5 Punkte, ko_luecke_unkompensierbar × 0 Punkte
- Normalisiere auf 100 (basierend auf maximal erreichbaren Punkten)
- Runde auf eine Dezimalstelle

## Empfehlungen:
- **bewerben** (Fit-Score ≥ 70): Starke Übereinstimmung, direkt bewerben
- **bewerben_mit_hinweis** (Fit-Score 45–69): Gute Chancen, aber Lücken müssen adressiert werden
- **nicht_empfohlen** (Fit-Score < 45 oder ko_luecke_unkompensierbar vorhanden): Zu viele kritische Lücken

## top_arguments (genau 3):
Die 3 stärksten, konkretesten Argumente für das Anschreiben — mit spezifischen Firmennamen, Zahlen und Erfolgen aus dem Lebenslauf. Diese werden direkt im Anschreiben verwendet.

## gap_notes:
Lücken, die im Anschreiben proaktiv thematisiert werden sollten — ehrlich, aber konstruktiv.

## Unternehmensrecherche (falls URL verfügbar):
Falls eine Unternehmens-URL im Prompt angegeben ist, rufe research_company_website mit der Basis-URL auf.
Extrahiere Domain-Keywords: Produktbereiche, Technologien, Kundensegmente, Marktpositionierung.
Gleiche diese Keywords mit dem Kandidatenprofil ab — nur tatsächlich gedeckte Keywords in covered_domain_keywords aufnehmen.

Rufe am Ende submit_gap_assessment auf."""


def _handle_research_company_website(url: str) -> str:
    """Fetch company website and return extracted markdown (max 3000 chars)."""
    fetch_result = fetch_url(url)
    if "error" in fetch_result:
        return json.dumps({"error": fetch_result["error"]})
    html = fetch_result.get("html", "")
    extract_result = extract_text_from_html(html, url)
    extracted_html = extract_result.get("extracted_html", html)
    md_result = convert_to_markdown(extracted_html)
    markdown = md_result.get("markdown", "")[:3000]
    return json.dumps({"markdown": markdown})


def run(
    analysis: AnalyzerOutput,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    job_url: str | None = None,
) -> GapAssessmentOutput:
    client = Anthropic(api_key=get_api_key())

    requirements_text = "\n".join(f"- {r}" for r in analysis.job_data.requirements)
    nice_to_have_text = "\n".join(f"- {r}" for r in analysis.job_data.nice_to_have)
    matching_text = "\n".join(f"- {s}" for s in analysis.mapping.matching_skills)
    missing_text = "\n".join(f"- {s}" for s in analysis.mapping.missing_skills)
    experience_text = "\n".join(
        f"- {exp.role} @ {exp.company} ({exp.period}): {'; '.join(exp.bullets[:2])}"
        for exp in analysis.cv_data.experience
    )

    # Derive base URL for company website research
    company_base_url = None
    if job_url:
        try:
            parsed = urlparse(job_url)
            company_base_url = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    url_hint = f"\n\n**Unternehmens-URL für Recherche:** {company_base_url}" if company_base_url else ""

    prompt = f"""Bewerte diese Bewerbung als Quereinsteiger ins Product Management.

**Stelle:** {analysis.job_data.title} bei {analysis.job_data.company}

**Anforderungen (must-have):**
{requirements_text}

**Nice-to-have:**
{nice_to_have_text}

**Bewerber:** {analysis.cv_data.name}
**Skills (Match):** {matching_text}
**Skills (Lücken):** {missing_text}

**Berufserfahrung:**
{experience_text}

**Ausbildung:**
{chr(10).join(f"- {edu.degree} @ {edu.institution} ({edu.period})" for edu in analysis.cv_data.education)}

**Bestehende Einschätzung (Analyzer):**
Key Selling Points: {chr(10).join(f'- {p}' for p in analysis.mapping.key_selling_points)}
{url_hint}"""

    messages = [{"role": "user", "content": prompt}]
    submit_result = None

    tools = [RESEARCH_COMPANY_WEBSITE_TOOL, SUBMIT_GAP_ASSESSMENT_TOOL]

    for iteration in range(8):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [GapAssessment] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [GapAssessment] → {block.name}")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_gap_assessment":
                submit_result = block.input
                result_content = json.dumps({"status": "submitted"})
            elif block.name == "research_company_website":
                result_content = _handle_research_company_website(block.input.get("url", ""))
            else:
                result_content = json.dumps({"error": f"Unknown tool: {block.name}"})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_content,
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    if submit_result is None:
        raise RuntimeError("GapAssessmentAgent did not call submit_gap_assessment")

    requirements_mapped = [
        RequirementMapping(
            requirement=r["requirement"],
            category=r["category"],
            translation_suggestion=r.get("translation_suggestion"),
            compensation_note=r.get("compensation_note"),
        )
        for r in submit_result.get("requirements_mapped", [])
    ]

    return GapAssessmentOutput(
        requirements_mapped=requirements_mapped,
        fit_score=float(submit_result["fit_score"]),
        recommendation=submit_result["recommendation"],
        recommendation_reason=submit_result["recommendation_reason"],
        top_arguments=submit_result.get("top_arguments", []),
        gap_notes=submit_result.get("gap_notes", []),
        covered_domain_keywords=submit_result.get("covered_domain_keywords", []),
        ko_compensations=submit_result.get("ko_compensations", []),
    )
