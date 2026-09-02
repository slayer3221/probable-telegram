"""Thin wrapper over the Anthropic SDK for JSON-shaped classification calls.

All AI processing happens here, during ingestion. The frontend never calls a
model. Prompts live in prompts/*.md and are versioned by prompts/config.json.
"""
import json
import logging
import random
import time

from .config import LLM_API_KEY, LLM_MODEL, LLM_WORKSPACE_ID, PROMPT_CONFIG, PROMPTS_DIR
from .io_utils import read_json, ROOT
from .taxonomies import GAPS

log = logging.getLogger("llm")


def render(template: str, **values) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def load_prompt(stage: str) -> str:
    name = PROMPT_CONFIG["stages"][stage]
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def question_list_text() -> str:
    """Question identifiers and text for the system prompt. Exact FDA wording
    is used when present; otherwise the tracker's short label is given and the
    model is told the exact text is pending."""
    data = read_json(ROOT / "data" / "questions.json")
    lines = []
    for q in data["questions"]:
        text = (q.get("question_text") or "").strip()
        if text:
            lines.append(f"{q['id']} (Q{q['question_number']}, theme {q['theme']}): {text}")
        else:
            lines.append(f"{q['id']} (Q{q['question_number']}, theme {q['theme']}): [exact FDA text pending] {q['short_title']}. {q.get('summary_ask','')}")
    return "\n".join(lines)


def system_prompt() -> str:
    return render((PROMPTS_DIR / "system.md").read_text(encoding="utf-8"), QUESTION_LIST=question_list_text())


class LLM:
    def __init__(self, model=None, max_tokens=None):
        try:
            import anthropic  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install -r requirements.txt (anthropic missing)") from exc
        if not LLM_API_KEY:
            raise RuntimeError("REGULATION_TRACKER_ANTHROPIC is not set (ANTHROPIC_API_KEY is accepted as a local fallback)")
        self.anthropic = anthropic
        # An identity-linked key is rejected with HTTP 400 unless the request
        # carries the workspace it acts in; a workspace-scoped key needs no header.
        headers = {"anthropic-workspace-id": LLM_WORKSPACE_ID} if LLM_WORKSPACE_ID else None
        self.client = anthropic.Anthropic(api_key=LLM_API_KEY, max_retries=3, default_headers=headers)
        self.model = model or LLM_MODEL
        self.max_tokens = max_tokens or PROMPT_CONFIG.get("max_tokens", 4096)
        self.system = system_prompt()
        self.calls = 0

    def _create(self, prompt, output_config=None, max_tokens=None, effort=None):
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
        }
        output_config = dict(output_config or {})
        if effort:
            output_config["effort"] = effort
        if output_config:
            kwargs["output_config"] = output_config
        # The SDK retries a few times with sub-second backoff. Transient 529
        # Overloaded / 5xx / connection errors can last longer than that, so
        # this loop adds a slower outer backoff (5s, 10s, 20s, 40s, 60s, 60s).
        for attempt in range(7):
            try:
                self.calls += 1
                resp = self.client.messages.create(**kwargs)
            except self.anthropic.BadRequestError as exc:
                if "workspace" in str(exc).lower():
                    raise RuntimeError(
                        "Anthropic rejected the request: the API key is identity-linked and needs a workspace id. "
                        "Set ANTHROPIC_WORKSPACE_ID (e.g. wrkspc_01...) or use a workspace-scoped API key."
                    ) from exc
                raise
            except self.anthropic.RateLimitError as exc:
                delay = int(exc.response.headers.get("retry-after", "30") or 30)
                log.warning("rate limited; sleeping %ss", delay)
                time.sleep(delay)
                continue
            except (self.anthropic.APIStatusError, self.anthropic.APIConnectionError) as exc:
                status = getattr(exc, "status_code", None)
                transient = status is None or status >= 500 or status == 429
                if not transient or attempt == 6:
                    raise
                delay = min(60, 5 * (2 ** attempt)) + random.uniform(0, 2)
                log.warning("transient API error (%s); retrying in %.0fs (attempt %d/7)", status or type(exc).__name__, delay, attempt + 1)
                time.sleep(delay)
                continue
            if resp.stop_reason == "refusal":
                raise RuntimeError("model declined the request")
            if resp.stop_reason == "max_tokens":
                log.warning("response hit max_tokens; retrying with a larger budget")
                kwargs["max_tokens"] = kwargs["max_tokens"] * 2
                continue
            return "".join(b.text for b in resp.content if b.type == "text")
        raise RuntimeError("model call failed after retries")

    def json(self, prompt, schema, max_tokens=None):
        text = self._create(prompt, output_config={"format": {"type": "json_schema", "schema": schema}}, max_tokens=max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = text.strip().strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            return json.loads(cleaned)

    def text(self, prompt, max_tokens=None, effort=None):
        # Thinking tokens count toward max_tokens on current models, so short
        # text outputs still need a few thousand tokens of headroom.
        return self._create(prompt, max_tokens=max_tokens or 2048, effort=effort).strip()

    def preflight(self):
        """One minimal request to prove authentication and model access
        before any docket work starts. Returns the model's reply."""
        return self.text("Reply with the single word OK.", max_tokens=16)


# JSON schemas for each stage -------------------------------------------------
QIDS = {"type": "array", "items": {"type": "string", "enum": [f"q{n}" for n in range(1, 27)]}}

SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_ids": QIDS,
                    "source_passage": {"type": "string"},
                    "position_gist": {"type": "string"},
                    "is_background_only": {"type": "boolean"},
                },
                "required": ["question_ids", "source_passage", "position_gist", "is_background_only"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["positions"],
    "additionalProperties": False,
}

POSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "question_ids": QIDS,
        "position": {"type": "string", "enum": ["support", "support_with_modification", "oppose", "mixed", "unclear"]},
        "primary_issue": {"type": "string"},
        "secondary_issue": {"type": ["string", "null"]},
        "stakeholder_concern": {"type": "string"},
        "requested_fda_action": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["question_ids", "position", "primary_issue", "secondary_issue", "stakeholder_concern", "requested_fda_action", "confidence"],
    "additionalProperties": False,
}

# Note: the structured-output validator rejects some JSON Schema keywords
# (maxItems was refused with HTTP 400), so limits are enforced in code.
GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "gap_tags": {"type": "array", "items": {"type": "string", "enum": list(GAPS)}},
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "gap": {"type": "string", "enum": list(GAPS)},
                    "explanation": {"type": "string"},
                },
                "required": ["gap", "explanation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["gap_tags", "explanations"],
    "additionalProperties": False,
}

COMMENTER_SCHEMA = {
    "type": "object",
    "properties": {
        "display_name": {"type": "string"},
        "organization": {"type": "string"},
        "stakeholder_type": {"type": "string"},
        "source_identity_text": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["display_name", "organization", "stakeholder_type", "source_identity_text", "confidence"],
    "additionalProperties": False,
}
