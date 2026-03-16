from pydantic import BaseModel, Field
from typing import Optional


class SkillTranslation(BaseModel):
    requirement: str
    original_experience: str          # Was hat die Person wirklich getan?
    cover_letter_formulation: str     # Fertiger Satz fürs Anschreiben
    cv_bullet: str                    # Kürzere Version für Lebenslauf
    evidence: str                     # Beleg aus dem Profil
    credibility: str                  # "stark" | "mittel" | "schwach"
    writer_warning: Optional[str] = None  # Hinweis wenn Beleg schwach


class SkillTranslationOutput(BaseModel):
    translations: list[SkillTranslation]
    strong_count: int
    risky_translations: list[str]     # Requirements mit schwachem Beleg
    narrative_frame: Optional[str] = None  # Narrative Klammer (z.B. "Engineering-Perspektive als PM-Vorteil")


class ScraperOutput(BaseModel):
    raw_markdown: str
    filepath: str
    job_title: str
    company_name: str


class JobData(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    job_type: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    contact_person: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)  # atomare Begriffe aus der Stellenanzeige
    raw_text: str = ""


class CvExperience(BaseModel):
    role: str
    company: str
    period: str
    bullets: list[str] = Field(default_factory=list)


class CvEducation(BaseModel):
    degree: str
    institution: str
    period: Optional[str] = None
    details: Optional[str] = None


class CvPublication(BaseModel):
    year: Optional[str] = None
    title: str
    description: Optional[str] = None
    url: Optional[str] = None


class CvTalk(BaseModel):
    year: Optional[str] = None
    title: str
    description: Optional[str] = None
    url: Optional[str] = None


class CvTool(BaseModel):
    year: Optional[str] = None
    title: str
    description: Optional[str] = None
    url: Optional[str] = None


class CvData(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    summary: Optional[str] = None
    experience: list[CvExperience] = Field(default_factory=list)
    education: list[CvEducation] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    publications: list[CvPublication] = Field(default_factory=list)
    talks: list[CvTalk] = Field(default_factory=list)
    tools_created: list[CvTool] = Field(default_factory=list)


class CvJobMapping(BaseModel):
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    relevant_experience: list[str] = Field(default_factory=list)
    relevant_experience_keys: list[str] = Field(default_factory=list)  # "role @ company"
    key_selling_points: list[str] = Field(default_factory=list)
    tone_recommendation: str = "professional"


class RequirementMapping(BaseModel):
    requirement: str
    category: str  # "direkt" | "übersetzbar" | "lücke" | "ko_luecke_kompensiert" | "ko_luecke_unkompensierbar"
    translation_suggestion: Optional[str] = None
    compensation_note: Optional[str] = None


class GapAssessmentOutput(BaseModel):
    requirements_mapped: list[RequirementMapping]
    fit_score: float  # 0–100
    recommendation: str  # "bewerben" | "bewerben_mit_hinweis" | "nicht_empfohlen"
    recommendation_reason: str
    top_arguments: list[str]  # 3 stärkste Argumente fürs Anschreiben
    gap_notes: list[str]  # Lücken die im Anschreiben adressiert werden sollen
    covered_domain_keywords: list[str] = Field(default_factory=list)
    # Company-Website-Keywords die durch das Profil gedeckt sind → direkt für Writer
    ko_compensations: list[str] = Field(default_factory=list)
    # Fertige offensive Formulierungen für K.O.-Lücken → direkt für Writer


class AnalyzerOutput(BaseModel):
    language: str  # "de" or "en"
    job_data: JobData
    cv_data: CvData
    mapping: CvJobMapping


class AnschreibenData(BaseModel):
    sender_name: str
    sender_address: str
    sender_email: str
    sender_phone: Optional[str] = None
    sender_city: str
    date: str
    company_name: str
    company_address: Optional[str] = None
    contact_person: Optional[str] = None
    salutation: str
    subject: str
    opening_paragraph: str
    body_paragraphs: list[str]
    closing_paragraph: str
    closing_formula: str
    tagline: Optional[str] = None
    photo_path: Optional[str] = None
    section_labels: list[str] = Field(default_factory=list)


class LebenslaufData(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    summary: Optional[str] = None
    experience: list[CvExperience]
    education: list[CvEducation]
    skills: list[str]
    languages: list[str]
    certifications: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    publications: list[CvPublication] = Field(default_factory=list)
    talks: list[CvTalk] = Field(default_factory=list)
    tools_created: list[CvTool] = Field(default_factory=list)


class ReferenzEntry(BaseModel):
    period: str
    role: str
    company: str
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class ReferenzprojekteData(BaseModel):
    entries: list[ReferenzEntry]
    name: str
    location: str
    website: Optional[str] = None
    email: str
    phone: str


class MegaAnalysisOutput(BaseModel):
    language: str  # "de" or "en"
    job_data: JobData
    cv_data: CvData
    mapping: CvJobMapping
    gap: GapAssessmentOutput
    skill_translations: SkillTranslationOutput


class ApplicationDocuments(BaseModel):
    anschreiben: AnschreibenData
    lebenslauf: LebenslaufData
    referenzprojekte: Optional[ReferenzprojekteData] = None
    language: str
    job_title: str
    company_name: str
