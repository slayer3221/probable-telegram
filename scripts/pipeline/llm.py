"""Anthropic client for the classification stages, with bounded concurrency
and per-stage run metrics.

All AI processing happens here, during ingestion. The frontend never calls a
model. Prompts live in prompts/*.md and are versioned per stage in
prompts/config.json.
"""
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import (
    LLM_API_KEY, LLM_CONCURRENCY, LLM_MODEL, LLM_WORKSPACE_ID, PRICING, PROMPT_CONFIG,
    PROMPTS_DIR, RUN_METRICS_PATH, env,
)
from .io_utils import ROOT, now_iso, read_json, write_json
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
    """Question identifiers and exact text for the system prompt."""
    data = read_json(ROOT / "data" / "questions.json")
    lines = []
    for q in data["questions"]:
        text = (q.get("question_text") or "").strip()
        if text:
            lines.append(f"{q['id']} (Q{q['question_number']}, theme {q['theme']}): {text}")
        else:
            lines.append(f"{q['id']} (Q{q['question_number']}, theme {q['theme']}): [exact FDA text pending] {q['short_title']}. {q.get('summary_ask', '')}")
    return "\n".join(lines)


def system_prompt() -> str:
    return render((PROMPTS_DIR / "system.md").read_text(encoding="utf-8"), QUESTION_LIST=question_list_text())


class Metrics:
    """Thread-safe counters for one pipeline stage."""

    FIELDS = ("llm_calls", "retries", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")

    def __init__(self, stage):
        self.stage = stage
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.counts = {f: 0 for f in self.FIELDS}
        self.extra = {}

    def record(self, usage, retries=0):
        with self.lock:
            self.counts["llm_calls"] += 1
            self.counts["retries"] += retries
            if usage is not None:
                self.counts["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
                self.counts["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
                self.counts["cache_read_tokens"] += getattr(usage, "cache_read_input_tokens", 0) or 0
                self.counts["cache_write_tokens"] += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def add(self, key, value=1):
        with self.lock:
            self.extra[key] = self.extra.get(key, 0) + value

    def estimated_cost(self, model):
        price = PRICING.get(model)
        if not price:
            return None
        c = self.counts
        usd = (c["input_tokens"] * price["input"] + c["output_tokens"] * price["output"]
               + c["cache_read_tokens"] * price["cache_read"] + c["cache_write_tokens"] * price["cache_write"]) / 1_000_000
        return round(usd, 4)

    def as_dict(self, model):
        out = {"elapsed_seconds": round(time.monotonic() - self.started, 1), "model": model}
        out.update(self.counts)
        out.update(self.extra)
        out["estimated_cost_usd"] = self.estimated_cost(model)
        return out


def save_stage_metrics(stage, payload):
    """Append one stage's metrics to public/run-metrics.json for this run."""
    run_id = env("GITHUB_RUN_ID", "local")
    data = read_json(RUN_METRICS_PATH, {}) or {}
    if data.get("run_id") != run_id:
        data = {"run_id": run_id, "started_at": now_iso(), "stages": {}}
    data["stages"][stage] = payload
    data["updated_at"] = now_iso()
    totals = {k: 0 for k in Metrics.FIELDS}
    cost = 0.0
    seconds = 0.0
    for st in data["stages"].values():
        for k in Metrics.FIELDS:
            totals[k] += st.get(k, 0) or 0
        cost += st.get("estimated_cost_usd") or 0
        seconds += st.get("elapsed_seconds") or 0
    totals["estimated_cost_usd"] = round(cost, 4)
    totals["elapsed_seconds"] = round(seconds, 1)
    data["totals"] = totals
    write_json(RUN_METRICS_PATH, data)


class LLM:
    def __init__(self, stage="llm", model=None, max_tokens=None, concurrency=None):
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
        self.concurrency = max(1, concurrency or LLM_CONCURRENCY)
        self.system = system_prompt()
        self.metrics = Metrics(stage)

    @property
    def calls(self):
        return self.metrics.counts["llm_calls"]

    def map(self, fn, items):
        """Run fn over items with bounded concurrency; results keep input order.
        The first exception is re-raised after the pool drains."""
        if not items:
            return []
        if self.concurrency == 1 or len(items) == 1:
            return [fn(item) for item in items]
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return list(pool.map(fn, items))

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
        retries = 0
        for attempt in range(7):
            try:
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
                retries += 1
                time.sleep(delay)
                continue
            except (self.anthropic.APIStatusError, self.anthropic.APIConnectionError) as exc:
                status = getattr(exc, "status_code", None)
                transient = status is None or status >= 500 or status == 429
                if not transient or attempt == 6:
                    raise
                delay = min(60, 5 * (2 ** attempt)) + random.uniform(0, 2)
                log.warning("transient API error (%s); retrying in %.0fs (attempt %d/7)", status or type(exc).__name__, delay, attempt + 1)
                retries += 1
                time.sleep(delay)
                continue
            self.metrics.record(getattr(resp, "usage", None), retries)
            retries = 0
            if resp.stop_reason == "refusal":
                raise RuntimeError("model declined the request")
            if resp.stop_reason == "max_tokens":
                log.warning("response hit max_tokens; retrying with a larger budget")
                kwargs["max_tokens"] = kwargs["max_tokens"] * 2
                retries += 1
                continue
            return "".join(b.text for b in resp.content if b.type == "text")
        raise RuntimeError("model call failed after retries")

    def json(self, prompt, schema, max_tokens=None, effort=None):
        text = self._create(prompt, output_config={"format": {"type": "json_schema", "schema": schema}}, max_tokens=max_tokens, effort=effort)
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

    def finish(self, **extra):
        """Persist this stage's metrics and return them."""
        payload = self.metrics.as_dict(self.model)
        payload.update(extra)
        save_stage_metrics(self.metrics.stage, payload)
        return payload


# JSON schemas -----------------------------------------------------------
# The structured-output validator rejects some JSON Schema keywords
# (maxItems was refused with HTTP 400), so list limits are enforced in code.
QIDS = {"type": "array", "items": {"type": "string", "enum": [f"q{n}" for n in range(1, 27)]}}
GAP_IDS = {"type": "string", "enum": list(GAPS)}

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

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "question_ids": QIDS,
        "position": {"type": "string", "enum": ["support", "support_with_modification", "oppose", "mixed", "unclear"]},
        "primary_issue": {"type": "string"},
        "secondary_issue": {"type": ["string", "null"]},
        "stakeholder_concern": {"type": "string"},
        "requested_fda_action": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "gap_tags": {"type": "array", "items": GAP_IDS},
        "gap_explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"gap": GAP_IDS, "explanation": {"type": "string"}},
                "required": ["gap", "explanation"],
                "additionalProperties": False,
            },
        },
        "public_summary": {"type": "string"},
    },
    "required": ["question_ids", "position", "primary_issue", "secondary_issue", "stakeholder_concern",
                 "requested_fda_action", "confidence", "gap_tags", "gap_explanations", "public_summary"],
    "additionalProperties": False,
}

