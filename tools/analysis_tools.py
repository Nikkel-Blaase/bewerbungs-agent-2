"""Analysis tool definitions and implementations: language detection, CV parsing."""
import json
from utils.markdown_parser import split_cv_sections, extract_name_from_cv

try:
    from langdetect import detect as _langdetect
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False


# ── Tool Definitions ──────────────────────────────────────────────────────────

DETECT_LANGUAGE_TOOL = {
    "name": "detect_language",
    "description": "Detect the language of the job posting text. Returns 'de' or 'en'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to detect language from."}
        },
        "required": ["text"],
    },
}

PARSE_CV_SECTIONS_TOOL = {
    "name": "parse_cv_sections",
    "description": "Parse a CV markdown string into labelled sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cv_markdown": {"type": "string", "description": "Full CV in Markdown format."}
        },
        "required": ["cv_markdown"],
    },
}

EXTRACT_JOB_REQUIREMENTS_TOOL = {
    "name": "extract_job_requirements",
    "description": "Extract structured requirements from a job posting markdown.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_markdown": {
                "type": "string",
                "description": "Job posting text in Markdown format.",
            }
        },
        "required": ["job_markdown"],
    },
}

MAP_CV_TO_JOB_TOOL = {
    "name": "map_cv_to_job",
    "description": "Map CV skills/experience to job requirements and identify gaps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cv_sections": {
                "type": "object",
                "description": "Parsed CV sections as returned by parse_cv_sections.",
            },
            "job_requirements": {
                "type": "object",
                "description": "Extracted job requirements.",
            },
        },
        "required": ["cv_sections", "job_requirements"],
    },
}

SUBMIT_ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": "Submit the final structured analysis result. Call this as the last step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["de", "en"],
                "description": "Detected language of the job posting.",
            },
            "job_data": {
                "type": "object",
                "description": "Structured job data with title, company, requirements, etc.",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "location": {"type": "string"},
                    "job_type": {"type": "string"},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                    "nice_to_have": {"type": "array", "items": {"type": "string"}},
                    "benefits": {"type": "array", "items": {"type": "string"}},
                    "contact_person": {"type": "string"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Atomare Keywords und Fachbegriffe aus der Stellenanzeige (keine ganzen Sätze). Z.B. ['Scrum', 'OKRs', 'Roadmap', 'Stakeholder Management', 'SQL', 'Python']. 10–20 Begriffe.",
                    },
                },
                "required": ["title", "company"],
            },
            "cv_data": {
                "type": "object",
                "description": "Structured CV data.",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "location": {"type": "string"},
                    "linkedin": {"type": "string"},
                    "github": {"type": "string"},
                    "website": {"type": "string"},
                    "summary": {"type": "string"},
                    "experience": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "company": {"type": "string"},
                                "period": {"type": "string"},
                                "bullets": {"type": "array", "items": {"type": "string"}},
                            },
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
                        },
                    },
                    "skills": {"type": "array", "items": {"type": "string"}},
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
                "required": ["name"],
            },
            "mapping": {
                "type": "object",
                "description": "Mapping between CV and job.",
                "properties": {
                    "matching_skills": {"type": "array", "items": {"type": "string"}},
                    "missing_skills": {"type": "array", "items": {"type": "string"}},
                    "relevant_experience": {"type": "array", "items": {"type": "string"}},
                    "relevant_experience_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exact 'role @ company' strings from the CV that are relevant to this job. Use the exact role and company names as they appear in the CV.",
                    },
                    "key_selling_points": {"type": "array", "items": {"type": "string"}},
                    "tone_recommendation": {"type": "string"},
                },
            },
        },
        "required": ["language", "job_data", "cv_data", "mapping"],
    },
}


# ── Implementations ───────────────────────────────────────────────────────────

def detect_language(text: str) -> dict:
    if _LANGDETECT_AVAILABLE:
        try:
            lang = _langdetect(text[:2000])
            # Normalize to de/en
            if lang.startswith("de"):
                return {"language": "de"}
            return {"language": "en"}
        except Exception:
            pass
    # Heuristic fallback
    german_indicators = ["und", "die", "der", "das", "für", "mit", "wir", "sie", "haben"]
    lower = text.lower()
    count = sum(1 for w in german_indicators if f" {w} " in lower)
    return {"language": "de" if count >= 3 else "en"}


def parse_cv_sections(cv_markdown: str) -> dict:
    sections = split_cv_sections(cv_markdown)
    name = extract_name_from_cv(cv_markdown)
    return {"name": name, "sections": sections}


def extract_job_requirements(job_markdown: str) -> dict:
    # Return raw text; Claude will extract structured requirements via reasoning
    return {"raw_text": job_markdown, "length": len(job_markdown)}


def map_cv_to_job(cv_sections: dict, job_requirements: dict) -> dict:
    # Provide the data to Claude; actual mapping is done by the LLM
    return {
        "cv_sections_available": list(cv_sections.get("sections", {}).keys()),
        "job_requirements_length": len(str(job_requirements)),
        "status": "ready_for_analysis",
    }


ANALYSIS_TOOL_HANDLERS = {
    "detect_language": lambda inp: detect_language(**inp),
    "parse_cv_sections": lambda inp: parse_cv_sections(**inp),
    "extract_job_requirements": lambda inp: extract_job_requirements(**inp),
    "map_cv_to_job": lambda inp: map_cv_to_job(**inp),
    "submit_analysis": lambda inp: inp,  # Pass-through; handled by agent
}
