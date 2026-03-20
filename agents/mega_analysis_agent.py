"""MegaAnalysisAgent: Single-shot Sonnet call combining Analyzer + GapAssessment + SkillTranslation."""
import base64
import json
import re
from anthropic import Anthropic
from models.document import (
    MegaAnalysisOutput, JobData, CvData, CvJobMapping, CvExperience, CvEducation,
    CvPublication, CvTalk, CvTool, GapAssessmentOutput, RequirementMapping,
    SkillTranslation, SkillTranslationOutput, PmArchetype,
)
from utils.config import get_api_key, messages_create_with_retry

SYSTEM_PROMPT = """Du bist ein kombinierter Bewerbungsanalyst für Quereinsteiger ins Product Management. Führe drei Analyse-Schritte in einem einzigen Durchgang durch und antworte NUR mit einem validen JSON-Objekt.

## SCHRITT 1: JOB + CV ANALYSIEREN

Extrahiere aus der Stellenanzeige und dem Lebenslauf:
- job_data: title, company, location, requirements (must-have als Liste), responsibilities, nice_to_have, benefits, contact_person, keywords (10–20 atomare Fachbegriffe/Buzzwords — einzelne Wörter oder kurze Phrasen, keine Sätze)
- cv_data: name, email, phone, location, linkedin, github, website, summary, experience (ALLE Einträge mit role/company/period/bullets), education, skills, languages, certifications, highlights, publications, talks, tools_created
- mapping: matching_skills, missing_skills, relevant_experience (Beschreibungen), relevant_experience_keys (exakte "role @ company" Strings aus dem Lebenslauf für relevante Positionen), key_selling_points (3–5), tone_recommendation

## SCHRITT 2: GAP-ASSESSMENT

Bewerte als ehrlicher Karriereberater. Kategorien für jede Anforderung:
- **direkt**: vollständig durch nachgewiesene Erfahrung erfüllt
- **übersetzbar**: übertragbare Fähigkeiten vorhanden (translation_suggestion: welche konkrete Erfahrung aus dem Lebenslauf lässt sich wie übersetzen)
- **lücke**: weder direkt noch übersetzbar abgedeckt (compensation_note: wie im Anschreiben proaktiv adressieren)
- **ko_luecke_kompensiert**: K.O.-Anforderung (Formulierungen wie "zwingend", "erforderlich", "mindestens X Jahre", "verhandlungssicher", "fließend") aber kompensierbar — in ko_compensations fertige offensive Formulierung für das Anschreiben. WICHTIG: Keine Vergleichskonstrukte ("Anstelle von...", "statt eines X", "als vergleichbar"). Formuliere nur die vorhandene Stärke, ohne die Lücke zu nennen.
- **ko_luecke_unkompensierbar**: K.O.-Anforderung ohne Kompensationsmöglichkeit → recommendation = "nicht_empfohlen"

Setze zusätzlich `is_ko: true` für ALLE K.O.-Anforderungen (auch wenn durch das Profil erfüllt),
erkennbar an: "zwingend", "erforderlich", "Voraussetzung", "mindestens X Jahre", "verhandlungssicher",
"fließend", explizite Abschlüsse/Zertifizierungen als Bedingung.

Fit-Score-Logik (0–100):
- direkt × 3 Punkte, übersetzbar × 1.5, lücke × 0, ko_luecke_kompensiert × 0.5, ko_luecke_unkompensierbar × 0
- Normalisiere auf 100 (basierend auf maximal erreichbaren Punkten), runde auf 1 Dezimalstelle

Empfehlungen:
- bewerben (Fit-Score ≥ 70)
- bewerben_mit_hinweis (45–69)
- nicht_empfohlen (<45 oder ko_luecke_unkompensierbar vorhanden)

top_arguments: genau 3 stärkste Argumente mit konkreten Firmennamen, Zahlen, Erfolgen aus dem Lebenslauf
gap_notes: Lücken die proaktiv im Anschreiben adressiert werden sollen

## SCHRITT 3: SKILL-TRANSLATION

Nur für Anforderungen mit Kategorie "übersetzbar" oder "ko_luecke_kompensiert":
- original_experience: Was hat die Person wirklich getan? (1–2 Sätze, aus dem Lebenslauf)
- cover_letter_formulation: Fertiger Satz fürs Anschreiben (Ich-Form, direkt verwendbar)
- cv_bullet: Kürzere Version (max. 15 Wörter)
- evidence: Spezifischer Beleg (Rolle + Firma + ggf. Zahl/Ergebnis)
- credibility: "stark" (direkter Beleg) | "mittel" (indirekt übertragbar) | "schwach" (stretch)
- writer_warning: nur bei "schwach" — was im Gespräch vorbereitet werden muss

Ehrlichkeit vor Übertreibung. Spezifität: kein "ich habe Erfahrung mit X", sondern konkrete Firma/Projekt/Zahl.
strong_count: Anzahl "stark"-Übersetzungen. narrative_frame: optionale übergreifende Stärke.

## SCHRITT 4: PM-ARCHETYP-ERKENNUNG

Bestimme den PM-Archetyp den das Unternehmen sucht. Signale aus Stellenanzeige UND Unternehmensrecherche.

Archetypen:
- **execution**: OKRs, Metriken, Business Impact, KPIs, Wachstumsziele, data-driven
- **collaborative**: Stakeholder, Alignment, cross-functional, Matrix-Org, Konsens
- **technical**: Engineering, Architektur, technische Tiefe, B2B-Infrastruktur, API-first
- **strategic**: Vision, Markt, Expansion, Go-to-Market, Series-A/B-Signale, Positionierung

Unternehmens-Heuristiken (falls Unternehmensrecherche vorhanden):
- B2B-Infra/Plattform → eher technical | Series-A-Startup → eher strategic
- Enterprise/Matrix → eher collaborative | Growth-Phase mit OKRs → eher execution

Primär: ein Archetyp. Sekundär: optional, nur wenn klar erkennbar.
Bei confidence = "niedrig": writer_hint auf universelles Trio fokussieren (Kommunikation, Execution, Product Sense).

writer_hint: Konkrete Anweisung welche Erfahrungen aus dem Kandidatenprofil vorne stehen sollen
und in welche Richtung das Framing geht (z.B. "Stelle Full-Stack-Hintergrund als technischen
PM-Vorteil dar; führe mit Infrastruktur-Erfahrung aus [Firma X]").

## OUTPUT FORMAT

Antworte NUR mit einem validen JSON-Objekt. Kein Text davor oder danach, kein Markdown-Code-Block.

{
  "language": "de",
  "job_data": {
    "title": "", "company": "", "location": null, "job_type": null,
    "requirements": [], "responsibilities": [], "nice_to_have": [],
    "benefits": [], "contact_person": null, "keywords": []
  },
  "cv_data": {
    "name": "", "email": null, "phone": null, "location": null,
    "linkedin": null, "github": null, "website": null, "summary": null,
    "experience": [{"role": "", "company": "", "period": "", "bullets": []}],
    "education": [{"degree": "", "institution": "", "period": "", "details": null}],
    "skills": [], "languages": [], "certifications": [], "highlights": [],
    "publications": [], "talks": [], "tools_created": []
  },
  "mapping": {
    "matching_skills": [], "missing_skills": [], "relevant_experience": [],
    "relevant_experience_keys": [], "key_selling_points": [], "tone_recommendation": "professional"
  },
  "gap": {
    "requirements_mapped": [{"requirement": "", "category": "direkt", "is_ko": false, "translation_suggestion": null, "compensation_note": null}],
    "fit_score": 0.0, "recommendation": "bewerben", "recommendation_reason": "",
    "top_arguments": [], "gap_notes": [], "covered_domain_keywords": [], "ko_compensations": []
  },
  "skill_translations": {
    "translations": [{"requirement": "", "original_experience": "", "cover_letter_formulation": "",
                      "cv_bullet": "", "evidence": "", "credibility": "stark", "writer_warning": null}],
    "strong_count": 0, "risky_translations": [], "narrative_frame": null
  },
  "pm_archetype": {
    "primary": "execution",
    "secondary": null,
    "confidence": "hoch",
    "reasoning": "",
    "writer_hint": ""
  }
}"""


