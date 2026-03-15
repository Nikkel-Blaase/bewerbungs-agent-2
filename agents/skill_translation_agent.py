"""SkillTranslationAgent: Translates transferable skills into concrete cover letter formulations."""
import json
from anthropic import Anthropic
from models.document import AnalyzerOutput, GapAssessmentOutput, SkillTranslation, SkillTranslationOutput
from utils.config import get_api_key, messages_create_with_retry

SUBMIT_SKILL_TRANSLATIONS_TOOL = {
    "name": "submit_skill_translations",
    "description": "Submit the completed skill translations. Call this as the final step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement": {"type": "string"},
                        "original_experience": {
                            "type": "string",
                            "description": "What the person actually did — specific, grounded in their CV",
                        },
                        "cover_letter_formulation": {
                            "type": "string",
                            "description": "Ready-to-use sentence for the cover letter",
                        },
                        "cv_bullet": {
                            "type": "string",
                            "description": "Shorter bullet point version for the CV",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Specific proof from the profile (role, project, company, number)",
                        },
                        "credibility": {
                            "type": "string",
                            "enum": ["stark", "mittel", "schwach"],
                        },
                        "writer_warning": {
                            "type": "string",
                            "description": "Warning note if evidence is weak or requires preparation",
                        },
                    },
                    "required": [
                        "requirement",
                        "original_experience",
                        "cover_letter_formulation",
                        "cv_bullet",
                        "evidence",
                        "credibility",
                    ],
                },
            },
            "strong_count": {
                "type": "integer",
                "description": "Number of translations with credibility='stark'",
            },
            "risky_translations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of requirement strings with weak evidence",
            },
            "narrative_frame": {
                "type": "string",
                "description": "Optional overarching narrative (e.g. 'Engineering-Perspektive als PM-Vorteil')",
            },
        },
        "required": ["translations", "strong_count", "risky_translations"],
    },
}

SYSTEM_PROMPT = """Du bist ein Spezialist für Quereinstieg-Bewerbungen. Deine Aufgabe: Übersetze transferable Skills eines Kandidaten in konkrete, belegbare Formulierungen für Anschreiben und Lebenslauf.

## Dein Ansatz:

**Ehrlichkeit vor Übertreibung:** Formuliere nahe am Original. Strecke keine dünnen Belege. Wenn eine Übersetzung schwach ist, markiere sie als "schwach" und gib einen writer_warning.

**Mehrwert der Quereinstiegsperspektive:** Wo echte Übertragbarkeit besteht, benenne explizit den Zusatznutzen gegenüber klassischen PM-Kandidaten — z.B. technisches Tiefenverständnis, direkte Implementierungserfahrung, interdisziplinärer Blick.

**Spezifität:** Kein "ich habe Erfahrung mit X". Stattdessen: konkrete Firma, konkretes Projekt, konkrete Zahl oder Ergebnis.

## Für jede Anforderung (nur "übersetzbar" und "ko_luecke_kompensiert"):

1. **original_experience**: Was hat die Person wirklich getan? (1–2 Sätze, aus dem Lebenslauf)
2. **cover_letter_formulation**: Fertiger Satz fürs Anschreiben — direkt verwendbar, Ich-Form, professionell
3. **cv_bullet**: Kürzere Version (max. 15 Wörter) für den Lebenslauf
4. **evidence**: Spezifischer Beleg (Rolle + Firma + ggf. Zahl/Ergebnis)
5. **credibility**: "stark" (direkter, spezifischer Beleg), "mittel" (übertragbar aber indirekt), "schwach" (stretch, dünn)
6. **writer_warning**: Nur bei "schwach" — konkreter Hinweis was der Bewerber im Gespräch vorbereiten muss

## narrative_frame:
Falls du eine übergreifende Stärke erkennst, die mehrere Übersetzungen verbindet, formuliere sie als kurzen Satz — z.B. "Technisches Tiefenverständnis ermöglicht präzisere Produktentscheidungen als reine PM-Ausbildung" oder "Direkter Entwickler-Hintergrund schließt typische Kommunikationslücken zwischen PM und Engineering".

Ruf am Ende submit_skill_translations auf."""


def run(
    analysis: AnalyzerOutput,
    gap_assessment: GapAssessmentOutput,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> SkillTranslationOutput:
    client = Anthropic(api_key=get_api_key())

    # Filter only translatable requirements
    translatable = [
        r for r in gap_assessment.requirements_mapped
        if r.category in ("übersetzbar", "ko_luecke_kompensiert")
    ]

    if not translatable:
        return SkillTranslationOutput(
            translations=[],
            strong_count=0,
            risky_translations=[],
            narrative_frame=None,
        )

    translatable_text = "\n".join(
        f"- [{r.category}] {r.requirement}"
        + (f"\n  Übersetzungshinweis: {r.translation_suggestion}" if r.translation_suggestion else "")
        + (f"\n  Kompensationshinweis: {r.compensation_note}" if r.compensation_note else "")
        for r in translatable
    )

    experience_text = "\n".join(
        f"- {exp.role} @ {exp.company} ({exp.period}):\n  "
        + "\n  ".join(exp.bullets)
        for exp in analysis.cv_data.experience
    )

    education_text = "\n".join(
        f"- {edu.degree} @ {edu.institution} ({edu.period})"
        + (f": {edu.details}" if edu.details else "")
        for edu in analysis.cv_data.education
    )

    prompt = f"""Erstelle konkrete Skill-Übersetzungen für diese Bewerbung.

**Stelle:** {analysis.job_data.title} bei {analysis.job_data.company}
**Bewerber:** {analysis.cv_data.name}

**Zu übersetzende Anforderungen** (nur diese, Kategorie in Klammern):
{translatable_text}

**Vollständige Berufserfahrung:**
{experience_text}

**Ausbildung:**
{education_text}

**Skills:** {', '.join(analysis.cv_data.skills[:20])}

**Top-Argumente aus Gap Assessment:**
{chr(10).join(f'- {a}' for a in gap_assessment.top_arguments)}

Übersetze jede Anforderung in eine konkrete, belegbare Formulierung. Nutze ausschließlich Belege aus dem oben genannten Profil."""

    messages = [{"role": "user", "content": prompt}]
    submit_result = None

    for iteration in range(6):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[SUBMIT_SKILL_TRANSLATIONS_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [SkillTranslation] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [SkillTranslation] → {block.name}")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_skill_translations":
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
        raise RuntimeError("SkillTranslationAgent did not call submit_skill_translations")

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
        for t in submit_result.get("translations", [])
    ]

    return SkillTranslationOutput(
        translations=translations,
        strong_count=submit_result.get("strong_count", sum(1 for t in translations if t.credibility == "stark")),
        risky_translations=submit_result.get("risky_translations", []),
        narrative_frame=submit_result.get("narrative_frame"),
    )
