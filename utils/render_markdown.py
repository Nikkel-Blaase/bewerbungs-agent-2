"""Render ApplicationDocuments to a Markdown file."""
from pathlib import Path
from models.document import ApplicationDocuments

_LABELS = {
    "de": {
        "cover_letter": "Anschreiben",
        "cv": "Lebenslauf",
        "experience": "Berufserfahrung",
        "education": "Ausbildung",
        "skills": "Skills",
        "languages": "Sprachen",
        "certifications": "Zertifikate",
        "publications": "Veröffentlichungen",
        "talks": "Vorträge",
        "tools": "Eigene Tools",
        "reference": "Referenzprojekte",
    },
    "en": {
        "cover_letter": "Cover Letter",
        "cv": "CV",
        "experience": "Experience",
        "education": "Education",
        "skills": "Skills",
        "languages": "Languages",
        "certifications": "Certifications",
        "publications": "Publications",
        "talks": "Talks",
        "tools": "Projects / Tools",
        "reference": "Reference Projects",
    },
}


def render_markdown(documents: ApplicationDocuments, output_path: Path, language: str = "de") -> None:
    """Render all application documents to a single Markdown file."""
    L = _LABELS.get(language, _LABELS["de"])
    parts = []

    # ── Cover Letter / Anschreiben ────────────────────────────────────────────
    a = documents.anschreiben
    parts.append(f"# {L['cover_letter']}\n\n")
    parts.append(f"**{a.sender_name}**  \n")
    parts.append(f"{a.sender_address.replace(chr(10), '  \n')}  \n")
    contact_line = a.sender_email
    if a.sender_phone:
        contact_line += f" | {a.sender_phone}"
    parts.append(f"{contact_line}\n\n")
    parts.append(f"{a.sender_city}, {a.date}\n\n")

    if a.company_name:
        parts.append(f"**{a.company_name}**  \n")
    if a.company_address:
        parts.append(f"{a.company_address}  \n")
    parts.append("\n")

    parts.append(f"{a.salutation}\n\n")
    parts.append(f"**{a.subject}**\n\n")

    if a.tagline:
        parts.append(f"*{a.tagline}*\n\n")

    parts.append(f"{a.opening_paragraph}\n\n")

    label_list = a.section_labels or []
    body_list = a.body_paragraphs or []
    for label, paragraph in zip(label_list, body_list):
        parts.append(f"**{label}**\n\n{paragraph}\n\n")
    # Remaining body paragraphs if more than section_labels
    for paragraph in body_list[len(label_list):]:
        parts.append(f"{paragraph}\n\n")

    parts.append(f"{a.closing_paragraph}\n\n")
    parts.append(f"{a.closing_formula},\n\n{a.sender_name}\n\n")
    parts.append("---\n\n")

    # ── CV / Lebenslauf ───────────────────────────────────────────────────────
    lv = documents.lebenslauf
    parts.append(f"# {L['cv']}\n\n")
    parts.append(f"## {lv.name}\n\n")

    contact_parts = [x for x in [lv.email, lv.phone, lv.location, lv.linkedin, lv.github, lv.website] if x]
    if contact_parts:
        parts.append(" | ".join(contact_parts) + "\n\n")

    if lv.summary:
        parts.append(f"{lv.summary}\n\n")

    if lv.highlights:
        for h in lv.highlights:
            parts.append(f"- {h}\n")
        parts.append("\n")

    if lv.experience:
        parts.append(f"### {L['experience']}\n\n")
        for exp in lv.experience:
            parts.append(f"**{exp.role}** – {exp.company} ({exp.period})\n\n")
            for b in exp.bullets:
                parts.append(f"- {b}\n")
            parts.append("\n")

    if lv.education:
        parts.append(f"### {L['education']}\n\n")
        for edu in lv.education:
            line = f"**{edu.degree}** – {edu.institution} ({edu.period})"
            if edu.details:
                line += f"\n{edu.details}"
            parts.append(line + "\n\n")

    if lv.skills:
        parts.append(f"**{L['skills']}:** {' | '.join(lv.skills)}\n\n")
    if lv.languages:
        parts.append(f"**{L['languages']}:** {' | '.join(lv.languages)}\n\n")
    if lv.certifications:
        parts.append(f"**{L['certifications']}:** {', '.join(lv.certifications)}\n\n")

    if lv.publications:
        parts.append(f"### {L['publications']}\n\n")
        for p in lv.publications:
            line = f"- **{p.title}**"
            if p.year:
                line += f" ({p.year})"
            if p.description:
                line += f" — {p.description}"
            if p.url:
                line += f" [{p.url}]"
            parts.append(line + "\n")
        parts.append("\n")

    if lv.talks:
        parts.append(f"### {L['talks']}\n\n")
        for t in lv.talks:
            line = f"- **{t.title}**"
            if t.year:
                line += f" ({t.year})"
            if t.description:
                line += f" — {t.description}"
            parts.append(line + "\n")
        parts.append("\n")

    if lv.tools_created:
        parts.append(f"### {L['tools']}\n\n")
        for t in lv.tools_created:
            line = f"- **{t.title}**"
            if t.year:
                line += f" ({t.year})"
            if t.description:
                line += f" — {t.description}"
            if t.url:
                line += f" [{t.url}]"
            parts.append(line + "\n")
        parts.append("\n")

    parts.append("---\n\n")

    # ── Reference Projects / Referenzprojekte ────────────────────────────────
    if documents.referenzprojekte:
        ref = documents.referenzprojekte
        parts.append(f"# {L['reference']}\n\n")
        ref_contact = [x for x in [ref.email, ref.phone, ref.location, ref.website] if x]
        parts.append(f"**{ref.name}**")
        if ref_contact:
            parts.append(" | " + " | ".join(ref_contact))
        parts.append("\n\n")

        for entry in ref.entries:
            parts.append(f"## {entry.role} – {entry.company} ({entry.period})\n\n")
            if entry.tags:
                parts.append("`" + "` `".join(entry.tags) + "`\n\n")
            for b in entry.bullets:
                parts.append(f"- {b}\n")
            if entry.url:
                parts.append(f"\n[{entry.url}]\n")
            parts.append("\n")

    output_path.write_text("".join(parts), encoding="utf-8")
