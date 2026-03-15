"""ScraperAgent: Job-URL → Markdown job posting."""
import json
from slugify import slugify
from anthropic import Anthropic
from tools.scraping_tools import (
    FETCH_URL_TOOL, EXTRACT_TEXT_FROM_HTML_TOOL, CONVERT_TO_MARKDOWN_TOOL,
    SUBMIT_SCRAPER_TOOL, SCRAPER_TOOL_HANDLERS,
)
from tools.file_tools import SAVE_JOB_FILE_TOOL, FILE_TOOL_HANDLERS
from models.document import ScraperOutput
from utils.config import get_api_key, messages_create_with_retry

TOOLS = [FETCH_URL_TOOL, EXTRACT_TEXT_FROM_HTML_TOOL, CONVERT_TO_MARKDOWN_TOOL,
         SAVE_JOB_FILE_TOOL, SUBMIT_SCRAPER_TOOL]

SYSTEM_PROMPT = """You are a web scraping agent specialized in extracting job postings.

Your task:
1. Call fetch_url to retrieve the HTML of the job posting URL.
2. If an error is returned (JS-heavy site), report it immediately via submit_scraper_result with
   job_title="ERROR" and the error message in raw_markdown.
3. Call extract_text_from_html to extract the relevant job content.
4. Call convert_to_markdown to convert to clean Markdown.
5. Generate a URL slug from the company + job title (lowercase, hyphens).
6. Call save_job_file with the slug and markdown content.
7. Finally call submit_scraper_result with all fields filled in.

Extract the job title and company name from the content. Be accurate."""


def run(job_url: str, model: str = "claude-sonnet-4-6", verbose: bool = False) -> ScraperOutput:
    client = Anthropic(api_key=get_api_key())
    messages = [{"role": "user", "content": f"Scrape the job posting at this URL: {job_url}"}]

    all_handlers = {**SCRAPER_TOOL_HANDLERS, **FILE_TOOL_HANDLERS}
    submit_result = None

    for iteration in range(10):
        response = messages_create_with_retry(
            client,
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    print(f"  [Scraper] {block.text[:200]}")
                elif hasattr(block, "type") and block.type == "tool_use":
                    print(f"  [Scraper] → {block.name}({list(block.input.keys())})")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            if tool_name == "submit_scraper_result":
                submit_result = tool_input
                result_content = json.dumps({"status": "submitted"})
            elif tool_name in all_handlers:
                result = all_handlers[tool_name](tool_input)
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
        raise RuntimeError("ScraperAgent did not call submit_scraper_result")

    if submit_result.get("job_title") == "ERROR":
        raise RuntimeError(submit_result.get("raw_markdown", "Scraping failed"))

    return ScraperOutput(
        raw_markdown=submit_result["raw_markdown"],
        filepath=submit_result["filepath"],
        job_title=submit_result["job_title"],
        company_name=submit_result["company_name"],
    )
