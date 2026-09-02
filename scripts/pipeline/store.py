"""Filesystem layout for raw (source-faithful) and classified (AI-derived)
records, plus the staleness rule that decides when a stage must rerun.

A stage output is reused when all of the following match the current run:
- input_hash  : hash of the upstream content it was derived from
- prompt_version and processing_version
- model (for LLM stages)
"""
from .config import (
    CLASSIFIED_GAPS, CLASSIFIED_POSITIONS, CLASSIFIED_SEGMENTS, CLASSIFIED_SUMMARIES,
    LLM_MODEL, PROCESSING_VERSION, PROMPT_VERSION, RAW_COMMENTS, RAW_TEXT,
)
from .io_utils import content_hash, now_iso, read_json, write_json

STAGE_DIRS = {
    "segments": CLASSIFIED_SEGMENTS,
    "positions": CLASSIFIED_POSITIONS,
    "gaps": CLASSIFIED_GAPS,
    "summaries": CLASSIFIED_SUMMARIES,
}


def raw_comment_path(comment_id):
    return RAW_COMMENTS / f"{comment_id}.json"


def raw_text_path(comment_id):
    return RAW_TEXT / f"{comment_id}.txt"


def raw_text_meta_path(comment_id):
    return RAW_TEXT / f"{comment_id}.meta.json"


def list_raw_comment_ids():
    return sorted(p.stem for p in RAW_COMMENTS.glob("*.json"))


def load_raw_comment(comment_id):
    return read_json(raw_comment_path(comment_id))


def load_raw_text(comment_id):
    path = raw_text_path(comment_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_text_meta(comment_id):
    return read_json(raw_text_meta_path(comment_id), {})


def stage_path(stage, comment_id):
    return STAGE_DIRS[stage] / f"{comment_id}.json"


def load_stage(stage, comment_id):
    return read_json(stage_path(stage, comment_id))


def stage_is_fresh(record, input_hash, uses_model=True):
    if not record:
        return False
    if record.get("input_hash") != input_hash:
        return False
    if record.get("prompt_version") != PROMPT_VERSION or record.get("processing_version") != PROCESSING_VERSION:
        return False
    if uses_model and record.get("model") != LLM_MODEL:
        return False
    return True


def stage_envelope(comment_id, input_hash, payload, uses_model=True):
    env = {
        "comment_id": comment_id,
        "input_hash": input_hash,
        "prompt_version": PROMPT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "created_at": now_iso(),
    }
    if uses_model:
        env["model"] = LLM_MODEL
    env.update(payload)
    return env


def save_stage(stage, comment_id, record):
    write_json(stage_path(stage, comment_id), record)


def hash_of_record(record):
    """Stable hash of a stage record's content, ignoring timestamps."""
    import json
    trimmed = {k: v for k, v in (record or {}).items() if k != "created_at"}
    return content_hash(json.dumps(trimmed, sort_keys=True, ensure_ascii=False))
