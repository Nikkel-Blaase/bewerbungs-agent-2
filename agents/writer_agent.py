"""WriterAgent: Generates cover letter (Anschreiben). Single-shot, no tool-use loop."""
import json
import re
from datetime import date
from anthropic import Anthropic
from models.document import MegaAnalysisOutput, AnschreibenData
from utils.config import get_api_key, messages_create_with_retry

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
- Gedankenstriche (—) sind im Fließtext verboten (opening_paragraph, body_paragraphs,
  closing_paragraph). Stattdessen Satzzeichen wie Punkt, Komma oder Doppelpunkt verwenden.

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

Antworte NUR mit einem validen JSON-Objekt mit genau diesen Feldern:
{
  "sender_name": "", "sender_address": "", "sender_email": "",
  "sender_phone": null, "sender_city": "", "date": "",
  "company_name": "", "company_address": null, "contact_person": null,
  "salutation": "", "subject": "", "tagline": "", "section_labels": [],
  "opening_paragraph": "", "body_paragraphs": [], "closing_paragraph": "", "closing_formula": ""
}"""

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
- Em dashes (—) are forbidden in body text (opening_paragraph, body_paragraphs,
  closing_paragraph). Use full stops, commas, or colons instead.

PAGE CONSTRAINT – The cover letter must fit on exactly one DIN A4 page:
- opening_paragraph: exactly 1 sentence ("I am applying for the position of X at Y.")
  The opening is NOT a content paragraph — it is a single declarative application statement.
- Each body_paragraph: maximum 3–4 concise sentences, no padding or filler
- closing_paragraph: exactly 1 sentence ("I look forward to the opportunity to...")
  The closing is NOT a content paragraph — it is a single forward-looking sentence.

Reply ONLY with a valid JSON object with exactly these fields:
{
  "sender_name": "", "sender_address": "", "sender_email": "",
  "sender_phone": null, "sender_city": "", "date": "",
  "company_name": "", "company_address": null, "contact_person": null,
  "salutation": "", "subject": "", "tagline": "", "section_labels": [],
  "opening_paragraph": "", "body_paragraphs": [], "closing_paragraph": "", "closing_formula": ""
}"""

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


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return json.loads(text)


def run(
    mega: MegaAnalysisOutput,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    writing_samples: str | None = None,
    lessons_context: str | None = None,
) -> AnschreibenData:
    client = Anthropic(api_key=get_api_key())
    language = mega.language
    base_system = SYSTEM_PROMPT_DE if language == "de" else SYSTEM_PROMPT_EN
    style_addendum = SYSTEM_PROMPT_STYLE_DE if language == "de" else SYSTEM_PROMPT_STYLE_EN
    system = base_system + (style_addendum if writing_samples else "")

    # Build gap section
    gap = mega.gap
    ko_comp_block = ""
    if gap.ko_compensations:
        ko_comp_block = f"""
**K.O.-Kompensations-Formulierungen (in "WER ICH BIN" einbauen):**
{chr(10).join(f'- {c}' for c in gap.ko_compensations)}
"""
    domain_kw_block = ""
    if gap.covered_domain_keywords:
        domain_kw_block = f"""
**Domain-Keywords des Unternehmens (durch Profil gedeckt, in "WARUM [FIRMA]" verwenden):**
{chr(10).join(f'- {k}' for k in gap.covered_domain_keywords)}
"""
    skill_translation_block = ""
    st = mega.skill_translations
    if st.translations:
        lines = []
        for t in st.translations:
            warning = f" im Gespräch vorbereiten: {t.writer_warning}" if t.writer_warning else ""
            lines.append(f"- {t.cover_letter_formulation} (Beleg: {t.evidence}, Stärke: {t.credibility}){warning}")
        narrative = f"\n**Narrative Klammer:** {st.narrative_frame}" if st.narrative_frame else ""
        skill_translation_block = f"""
**Skill-Übersetzungen (fertige Formulierungen — direkt verwenden):**
{chr(10).join(lines)}{narrative}
"""

    archetype_block = ""
    if mega.pm_archetype:
        arch = mega.pm_archetype
        secondary_note = f" (sekundär: {arch.secondary})" if arch.secondary else ""
        archetype_block = f"""
**PM-Archetyp des Unternehmens: {arch.primary.upper()}{secondary_note} (Konfidenz: {arch.confidence})**
{arch.reasoning}

Framing-Anweisung:
{arch.writer_hint}
"""

    gap_section = f"""
**Gap Assessment (Fit-Score: {gap.fit_score:.0f} | {gap.recommendation}):**

Top-Argumente (diese verwenden):
{chr(10).join(f'- {a}' for a in gap.top_arguments)}

Lücken (proaktiv adressieren):
{chr(10).join(f'- {n}' for n in gap.gap_notes)}
{ko_comp_block}{domain_kw_block}{skill_translation_block}{archetype_block}"""

    lessons_block = f"\n{lessons_context}\n" if lessons_context else ""

    prompt = f"""Write a cover letter for:

**Position:** {mega.job_data.title} at {mega.job_data.company}
**Location:** {mega.job_data.location or 'not specified'}
**Contact:** {mega.job_data.contact_person or 'not specified'}

**Applicant:** {mega.cv_data.name}
**Email:** {mega.cv_data.email or ''}
**Phone:** {mega.cv_data.phone or ''}
**Location:** {mega.cv_data.location or ''}

**Key selling points:**
{chr(10).join(f'- {p}' for p in mega.mapping.key_selling_points)}

**Matching skills:**
{chr(10).join(f'- {s}' for s in mega.mapping.matching_skills[:10])}

**Most relevant experience:**
{chr(10).join(f'- {e}' for e in mega.mapping.relevant_experience[:5])}

**Job requirements summary:**
{chr(10).join(f'- {r}' for r in mega.job_data.requirements[:10])}

**Keywords (diese Begriffe wörtlich im Anschreiben einbauen):**
{chr(10).join(f'- {k}' for k in mega.job_data.keywords[:15])}
{gap_section}
{lessons_block}Today's date: {_format_date(language)}
{f"""
## Schreibstil-Referenz (Originalstimme der Person)
Analysiere diese Texte und übernimm den charakteristischen Stil – professionalisiert auf Bewerbungsniveau:

---
{writing_samples}
---
""" if writing_samples else ""}"""

    response = messages_create_with_retry(
        client,
        model=model,
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    if verbose:
        usage = response.usage
        print(f"  [Writer] Tokens: {usage.input_tokens} in, {usage.output_tokens} out")

    text = "".join(block.text for block in response.content if hasattr(block, "text"))

    try:
        result = _extract_json(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"WriterAgent returned invalid JSON: {e}\n\nResponse:\n{text[:500]}")

    return AnschreibenData(
        sender_name=result.get("sender_name", mega.cv_data.name),
        sender_address=result.get("sender_address", mega.cv_data.location or ""),
        sender_email=result.get("sender_email", mega.cv_data.email or ""),
        sender_phone=result.get("sender_phone", mega.cv_data.phone),
        sender_city=result.get("sender_city", mega.cv_data.location or ""),
        date=result.get("date", _format_date(language)),
        company_name=result.get("company_name", mega.job_data.company),
        company_address=result.get("company_address"),
        contact_person=result.get("contact_person"),
        salutation=result["salutation"],
        subject=result["subject"],
        tagline=result.get("tagline"),
        section_labels=result.get("section_labels", []),
        opening_paragraph=result["opening_paragraph"],
        body_paragraphs=result["body_paragraphs"],
        closing_paragraph=result["closing_paragraph"],
        closing_formula=result["closing_formula"],
    )