RESPONSE_TYPE_IDS = {"type": "string", "enum": ["direct_answer", "recommendation", "concern", "proposed_criterion",
                                                "evidence_suggestion", "scope_challenge", "implementation_issue", "no_clear_answer"]}
DISAGREEMENT_TOPIC_IDS = {"type": "string", "enum": ["thresholds", "scope", "evidence_burden", "ownership", "implementation",
                                                     "definitions", "timing", "degree_of_autonomy"]}

# One call per submission: a response type for every position it holds.
RESPONSE_TYPES_SCHEMA = {
    "type": "object",
    "properties": {
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"segment_id": {"type": "string"}, "response_type": RESPONSE_TYPE_IDS},
                "required": ["segment_id", "response_type"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["positions"],
    "additionalProperties": False,
}

# One call per question: a descriptive synthesis of the positions on it.
SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "saying": {"type": "string"},
        "dominant_response_type": RESPONSE_TYPE_IDS,
        "disagreement": {
            "type": "object",
            "properties": {
                "exists": {"type": "boolean"},
                "about": {"type": "array", "items": DISAGREEMENT_TOPIC_IDS},
                "text": {"type": "string"},
                "sides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}, "position_ids": {"type": "array", "items": {"type": "string"}}},
                        "required": ["summary", "position_ids"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["exists", "about", "text", "sides"],
            "additionalProperties": False,
        },
        "stakeholder_divide": {
            "type": "object",
            "properties": {
                "claimed": {"type": "boolean"},
                "groups": {"type": "array", "items": {"type": "string"}},
                "text": {"type": "string"},
            },
            "required": ["claimed", "groups", "text"],
            "additionalProperties": False,
        },
        "evidence_position_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["saying", "dominant_response_type", "disagreement", "stakeholder_divide", "evidence_position_ids"],
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
