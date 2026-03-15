"""AnalyzerAgent: Job posting + CV → structured analysis."""
import json
from anthropic import Anthropic
from tools.analysis_tools import (
    DETECT_LANGUAGE_TOOL, PARSE_CV_SECTIONS_TOOL, EXTRACT_JOB_REQUIREMENTS_TOOL,
    MAP_CV_TO_JOB_TOOL, SUBMIT_ANALYSIS_TOOL, ANALYSIS_TOOL_HANDLERS,
)
from models.document import AnalyzerOutput, JobData, CvData, CvJobMapping, CvExperience, CvEducation, CvPublication, CvTalk, CvTool
from utils.config import get_api_key, messages_create_with_retry

TOOLS = [
    DETECT_LANGUAGE_TOOL, PARSE_CV_SECTIONS_TOOL, EXTRACT_JOB_REQUIREMENTS_TOOL,
    MAP_CV_TO_JOB_TOOL, SUBMIT_ANALYSIS_TOOL,
]

SYSTEM_PROMPT = """You are an expert job application analyst.

Your task:
1. Call detect_language on the job posting to determine if it's German (de) or English (en).
2. Call parse_cv_sections to structure the CV content.
3. Call extract_job_requirements on the job markdown to understand requirements.
4. Call map_cv_to_job to analyze the fit between CV and job.
5. Based on all gathered information, call submit_analysis with fully structured data.

For submit_analysis, carefully extract:
- job_data: title, company, location, requirements (hard requirements), responsibilities,
  nice_to_have, benefits, contact_person,
  keywords (10–20 atomare Fachbegriffe aus der Stellenanzeige — einzelne Wörter oder kurze Phrasen,
  keine Sätze; Buzzwords, Tools, Methoden, Technologien, Domänenbegriffe die wörtlich im Dokument auftauchen sollen)
- cv_data: name, contact info, all experience entries with role/company/period/bullets,
  education, skills list, languages list
- mapping: matching_skills, missing_skills, relevant_experience descriptions,
  relevant_experience_keys (list of "role @ company" strings — exact names from CV — for positions relevant to this job; only truly relevant positions),
  key_selling_points (3-5 strongest points), tone_recommendation

Be thorough and accurate. Extract ALL experience entries from the CV."""


def run(
    job_markdown: str,
    cv_markdown: str,
    model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> AnalyzerOutput:
    client = Anthropic(api_key=get_api_key())
    messages = [
        {
            "role": "user",
            "content": (
                f"Analyze this job posting and CV.\n\n"
                f"## JOB POSTING\n{job_markdown}\n\n"
                f"## CV\n{cv_markdown}"
            ),
        }
    ]

    submit_result = None

    for iteration in range(8):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [Analyzer] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [Analyzer] → {block.name}({list(block.input.keys())})")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            if tool_name == "submit_analysis":
                submit_result = tool_input
                result_content = json.dumps({"status": "submitted"})
            elif tool_name in ANALYSIS_TOOL_HANDLERS:
                result = ANALYSIS_TOOL_HANDLERS[tool_name](tool_input)
                result_content = json.dumps(result)
            else:
                result_content = json.dumps({"error": f"Unknown tool: {tool_name}"})

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
        raise RuntimeError("AnalyzerAgent did not call submit_analysis")

    # Build typed models — defensively parse if the model returned JSON strings
    job_raw = submit_result["job_data"]
    if isinstance(job_raw, str):
        job_raw = json.loads(job_raw)
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

    cv_raw = submit_result["cv_data"]
    if isinstance(cv_raw, str):
        cv_raw = json.loads(cv_raw)
    cv_data = CvData(
        name=cv_raw.get("name", ""),
        email=cv_raw.get("email"),
        phone=cv_raw.get("phone"),
        location=cv_raw.get("location"),
        linkedin=cv_raw.get("linkedin"),
        github=cv_raw.get("github"),
        website=cv_raw.get("website"),
        summary=cv_raw.get("summary"),
        experience=[
            CvExperience(**exp) for exp in cv_raw.get("experience", [])
        ],
        education=[
            CvEducation(**edu) for edu in cv_raw.get("education", [])
        ],
        skills=cv_raw.get("skills", []),
        languages=cv_raw.get("languages", []),
        certifications=cv_raw.get("certifications", []),
        highlights=cv_raw.get("highlights", []),
        publications=[CvPublication(**p) for p in cv_raw.get("publications", [])],
        talks=[CvTalk(**t) for t in cv_raw.get("talks", [])],
        tools_created=[CvTool(**t) for t in cv_raw.get("tools_created", [])],
    )

    mapping_raw = submit_result.get("mapping", {})
    if isinstance(mapping_raw, str):
        mapping_raw = json.loads(mapping_raw)
    mapping = CvJobMapping(
        matching_skills=mapping_raw.get("matching_skills", []),
        missing_skills=mapping_raw.get("missing_skills", []),
        relevant_experience=mapping_raw.get("relevant_experience", []),
        relevant_experience_keys=mapping_raw.get("relevant_experience_keys", []),
        key_selling_points=mapping_raw.get("key_selling_points", []),
        tone_recommendation=mapping_raw.get("tone_recommendation", "professional"),
    )

    return AnalyzerOutput(
        language=submit_result["language"],
        job_data=job_data,
        cv_data=cv_data,
        mapping=mapping,
    )
