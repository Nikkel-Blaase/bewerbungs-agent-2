"""WriterAgent: Generates cover letter (Anschreiben) template variables."""
import json
from datetime import date
from anthropic import Anthropic
from models.document import AnalyzerOutput, AnschreibenData, GapAssessmentOutput, SkillTranslationOutput
from utils.config import get_api_key, messages_create_with_retry

SUBMIT_ANSCHREIBEN_TOOL = {
    "name": "submit_anschreiben",
    "description": "Submit the final cover letter content. Call this as the last step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sender_name": {"type": "string"},
            "sender_address": {"type": "string", "description": "Full address, newlines as \\n"},
            "sender_email": {"type": "string"},
            "sender_phone": {"type": "string"},
            "sender_city": {"type": "string"},
            "date": {"type": "string", "description": "Date string, e.g. '13. März 2026'"},
            "company_name": {"type": "string"},
            "company_address": {"type": "string"},
            "contact_person": {"type": "string"},
            "salutation": {"type": "string", "description": "e.g. 'Sehr geehrte Damen und Herren,'"},
            "subject": {"type": "string", "description": "Betreff line"},
            "tagline": {
                "type": "string",
                "description": "Short professional tagline, pipe-separated keywords in uppercase, e.g. 'PRODUCT | STRATEGY | INNOVATION | LEADERSHIP'. Derived from CV strengths.",
            },
            "section_labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exactly 3 labels for body sections. DE: ['WER ICH BIN', 'WAS ICH MITBRINGE', 'WARUM [FIRMA]']. EN: ['WHO I AM', 'WHAT I CAN DO FOR YOU', 'WHY [COMPANY]'].",
            },
            "opening_paragraph": {"type": "string"},
            "body_paragraphs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exactly 3 paragraphs, matching section_labels in order.",
            },
            "closing_paragraph": {"type": "string"},
            "closing_formula": {"type": "string", "description": "e.g. 'Mit freundlichen Grüßen'"},
        },
        "required": [
            "sender_name", "sender_address", "sender_email", "sender_city",
            "date", "company_name", "salutation", "subject",
            "tagline", "section_labels",
            "opening_paragraph", "body_paragraphs", "closing_paragraph", "closing_formula",
        ],
    },
}

SYSTEM_PROMPT_DE = """Du bist ein erfahrener Bewerbungsschreiber für Quereinsteiger. Verfasse ein professionelles,
überzeugendes Anschreiben nach DIN 5008.

Falls ein Gap Assessment vorliegt: Du verwendest ausschließlich die freigegebenen Argumente aus dem Gap Assessment (top_arguments). Adressiere die gap_notes proaktiv und ehrlich im Anschreiben.

Regeln:
- Individuell auf die Stelle zugeschnitten, keine generischen Floskeln
- Zeige konkreten Mehrwert: Zahlen, Erfolge, Relevanz
- Anrede: Wenn Kontaktperson bekannt, "Sehr geehrte/r [Name]," sonst "Sehr geehrte Damen und Herren,"
- Betreff: Stelle + ggf. Referenznummer
- Ton: professionell, selbstbewusst, nicht überheblich
- Nenne konkrete Firmennamen aus dem Lebenslauf (Arbeitgeber, Kunden, Projekte)
- Kein "Ich möchte mich bewerben" oder "Hiermit schreibe ich" – direkt deklarativ formulieren

WICHTIG – Stilregeln:
- Genau 3 body_paragraphs, passend zu den section_labels in derselben Reihenfolge.
- section_labels: ['WER ICH BIN', 'WAS ICH MITBRINGE', 'WARUM [Firmenname]'] (Firmenname einsetzen).
- Tagline: 4–5 kurze Stichworte aus dem Lebenslauf, durch | getrennt, Großbuchstaben.
- Abschlussformel: "Mit freundlichen Grüßen"

K.O.-KOMPENSATION: Falls ko_compensations vorliegen, baue die fertige Formulierung
in den "WER ICH BIN"-Paragraph ein — offensiv, nicht defensiv. Die Lücke nicht
verschweigen, aber als alternativen Weg positionieren, gestützt durch konkreten Beleg.

DOMAIN-KEYWORDS: Falls covered_domain_keywords vorliegen, verwende sie gezielt
im "WARUM [FIRMA]"-Paragraph. Nicht einfach einstreuen — mit einer konkreten
Erfahrung des Kandidaten verbinden.

SEITENEINSCHRÄNKUNG – Das Anschreiben muss auf genau eine DIN-A4-Seite passen:
- opening_paragraph: genau 1 Satz ("Hiermit bewerbe ich mich für die Stelle als X bei Y.")
  Der Opening-Paragraph ist KEIN Inhaltsparagraph – nur eine direkte Bewerbungsaussage.
- Jeder body_paragraph: maximal 3–4 prägnante Sätze, kein Fülltext
- closing_paragraph: genau 1 Satz ("Ich freue mich auf die Möglichkeit, ...")
  Der Closing-Paragraph ist KEIN Inhaltsparagraph – nur ein knapper Abschluss.

Ruf am Ende submit_anschreiben auf."""

