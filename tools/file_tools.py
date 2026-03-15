"""File I/O tool definitions and implementations for agents."""
from pathlib import Path
from utils.config import JOBS_DIR


# ── Tool Definitions ──────────────────────────────────────────────────────────

SAVE_JOB_FILE_TOOL = {
    "name": "save_job_file",
    "description": "Save scraped job markdown to the jobs/ directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "URL slug used as filename (no extension).",
            },
            "content": {
                "type": "string",
                "description": "Full markdown content to save.",
            },
        },
        "required": ["slug", "content"],
    },
}

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read a text file from the filesystem.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "Absolute or relative path."}
        },
        "required": ["filepath"],
    },
}


# ── Implementations ───────────────────────────────────────────────────────────

def save_job_file(slug: str, content: str) -> dict:
    filepath = JOBS_DIR / f"{slug}.md"
    filepath.write_text(content, encoding="utf-8")
    return {"success": True, "filepath": str(filepath)}


def read_file(filepath: str) -> dict:
    path = Path(filepath)
    if not path.exists():
        return {"error": f"File not found: {filepath}"}
    return {"content": path.read_text(encoding="utf-8")}


FILE_TOOL_HANDLERS = {
    "save_job_file": lambda inp: save_job_file(**inp),
    "read_file": lambda inp: read_file(**inp),
}
