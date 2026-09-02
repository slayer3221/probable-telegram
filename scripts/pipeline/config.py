"""Pipeline configuration. Secrets come from the environment (see .env.example)."""
from pathlib import Path

from .io_utils import ROOT, env, read_json

DOCKET_ID = env("DOCKET_ID", "FDA-2026-N-7874")
DOCUMENT_ID = env("DOCUMENT_ID", "FDA-2026-N-7874-0001")
REGULATIONS_API_BASE = "https://api.regulations.gov/v4"
REGULATIONS_API_KEY = env("REGULATIONS_GOV_API_KEY")
# The Anthropic key is read from REGULATION_TRACKER_ANTHROPIC (the GitHub
# secret name); ANTHROPIC_API_KEY is accepted as a local-development fallback.
LLM_API_KEY = env("REGULATION_TRACKER_ANTHROPIC") or env("ANTHROPIC_API_KEY")
# Identity-linked API keys must name the workspace each request acts in.
# Leave unset for workspace-scoped keys.
LLM_WORKSPACE_ID = env("ANTHROPIC_WORKSPACE_ID")

# Bump when segmentation, classification or build logic changes in a way that
# should force reprocessing of every submission.
PROCESSING_VERSION = "2026.09.1"

RAW_DIR = ROOT / "raw"
RAW_COMMENTS = RAW_DIR / "comments"
RAW_TEXT = RAW_DIR / "text"
RAW_ATTACHMENTS = RAW_DIR / "attachments"
CLASSIFIED_DIR = ROOT / "classified"
CLASSIFIED_SEGMENTS = CLASSIFIED_DIR / "segments"
CLASSIFIED_POSITIONS = CLASSIFIED_DIR / "positions"
CLASSIFIED_GAPS = CLASSIFIED_DIR / "gaps"
CLASSIFIED_SUMMARIES = CLASSIFIED_DIR / "summaries"
CLASSIFIED_COMMENTERS = CLASSIFIED_DIR / "commenters.json"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
EDITORIAL_DIR = ROOT / "editorial"
PROMPTS_DIR = ROOT / "prompts"

PROMPT_CONFIG = read_json(PROMPTS_DIR / "config.json", {})
PROMPT_VERSION = PROMPT_CONFIG.get("prompt_version", "0")
LLM_MODEL = env("LLM_MODEL", PROMPT_CONFIG.get("model", "claude-sonnet-5"))

DOCKET_META = {
    "docket_id": DOCKET_ID,
    "docket_url": f"https://www.regulations.gov/docket/{DOCKET_ID}",
    "document_id": DOCUMENT_ID,
    "discussion_paper_url": "https://www.fda.gov/media/194242/download",
    "discussion_paper_landing_url": "https://www.fda.gov/medical-devices/digital-health-center-excellence/considerations-regulation-generative-ai-enabled-medical-devices-discussion-paper-and-request",
    "comment_deadline": "2026-10-19",
    "paper_date": "2026-08-18",
}


def ensure_dirs():
    for d in (RAW_COMMENTS, RAW_TEXT, RAW_ATTACHMENTS, CLASSIFIED_SEGMENTS, CLASSIFIED_POSITIONS,
              CLASSIFIED_GAPS, CLASSIFIED_SUMMARIES, PUBLIC_DIR, DATA_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)