SYSTEM_PROMPT_STYLE_DE = """

SCHREIBSTIL-ANWEISUNG: Die Person hat eigene Textbeispiele bereitgestellt.
Analysiere ihre charakteristischen Formulierungen, Satzbau-Muster, Rhythmus und Wortwahl.
Übernimm diesen Stil – hebe ihn aber auf professionelles Bewerbungsdeutsch.
Kein 1:1-Kopieren von Inhalten; der persönliche Klang soll erkennbar bleiben."""

SYSTEM_PROMPT_STYLE_EN = """

WRITING STYLE INSTRUCTION: The applicant has provided personal writing samples.
Analyse their characteristic phrasing, sentence rhythm, and word choice.
Adopt this style — but elevate it to professional cover letter English.
Do not copy content verbatim; the personal voice should remain recognisable."""

SYSTEM_PROMPT_EN = """You are an expert cover letter writer for career changers. Write a professional, compelling
cover letter.

If a gap assessment is provided: Use exclusively the approved arguments from the gap assessment (top_arguments). Address the gap_notes proactively and honestly in the cover letter.

Rules:
- Tailored to the specific role — no generic phrases
- Show concrete value: numbers, achievements, relevance
- Salutation: "Dear [Name]," if known, else "Dear Hiring Team,"
- Subject: Position title
- Tone: professional, confident, not arrogant
- Reference specific company names from the CV (employers, clients, projects)
- Do NOT use "I would like to" or "I am writing to" — write declaratively and directly

IMPORTANT – Style rules:
- Exactly 3 body_paragraphs, matching section_labels in the same order.
- section_labels: ['WHO I AM', 'WHAT I CAN DO FOR YOU', 'WHY [CompanyName]'] (insert actual company name).
- Tagline: 4–5 short keywords from the CV, pipe-separated, uppercase.
- Closing formula: "Yours sincerely," or "Best regards,"

PAGE CONSTRAINT – The cover letter must fit on exactly one DIN A4 page:
- opening_paragraph: exactly 1 sentence ("I am applying for the position of X at Y.")
  The opening is NOT a content paragraph — it is a single declarative application statement.
- Each body_paragraph: maximum 3–4 concise sentences, no padding or filler
- closing_paragraph: exactly 1 sentence ("I look forward to the opportunity to...")
  The closing is NOT a content paragraph — it is a single forward-looking sentence.

Call submit_anschreiben as the final step."""

_GERMAN_MONTHS = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}


def _format_date(language: str) -> str:
    today = date.today()
    if language == "de":
        return f"{today.day}. {_GERMAN_MONTHS[today.month]} {today.year}"
    return today.strftime("%B %d, %Y")


