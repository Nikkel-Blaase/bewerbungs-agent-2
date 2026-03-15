"""CvAgent: Tailors CV content for a specific job posting."""
import json
from anthropic import Anthropic
from models.document import AnalyzerOutput, LebenslaufData, CvExperience, CvEducation, CvPublication, CvTalk, CvTool, GapAssessmentOutput
from utils.config import get_api_key, messages_create_with_retry

SUBMIT_LEBENSLAUF_TOOL = {
    "name": "submit_lebenslauf",
    "description": "Submit the final tailored CV content. Call this as the last step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "location": {"type": "string"},
            "linkedin": {"type": "string"},
            "github": {"type": "string"},
            "website": {"type": "string"},
            "summary": {"type": "string", "description": "2-3 sentence professional summary."},
            "experience": {
                "type": "array",
                "description": "Work experience, ordered by recency (newest first).",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "company": {"type": "string"},
                        "period": {"type": "string"},
                        "bullets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Achievement-focused bullets, quantified where possible.",
                        },
                    },
                    "required": ["role", "company", "period", "bullets"],
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "degree": {"type": "string"},
                        "institution": {"type": "string"},
                        "period": {"type": "string"},
                        "details": {"type": "string"},
                    },
                    "required": ["degree", "institution", "period"],
                },
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Skills sorted by relevance to this job.",
            },
            "languages": {"type": "array", "items": {"type": "string"}},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "highlights": {"type": "array", "items": {"type": "string"},
                "description": "Short stats/achievements, e.g. '12+ years Product Experience'"},
            "publications": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "year": {"type": "string"}, "title": {"type": "string"},
                    "description": {"type": "string"}, "url": {"type": "string"},
                }},
            },
            "talks": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "year": {"type": "string"}, "title": {"type": "string"},
                    "description": {"type": "string"}, "url": {"type": "string"},
                }},
            },
            "tools_created": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "year": {"type": "string"}, "title": {"type": "string"},
                    "description": {"type": "string"}, "url": {"type": "string"},
                }},
            },
        },
        "required": ["name", "experience", "education", "skills", "languages"],
    },
}

SYSTEM_PROMPT_DE = """Du bist ein Experte für Lebenslauf-Optimierung.

Deine Aufgabe:
- Sortiere Berufserfahrungen chronologisch (neueste zuerst). Behalte die relevantesten Einträge (max 4), aber innerhalb dieser Auswahl gilt: neueste zuerst.
- Formuliere Bullet Points um: aktionsorientiert, mit messbaren Ergebnissen wo möglich
- Hebe relevante Skills für diese Stelle hervor
- Erstelle eine professionelle Zusammenfassung (2-3 Sätze), die auf die Stelle zugeschnitten ist
- Verwende nur die angegebenen Erfahrungseinträge — erfinde NICHTS
- Skills: Sortiere nach Relevanz für die Stelle
- Behalte publications, talks, tools_created und highlights unverändert aus dem Original-CV

AKTIVE ÜBERSETZUNG (Quereinsteiger):
- Jobtitel NICHT ändern — aber Summary, Bullets und Framing in PM-Sprache übersetzen
- Beispiel: "Implemented feature X" → "Definierte Anforderungen und führte cross-funktionale Umsetzung von Feature X, Reichweite 50K+ Nutzer"
- PM-Vokabular aktiv einsetzen: Roadmap, Anforderungen, Stakeholder, Go-to-Market, Produktstrategie, Marktbeobachtung, Produktentstehungsprozess, Lastenheft, Markteinführung
- Nutze die Übersetzungshinweise im User Prompt als konkreten Leitfaden — nicht generisch, sondern stellenspezifisch übersetzen

SEITENEINSCHRÄNKUNG – Der Lebenslauf muss auf genau eine DIN-A4-Seite passen:
- Maximal 4 Erfahrungseinträge (nur Titel + Firma + Zeitraum — keine Bullets im Lebenslauf)
- Maximal 6 Skill-Tags
- Maximal 2 Ausbildungseinträge
- Maximal 4 Highlights

Ruf am Ende submit_lebenslauf auf."""

SYSTEM_PROMPT_EN = """You are an expert CV optimizer.

Your task:
- Order work experience chronologically (newest first). Keep the most relevant entries (max 4), but within that selection: newest first.
- Rewrite bullet points: action-oriented, with measurable results where possible
- Highlight skills most relevant to this role
- Create a professional summary (2-3 sentences) tailored to the position
- Only use the listed experience entries — do NOT invent anything
- Skills: sort by relevance to the role
- Keep publications, talks, tools_created and highlights unchanged from the original CV

PAGE CONSTRAINT – The CV must fit on exactly one DIN A4 page:
- Maximum 4 experience entries (title + company + period only — no bullets shown on CV)
- Maximum 6 skill tags
- Maximum 2 education entries
- Maximum 4 highlights

Call submit_lebenslauf as the final step."""


