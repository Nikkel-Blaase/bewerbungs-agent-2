import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
        )
    return key


# Directory constants
ROOT_DIR = _root
JOBS_DIR = _root / "jobs"
OUTPUT_DIR = _root / "output"
TEMPLATES_DIR = _root / "pdf" / "templates"
WRITING_SAMPLES_DIR = _root / "writing_samples"

JOBS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
WRITING_SAMPLES_DIR.mkdir(exist_ok=True)


def messages_create_with_retry(client, max_retries: int = 3, timeout: float = 600.0, **kwargs):
    """Call client.messages.create with exponential backoff on rate limit errors."""
    from anthropic import RateLimitError
    delay = 10
    for attempt in range(max_retries):
        try:
            return client.messages.create(timeout=timeout, **kwargs)
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            print(f"\n  [Rate limit] Waiting {delay}s before retry ({attempt + 1}/{max_retries})...")
            time.sleep(delay)
            delay = min(delay * 2, 60)
