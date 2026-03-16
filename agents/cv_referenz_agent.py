"""CvReferenzAgent: Single Haiku call generating Lebenslauf + Referenzprojekte."""
import json
import re
from anthropic import Anthropic
from models.document import (
    MegaAnalysisOutput, LebenslaufData, ReferenzprojekteData, ReferenzEntry,
    CvExperience, CvEducation, CvPublication, CvTalk, CvTool,
)
from utils.config import get_api_key, messages_create_with_retry

SYSTEM_PROMPT_DE = """Du bist ein Experte für Lebenslauf-Optimierung und Bewerbungsunterlagen für Quereinsteiger ins Product Management.

Erzeuge zwei Dokumente in einem einzigen JSON-Response:
1. **lebenslauf**: Optimierter Lebenslauf für die Zielstelle
2. **referenzprojekte**: Relevante Erfahrungseinträge als Referenzseite

## Lebenslauf-Regeln:
- Sortiere Berufserfahrungen chronologisch (neueste zuerst), max. 4 Einträge
- Formuliere Bullets aktionsorientiert mit messbaren Ergebnissen wo möglich
- Skills nach Relevanz sortiert, max. 6 Tags
- Professionelle Zusammenfassung (2–3 Sätze), auf die Stelle zugeschnitten
- Jobtitel NICHT ändern, aber Bullets und Summary in PM-Sprache übersetzen
- PM-Vokabular: Roadmap, Anforderungen, Stakeholder, Go-to-Market, Produktstrategie, Marktbeobachtung
- Behalte publications, talks, tools_created und highlights unverändert aus dem Original-CV
- Max. 2 Ausbildungseinträge, max. 4 Highlights
- Nutze die Übersetzungshinweise im Prompt als konkreten Leitfaden

## Referenzprojekte-Regeln:
- Wähle 3–6 stellenrelevanteste Erfahrungseinträge
- Weise 2–4 Skill-Tags pro Eintrag zu (aus Job-Keywords bevorzugt)
- Übersetze Bullets in PM-Sprache, behalte alle inhaltlichen Fakten
- Reihenfolge: Relevanz für die Stelle zuerst, bei gleicher Relevanz neueste zuerst

## OUTPUT FORMAT

Antworte NUR mit einem validen JSON-Objekt. Kein Text davor oder danach, kein Markdown-Wrapper.

{
  "lebenslauf": {
    "name": "", "email": null, "phone": null, "location": null,
    "linkedin": null, "github": null, "website": null, "summary": "",
    "experience": [{"role": "", "company": "", "period": "", "bullets": []}],
    "education": [{"degree": "", "institution": "", "period": "", "details": null}],
    "skills": [], "languages": [], "certifications": [], "highlights": [],
    "publications": [], "talks": [], "tools_created": []
  },
  "referenzprojekte": {
    "entries": [{"period": "", "role": "", "company": "", "url": null, "tags": [], "bullets": []}]
  }
}"""

SYSTEM_PROMPT_EN = """You are an expert in CV optimization and application documents for career changers into Product Management.

Generate two documents in a single JSON response:
1. **lebenslauf**: Optimized CV for the target role
2. **referenzprojekte**: Relevant experience entries as reference page

## CV Rules:
- Order experience chronologically (newest first), max 4 entries
- Action-oriented bullets with measurable results where possible
- Skills sorted by relevance, max 6 tags
- Professional summary (2–3 sentences), tailored to the role
- Do NOT change job titles, but translate bullets and summary into PM language
- PM vocabulary: roadmap, requirements, stakeholders, go-to-market, product strategy, market analysis
- Keep publications, talks, tools_created and highlights unchanged from original CV
- Max 2 education entries, max 4 highlights
- Use the translation hints in the prompt as a concrete guide

## Reference Projects Rules:
- Select 3–6 most job-relevant experience entries
- Assign 2–4 skill tags per entry (prefer job keywords)
- Translate bullets into PM language, preserve all factual content
- Order: relevance first, then recency

## OUTPUT FORMAT

Reply ONLY with a valid JSON object. No text before or after, no markdown wrapper.

{
  "lebenslauf": {
    "name": "", "email": null, "phone": null, "location": null,
    "linkedin": null, "github": null, "website": null, "summary": "",
    "experience": [{"role": "", "company": "", "period": "", "bullets": []}],
    "education": [{"degree": "", "institution": "", "period": "", "details": null}],
    "skills": [], "languages": [], "certifications": [], "highlights": [],
    "publications": [], "talks": [], "tools_created": []
  },
  "referenzprojekte": {
    "entries": [{"period": "", "role": "", "company": "", "url": null, "tags": [], "bullets": []}]
  }
}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return json.loads(text)


def run(
    mega: MegaAnalysisOutput,
    model: str = "claude-haiku-4-5-20251001",
    verbose: bool = False,
) -> tuple[LebenslaufData, ReferenzprojekteData]:
    client = Anthropic(api_key=get_api_key())
    language = mega.language
    system = SYSTEM_PROMPT_DE if language == "de" else SYSTEM_PROMPT_EN

    exp_text = "\n".join(
        f"### {e.role} @ {e.company} ({e.period})\n" + "\n".join(f"- {b}" for b in e.bullets)
        for e in mega.cv_data.experience
    )
    edu_text = "\n".join(
        f"- {e.degree}, {e.institution} ({e.period})"
        for e in mega.cv_data.education
    )

    translations = [
        r.translation_suggestion
        for r in mega.gap.requirements_mapped
        if r.translation_suggestion and r.category in ("übersetzbar", "ko_luecke_kompensiert")
    ]
    translation_block = ""
    if translations:
        translation_block = "\n**Übersetzungshinweise (aus Gap Assessment):**\n" + "\n".join(f"- {t}" for t in translations)

    prompt = f"""Erstelle Lebenslauf und Referenzprojekte für:

