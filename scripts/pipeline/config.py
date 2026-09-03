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
CLASSIFIED_ANALYSIS = CLASSIFIED_DIR / "analysis"
CLASSIFIED_CONSOLIDATION = CLASSIFIED_DIR / "consolidation"
CLASSIFIED_COMMENTERS = CLASSIFIED_DIR / "commenters.json"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
EDITORIAL_DIR = ROOT / "editorial"
PROMPTS_DIR = ROOT / "prompts"

PROMPT_CONFIG = read_json(PROMPTS_DIR / "config.json", {})
# One prompt version per stage, so a change to the analysis prompt does not
# force every submission to be re-segmented.
PROMPT_VERSIONS = PROMPT_CONFIG.get("prompt_versions", {})
LLM_MODEL = env("LLM_MODEL", PROMPT_CONFIG.get("model", "claude-opus-5"))
LLM_CONCURRENCY = int(env("LLM_CONCURRENCY", PROMPT_CONFIG.get("llm_concurrency", 4)))
PRICING = PROMPT_CONFIG.get("pricing_usd_per_million_tokens", {})
RUN_METRICS_PATH = PUBLIC_DIR / "run-metrics.json"


def prompt_version(stage: str) -> str:
    return str(PROMPT_VERSIONS.get(stage, "0"))

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
    for d in (RAW_COMMENTS, RAW_TEXT, RAW_ATTACHMENTS, CLASSIFIED_SEGMENTS, CLASSIFIED_ANALYSIS, CLASSIFIED_CONSOLIDATION, PUBLIC_DIR, DATA_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)