def _extract_json(text: str) -> dict:
    """Extract JSON from text, handling optional markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return json.loads(text)


def run(
    job_markdown: str,
    cv_markdown: str | None,
    cv_pdf_bytes: bytes | None = None,
    company_context: str | None = None,
    language: str | None = None,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    lessons_context: str | None = None,
) -> MegaAnalysisOutput:
    client = Anthropic(api_key=get_api_key())

    lang_hint = f"\n\nDie Stellenanzeige ist auf {'Deutsch' if language == 'de' else 'Englisch'}." if language else ""

    company_block = ""
    if company_context:
        company_block = (
            f"\n\n## UNTERNEHMENSRECHERCHE\n"
            f"Nutze diese Informationen für SCHRITT 2 (covered_domain_keywords enrichment — nur wenn durch "
            f"Profil gedeckt) und SCHRITT 4 (PM-Archetyp-Heuristik aus Unternehmenskontext).\n\n"
            f"{company_context}"
        )

    lessons_block = f"\n\n{lessons_context}" if lessons_context else ""

    if cv_pdf_bytes:
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Analysiere diese Stellenanzeige und diesen Lebenslauf (PDF beigefügt).{lang_hint}\n\n"
                    f"## STELLENANZEIGE\n{job_markdown}\n\n"
                    f"## LEBENSLAUF\nSiehe beigefügtes PDF-Dokument."
                    f"{company_block}"
                    f"{lessons_block}"
                ),
            },
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(cv_pdf_bytes).decode("utf-8"),
                },
            },
        ]
    else:
        user_content = (
            f"Analysiere diese Stellenanzeige und diesen Lebenslauf.{lang_hint}\n\n"
            f"## STELLENANZEIGE\n{job_markdown}\n\n"
            f"## LEBENSLAUF\n{cv_markdown}"
            f"{company_block}"
            f"{lessons_block}"
        )

    response = messages_create_with_retry(
        client,
        model=model,
        max_tokens=16384,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    if verbose:
        usage = response.usage
        print(f"  [MegaAnalysis] Tokens: {usage.input_tokens} in, {usage.output_tokens} out")

    text = "".join(block.text for block in response.content if hasattr(block, "text"))

    try:
        data = _extract_json(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"MegaAnalysisAgent returned invalid JSON: {e}\n\nResponse:\n{text[:500]}")

    # Parse job_data
    job_raw = data["job_data"]
    job_data = JobData(
        title=job_raw.get("title", ""),
        company=job_raw.get("company", ""),
        location=job_raw.get("location"),
        job_type=job_raw.get("job_type"),
        requirements=job_raw.get("requirements", []),
        responsibilities=job_raw.get("responsibilities", []),
        nice_to_have=job_raw.get("nice_to_have", []),
        benefits=job_raw.get("benefits", []),
        contact_person=job_raw.get("contact_person"),
        keywords=job_raw.get("keywords", []),
        raw_text=job_markdown,
    )

    # Parse cv_data
    cv_raw = data["cv_data"]
    cv_data = CvData(
        name=cv_raw.get("name", ""),
        email=cv_raw.get("email"),
        phone=cv_raw.get("phone"),
        location=cv_raw.get("location"),
        linkedin=cv_raw.get("linkedin"),
        github=cv_raw.get("github"),
        website=cv_raw.get("website"),
        summary=cv_raw.get("summary"),
        experience=[CvExperience(**e) for e in cv_raw.get("experience", [])],
        education=[CvEducation(**e) for e in cv_raw.get("education", [])],
        skills=[s if isinstance(s, str) else str(s) for s in cv_raw.get("skills", [])],
        languages=[
            (f"{l['language']} ({l['level']})" if isinstance(l, dict) else str(l))
            for l in cv_raw.get("languages", [])
        ],
        certifications=[
            (f"{c['title']} ({c.get('date', '')})" if isinstance(c, dict) else str(c))
            for c in cv_raw.get("certifications", [])
        ],
        highlights=cv_raw.get("highlights", []),
        publications=[
            CvPublication(**p) if isinstance(p, dict) else CvPublication(title=str(p))
            for p in cv_raw.get("publications", [])
        ],
        talks=[
            CvTalk(**t) if isinstance(t, dict) else CvTalk(title=str(t))
            for t in cv_raw.get("talks", [])
        ],
        tools_created=[
            CvTool(title=t.get("title") or t.get("name", ""), description=t.get("description"), year=t.get("year"), url=t.get("url"))
            if isinstance(t, dict) else CvTool(title=str(t))
            for t in cv_raw.get("tools_created", [])
        ],
    )

    # Parse mapping
    map_raw = data["mapping"]
    mapping = CvJobMapping(
        matching_skills=map_raw.get("matching_skills", []),
        missing_skills=map_raw.get("missing_skills", []),
        relevant_experience=map_raw.get("relevant_experience", []),
        relevant_experience_keys=map_raw.get("relevant_experience_keys", []),
        key_selling_points=map_raw.get("key_selling_points", []),
        tone_recommendation=map_raw.get("tone_recommendation", "professional"),
    )

    # Parse gap
    gap_raw = data["gap"]
    requirements_mapped = [
        RequirementMapping(
            requirement=r["requirement"],
            category=r["category"],
            is_ko=r.get("is_ko", False),
            translation_suggestion=r.get("translation_suggestion"),
            compensation_note=r.get("compensation_note"),
        )
        for r in gap_raw.get("requirements_mapped", [])
    ]
    gap = GapAssessmentOutput(
        requirements_mapped=requirements_mapped,
        fit_score=float(gap_raw.get("fit_score", 0)),
        recommendation=gap_raw.get("recommendation", "nicht_empfohlen"),
        recommendation_reason=gap_raw.get("recommendation_reason", ""),
        top_arguments=gap_raw.get("top_arguments", []),
        gap_notes=gap_raw.get("gap_notes", []),
        covered_domain_keywords=gap_raw.get("covered_domain_keywords", []),
        ko_compensations=gap_raw.get("ko_compensations", []),
    )

    # Parse skill_translations
    st_raw = data["skill_translations"]
    translations = [
        SkillTranslation(
            requirement=t["requirement"],
            original_experience=t["original_experience"],
            cover_letter_formulation=t["cover_letter_formulation"],
            cv_bullet=t["cv_bullet"],
            evidence=t["evidence"],
            credibility=t["credibility"],
            writer_warning=t.get("writer_warning"),
        )
        for t in st_raw.get("translations", [])
    ]
    risky_raw = st_raw.get("risky_translations", [])
    risky_translations = [
        r.get("requirement", str(r)) if isinstance(r, dict) else str(r)
        for r in risky_raw
    ]
    skill_translations = SkillTranslationOutput(
        translations=translations,
        strong_count=st_raw.get("strong_count", sum(1 for t in translations if t.credibility == "stark")),
        risky_translations=risky_translations,
        narrative_frame=st_raw.get("narrative_frame"),
    )

    pm_arch_raw = data.get("pm_archetype")
    pm_archetype = None
    if pm_arch_raw:
        pm_archetype = PmArchetype(
            primary=pm_arch_raw.get("primary", "execution"),
            secondary=pm_arch_raw.get("secondary"),
            confidence=pm_arch_raw.get("confidence", "niedrig"),
            reasoning=pm_arch_raw.get("reasoning", ""),
            writer_hint=pm_arch_raw.get("writer_hint", ""),
        )

    return MegaAnalysisOutput(
        language=language or data.get("language", "de"),
        job_data=job_data,
        cv_data=cv_data,
        mapping=mapping,
        gap=gap,
        skill_translations=skill_translations,
        pm_archetype=pm_archetype,
    )