def run(
    analysis: AnalyzerOutput,
    gap_assessment: GapAssessmentOutput | None = None,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    writing_samples: str | None = None,
    skill_translation: SkillTranslationOutput | None = None,
) -> AnschreibenData:
    client = Anthropic(api_key=get_api_key())
    language = analysis.language
    base_system = SYSTEM_PROMPT_DE if language == "de" else SYSTEM_PROMPT_EN
    style_addendum = SYSTEM_PROMPT_STYLE_DE if language == "de" else SYSTEM_PROMPT_STYLE_EN
    system = base_system + (style_addendum if writing_samples else "")

    gap_section = ""
    if gap_assessment is not None:
        ko_comp_block = ""
        if gap_assessment.ko_compensations:
            ko_comp_block = f"""
**K.O.-Kompensations-Formulierungen (in "WER ICH BIN" einbauen):**
{chr(10).join(f'- {c}' for c in gap_assessment.ko_compensations)}
"""
        domain_kw_block = ""
        if gap_assessment.covered_domain_keywords:
            domain_kw_block = f"""
**Domain-Keywords des Unternehmens (durch Profil gedeckt, in "WARUM [FIRMA]" verwenden):**
{chr(10).join(f'- {k}' for k in gap_assessment.covered_domain_keywords)}
"""
        skill_translation_block = ""
        if skill_translation and skill_translation.translations:
            lines = []
            for t in skill_translation.translations:
                warning = f" ⚠️ im Gespräch vorbereiten: {t.writer_warning}" if t.writer_warning else ""
                lines.append(
                    f"- {t.cover_letter_formulation} (Beleg: {t.evidence}, Stärke: {t.credibility}){warning}"
                )
            narrative = (
                f"\n**Narrative Klammer:** {skill_translation.narrative_frame}"
                if skill_translation.narrative_frame
                else ""
            )
            skill_translation_block = f"""
**Skill-Übersetzungen (fertige Formulierungen — direkt verwenden):**
{chr(10).join(lines)}{narrative}
"""

        gap_section = f"""
**Gap Assessment (Fit-Score: {gap_assessment.fit_score:.0f} | {gap_assessment.recommendation}):**

Top-Argumente (diese verwenden):
{chr(10).join(f'- {a}' for a in gap_assessment.top_arguments)}

Lücken (proaktiv adressieren):
{chr(10).join(f'- {n}' for n in gap_assessment.gap_notes)}
{ko_comp_block}{domain_kw_block}{skill_translation_block}"""

    prompt = f"""Write a cover letter for:

**Position:** {analysis.job_data.title} at {analysis.job_data.company}
**Location:** {analysis.job_data.location or 'not specified'}
**Contact:** {analysis.job_data.contact_person or 'not specified'}

**Applicant:** {analysis.cv_data.name}
**Email:** {analysis.cv_data.email or ''}
**Phone:** {analysis.cv_data.phone or ''}
**Location:** {analysis.cv_data.location or ''}

**Key selling points:**
{chr(10).join(f'- {p}' for p in analysis.mapping.key_selling_points)}

**Matching skills:**
{chr(10).join(f'- {s}' for s in analysis.mapping.matching_skills[:10])}

**Most relevant experience:**
{chr(10).join(f'- {e}' for e in analysis.mapping.relevant_experience[:5])}

**Job requirements summary:**
{chr(10).join(f'- {r}' for r in analysis.job_data.requirements[:10])}

**Keywords (diese Begriffe wörtlich im Anschreiben einbauen):**
{chr(10).join(f'- {k}' for k in analysis.job_data.keywords[:15])}
{gap_section}
Today's date: {_format_date(language)}
{f"""
## Schreibstil-Referenz (Originalstimme der Person)
Analysiere diese Texte und übernimm den charakteristischen Stil – professionalisiert auf Bewerbungsniveau:

---
{writing_samples}
---
""" if writing_samples else ""}
"""

    messages = [{"role": "user", "content": prompt}]
    submit_result = None

    for iteration in range(8):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=system,
            tools=[SUBMIT_ANSCHREIBEN_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [Writer] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [Writer] → {block.name}")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_anschreiben":
                submit_result = block.input
                result_content = json.dumps({"status": "submitted"})
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
        raise RuntimeError("WriterAgent did not call submit_anschreiben")

    return AnschreibenData(
        sender_name=submit_result.get("sender_name", analysis.cv_data.name),
        sender_address=submit_result.get("sender_address", analysis.cv_data.location or ""),
        sender_email=submit_result.get("sender_email", analysis.cv_data.email or ""),
        sender_phone=submit_result.get("sender_phone", analysis.cv_data.phone),
        sender_city=submit_result.get("sender_city", analysis.cv_data.location or ""),
        date=submit_result.get("date", _format_date(language)),
        company_name=submit_result.get("company_name", analysis.job_data.company),
        company_address=submit_result.get("company_address"),
        contact_person=submit_result.get("contact_person"),
        salutation=submit_result["salutation"],
        subject=submit_result["subject"],
        tagline=submit_result.get("tagline"),
        section_labels=submit_result.get("section_labels", []),
        opening_paragraph=submit_result["opening_paragraph"],
        body_paragraphs=submit_result["body_paragraphs"],
        closing_paragraph=submit_result["closing_paragraph"],
        closing_formula=submit_result["closing_formula"],
    )
