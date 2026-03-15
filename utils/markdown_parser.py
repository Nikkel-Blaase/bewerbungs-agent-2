"""Parse CV markdown into structured sections using fuzzy heading matching."""
import re
from typing import Optional

# German/English heading aliases → canonical section names
SECTION_ALIASES = {
    "experience": [
        "berufserfahrung", "erfahrung", "work experience", "experience",
        "professional experience", "career", "berufliche erfahrung",
        "tätigkeiten", "arbeitserfahrung",
    ],
    "education": [
        "ausbildung", "bildung", "studium", "education", "studies",
        "academic background", "qualifications", "abschlüsse",
    ],
    "skills": [
        "kenntnisse", "fähigkeiten", "kompetenzen", "skills",
        "technical skills", "core competencies", "technologien",
        "hard skills", "soft skills", "expertise",
    ],
    "languages": [
        "sprachen", "sprachkenntnisse", "languages", "language skills",
        "fremdsprachen",
    ],
    "certifications": [
        "zertifikate", "zertifizierungen", "certifications", "certificates",
        "awards", "auszeichnungen",
    ],
    "summary": [
        "zusammenfassung", "profil", "über mich", "summary", "profile",
        "about me", "objective", "berufsprofil",
    ],
    "publications": ["publikationen", "publications", "veröffentlichungen"],
    "talks": ["talks", "talks & workshops", "vorträge", "workshops", "presentations"],
    "highlights": ["auf einen blick", "highlights", "at a glance", "kurzprofil"],
    "tools_created": ["tools created", "meine tools"],
}


def _normalize(text: str) -> str:
    return text.strip().lower()


def _match_section(heading: str) -> Optional[str]:
    norm = _normalize(heading)
    for canonical, aliases in SECTION_ALIASES.items():
        if norm in aliases or any(alias in norm for alias in aliases):
            return canonical
    return None


def split_cv_sections(cv_markdown: str) -> dict[str, str]:
    """Return a dict mapping canonical section names to their raw markdown content."""
    lines = cv_markdown.splitlines()
    sections: dict[str, str] = {"header": []}
    current_section = "header"

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            if level >= 2:  # Sections start at ##
                canonical = _match_section(heading_text)
                if canonical:
                    current_section = canonical
                    if canonical not in sections:
                        sections[canonical] = []
                    continue
        if isinstance(sections.get(current_section), list):
            sections[current_section].append(line)
        else:
            sections[current_section] = sections.get(current_section, "") + line + "\n"

    return {k: "\n".join(v) if isinstance(v, list) else v for k, v in sections.items()}


def extract_name_from_cv(cv_markdown: str) -> str:
    """Extract the full name from the first H1 heading."""
    for line in cv_markdown.splitlines():
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            return m.group(1).strip()
    return "Unbekannt"
