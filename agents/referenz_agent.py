"""ReferenzAgent: Selects and enriches work experience entries for reference pages."""
import json
from anthropic import Anthropic
from models.document import AnalyzerOutput, ReferenzprojekteData, ReferenzEntry, GapAssessmentOutput
from utils.config import get_api_key, messages_create_with_retry

SUBMIT_REFERENZPROJEKTE_TOOL = {
    "name": "submit_referenzprojekte",
    "description": "Submit the final reference project entries. Call this as the last step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": "3–6 most job-relevant experience entries with enriched details.",
                "items": {
                    "type": "object",
                    "properties": {
                        "period": {"type": "string", "description": "e.g. '10/2025 – PRESENT'"},
                        "role": {"type": "string"},
                        "company": {"type": "string", "description": "Company name and location, e.g. 'Pneuhage, Karlsruhe'"},
                        "url": {"type": "string", "description": "Optional portfolio/detail link"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2–4 skill tags most relevant to the job posting",
                        },
                        "bullets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "All original bullet points from the CV entry, preserved verbatim",
                        },
                    },
                    "required": ["period", "role", "company", "tags", "bullets"],
                },
            },
        },
        "required": ["entries"],
    },
}

SYSTEM_PROMPT_DE = """Du bist ein Experte für Bewerbungsunterlagen.

Deine Aufgabe:
- Wähle die 3–6 stellenrelevantesten Erfahrungseinträge aus dem Lebenslauf aus
- Weise jedem Eintrag 2–4 Skill-Tags zu, die für die ausgeschriebene Stelle besonders relevant sind
- Übersetze alle Bullet Points in PM-Sprache — behalte alle inhaltlichen Fakten, aber formuliere in der Sprache der Zielrolle
- Reihenfolge: Relevanz für die Stelle zuerst, dann chronologisch

AKTIVE ÜBERSETZUNG (Quereinsteiger):
- Jobtitel NICHT ändern — aber Bullets in PM-Sprache übersetzen
- Beispiel: "Implemented feature X" → "Definierte Anforderungen und führte cross-funktionale Umsetzung von Feature X, Reichweite 50K+ Nutzer"
- PM-Vokabular aktiv einsetzen: Roadmap, Anforderungen, Stakeholder, Go-to-Market, Produktstrategie, Marktbeobachtung, Produktentstehungsprozess, Lastenheft, Markteinführung
- Nutze die Übersetzungshinweise im User Prompt als konkreten Leitfaden

Ruf am Ende submit_referenzprojekte auf."""

SYSTEM_PROMPT_EN = """You are an expert in application documents.

Your task:
- Select the 3–6 most job-relevant experience entries from the CV
- Assign 2–4 skill tags per entry that are most relevant to the job posting
- Translate all bullet points into PM language — preserve all factual content but reframe using product management vocabulary
- Order: most relevant to the role first, then chronologically

ACTIVE TRANSLATION (career changer):
- Do NOT change job titles — but translate bullets into PM language
- Example: "Implemented feature X" → "Defined requirements and led cross-functional delivery of feature X, reaching 50K+ users"
- Actively use PM vocabulary: roadmap, requirements, stakeholders, go-to-market, product strategy, market analysis, product lifecycle, launch
- Use the translation hints in the user prompt as a concrete guide

Call submit_referenzprojekte as the final step."""


def run(
    analysis: AnalyzerOutput,
    gap_assessment: GapAssessmentOutput | None = None,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> ReferenzprojekteData:
    client = Anthropic(api_key=get_api_key())
    language = analysis.language
    system = SYSTEM_PROMPT_DE if language == "de" else SYSTEM_PROMPT_EN

    exp_text = "\n".join(
        f"### {e.role} @ {e.company} ({e.period})\n"
        + "\n".join(f"- {b}" for b in e.bullets)
        for e in analysis.cv_data.experience
    )

    prompt = f"""Select and tag the most relevant experience entries for this application:

**Target Position:** {analysis.job_data.title} at {analysis.job_data.company}

**Job Requirements:**
{chr(10).join(f'- {r}' for r in analysis.job_data.requirements[:12])}

**Matching skills identified:**
{', '.join(analysis.mapping.matching_skills)}

**Keywords aus der Stelle (für Tags bei den Einträgen bevorzugen):**
{', '.join(analysis.job_data.keywords[:15])}

**All CV experience entries:**
{exp_text}
"""

    if gap_assessment:
        translations = [
            r.translation_suggestion
            for r in gap_assessment.requirements_mapped
            if r.translation_suggestion and r.category in ("übersetzbar", "ko_luecke_kompensiert")
        ]
        if translations:
            prompt += "\n**Übersetzungshinweise (aus Gap Assessment):**\n"
            prompt += "\n".join(f"- {t}" for t in translations)

        if gap_assessment.top_arguments:
            prompt += "\n\n**Top-Argumente für das Referenz-Narrativ:**\n"
            prompt += "\n".join(f"- {a}" for a in gap_assessment.top_arguments)

    messages = [{"role": "user", "content": prompt}]
    submit_result = None

    for iteration in range(5):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=system,
            tools=[SUBMIT_REFERENZPROJEKTE_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [Referenz] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [Referenz] → {block.name}")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_referenzprojekte":
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
        raise RuntimeError("ReferenzAgent did not call submit_referenzprojekte")

    return ReferenzprojekteData(
        entries=[ReferenzEntry(**e) for e in submit_result["entries"]],
        name=analysis.cv_data.name,
        location=analysis.cv_data.location or "",
        website=analysis.cv_data.website,
        email=analysis.cv_data.email or "",
        phone=analysis.cv_data.phone or "",
    )