def run(
    analysis: AnalyzerOutput,
    gap_assessment: GapAssessmentOutput | None = None,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> LebenslaufData:
    client = Anthropic(api_key=get_api_key())
    language = analysis.language
    system = SYSTEM_PROMPT_DE if language == "de" else SYSTEM_PROMPT_EN

    relevant_keys = analysis.mapping.relevant_experience_keys
    if relevant_keys:
        def _matches(e: CvExperience) -> bool:
            key = f"{e.role} @ {e.company}".lower()
            return any(k.lower() in key or key in k.lower() for k in relevant_keys)
        experiences = [e for e in analysis.cv_data.experience if _matches(e)]
        if not experiences:  # Fallback: alle, wenn nichts matcht
            experiences = analysis.cv_data.experience
    else:
        experiences = analysis.cv_data.experience

    if verbose:
        print(f"  [CV] Using {len(experiences)}/{len(analysis.cv_data.experience)} experience entries")

    exp_text = "\n".join(
        f"### {e.role} @ {e.company} ({e.period})\n"
        + "\n".join(f"- {b}" for b in e.bullets)
        for e in experiences
    )
    edu_text = "\n".join(
        f"- {e.degree}, {e.institution} ({e.period})"
        for e in analysis.cv_data.education
    )

    prompt = f"""Optimize this CV for the following job:

**Target Position:** {analysis.job_data.title} at {analysis.job_data.company}

**Job Requirements:**
{chr(10).join(f'- {r}' for r in analysis.job_data.requirements[:12])}

**Key selling points identified:**
{chr(10).join(f'- {p}' for p in analysis.mapping.key_selling_points)}

**Matching skills:**
{', '.join(analysis.mapping.matching_skills)}

**Keywords aus der Stelle (für Skills und Bullets verwenden):**
{', '.join(analysis.job_data.keywords[:15])}

**CV to optimize:**
Name: {analysis.cv_data.name}
Email: {analysis.cv_data.email or ''}
Phone: {analysis.cv_data.phone or ''}
Location: {analysis.cv_data.location or ''}
LinkedIn: {analysis.cv_data.linkedin or ''}
GitHub: {analysis.cv_data.github or ''}

Experience:
{exp_text}

Education:
{edu_text}

Skills: {', '.join(analysis.cv_data.skills)}
Languages: {', '.join(analysis.cv_data.languages)}
Certifications: {', '.join(analysis.cv_data.certifications)}
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
            prompt += "\n\n**Top-Argumente für das CV-Narrativ:**\n"
            prompt += "\n".join(f"- {a}" for a in gap_assessment.top_arguments)

    messages = [{"role": "user", "content": prompt}]
    submit_result = None

    for iteration in range(5):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=system,
            tools=[SUBMIT_LEBENSLAUF_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [CV] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [CV] → {block.name}")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_lebenslauf":
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
        raise RuntimeError("CvAgent did not call submit_lebenslauf")

    return LebenslaufData(
        name=submit_result["name"],
        email=submit_result.get("email", analysis.cv_data.email),
        phone=submit_result.get("phone", analysis.cv_data.phone),
        location=submit_result.get("location", analysis.cv_data.location),
        linkedin=submit_result.get("linkedin", analysis.cv_data.linkedin),
        github=submit_result.get("github", analysis.cv_data.github),
        website=submit_result.get("website", analysis.cv_data.website),
        summary=submit_result.get("summary"),
        experience=[CvExperience(**e) for e in submit_result.get("experience", [])],
        education=[CvEducation(**e) for e in submit_result.get("education", [])],
        skills=submit_result.get("skills", []),
        languages=submit_result.get("languages", []),
        certifications=submit_result.get("certifications", []),
        highlights=submit_result.get("highlights", analysis.cv_data.highlights),
        publications=[CvPublication(**p) for p in sorted(
            submit_result.get("publications", [p.model_dump() for p in analysis.cv_data.publications]),
            key=lambda x: x.get("year", "") if isinstance(x, dict) else x.year,
            reverse=True
        )],
        talks=[CvTalk(**t) for t in sorted(
            submit_result.get("talks", [t.model_dump() for t in analysis.cv_data.talks]),
            key=lambda x: x.get("year", "") if isinstance(x, dict) else x.year,
            reverse=True
        )],
        tools_created=[CvTool(**t) for t in sorted(
            submit_result.get("tools_created", [t.model_dump() for t in analysis.cv_data.tools_created]),
            key=lambda x: x.get("year", "") if isinstance(x, dict) else x.year,
            reverse=True
        )],
    )