**Stelle:** {mega.job_data.title} bei {mega.job_data.company}

**Job-Anforderungen:**
{chr(10).join(f'- {r}' for r in mega.job_data.requirements[:12])}

**Keywords aus der Stelle:** {', '.join(mega.job_data.keywords[:15])}

**Key Selling Points:**
{chr(10).join(f'- {p}' for p in mega.mapping.key_selling_points)}

**Top-Argumente aus Gap Assessment:**
{chr(10).join(f'- {a}' for a in mega.gap.top_arguments)}{translation_block}

**Bewerber:**
Name: {mega.cv_data.name}
Email: {mega.cv_data.email or ''}
Phone: {mega.cv_data.phone or ''}
Location: {mega.cv_data.location or ''}
LinkedIn: {mega.cv_data.linkedin or ''}
GitHub: {mega.cv_data.github or ''}
Website: {mega.cv_data.website or ''}
Skills: {', '.join(mega.cv_data.skills)}
Languages: {', '.join(mega.cv_data.languages)}
Certifications: {', '.join(mega.cv_data.certifications)}

**Berufserfahrung:**
{exp_text}

**Ausbildung:**
{edu_text}"""

    response = messages_create_with_retry(
        client,
        model=model,
        max_tokens=3500,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    if verbose:
        usage = response.usage
        print(f"  [CvReferenz] Tokens: {usage.input_tokens} in, {usage.output_tokens} out")

    text = "".join(block.text for block in response.content if hasattr(block, "text"))

    try:
        data = _extract_json(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"CvReferenzAgent returned invalid JSON: {e}\n\nResponse:\n{text[:500]}")

    # Build LebenslaufData
    lv = data["lebenslauf"]
    lebenslauf = LebenslaufData(
        name=lv.get("name", mega.cv_data.name),
        email=lv.get("email", mega.cv_data.email),
        phone=lv.get("phone", mega.cv_data.phone),
        location=lv.get("location", mega.cv_data.location),
        linkedin=lv.get("linkedin", mega.cv_data.linkedin),
        github=lv.get("github", mega.cv_data.github),
        website=lv.get("website", mega.cv_data.website),
        summary=lv.get("summary"),
        experience=[CvExperience(**e) for e in lv.get("experience", [])],
        education=[CvEducation(**e) for e in lv.get("education", [])],
        skills=lv.get("skills", []),
        languages=lv.get("languages", []),
        certifications=lv.get("certifications", []),
        highlights=lv.get("highlights", mega.cv_data.highlights),
        publications=[
            CvPublication(**p) if isinstance(p, dict) else CvPublication(title=str(p))
            for p in sorted(
                lv.get("publications", [p.model_dump() for p in mega.cv_data.publications]),
                key=lambda x: x.get("year", "") if isinstance(x, dict) else (x.year or "") if hasattr(x, "year") else "",
                reverse=True,
            )
        ],
        talks=[
            CvTalk(**t) if isinstance(t, dict) else CvTalk(title=str(t))
            for t in sorted(
                lv.get("talks", [t.model_dump() for t in mega.cv_data.talks]),
                key=lambda x: x.get("year", "") if isinstance(x, dict) else (x.year or "") if hasattr(x, "year") else "",
                reverse=True,
            )
        ],
        tools_created=[
            CvTool(title=t.get("title") or t.get("name", ""), description=t.get("description"), year=t.get("year"), url=t.get("url"))
            if isinstance(t, dict) else CvTool(title=str(t))
            for t in sorted(
                lv.get("tools_created", [t.model_dump() for t in mega.cv_data.tools_created]),
                key=lambda x: x.get("year", "") if isinstance(x, dict) else (x.year or "") if hasattr(x, "year") else "",
                reverse=True,
            )
        ],
    )

    # Build ReferenzprojekteData
    ref_raw = data["referenzprojekte"]
    referenzprojekte = ReferenzprojekteData(
        entries=[ReferenzEntry(**e) for e in ref_raw.get("entries", [])],
        name=mega.cv_data.name,
        location=mega.cv_data.location or "",
        website=mega.cv_data.website,
        email=mega.cv_data.email or "",
        phone=mega.cv_data.phone or "",
    )

    return lebenslauf, referenzprojekte
