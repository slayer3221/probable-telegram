#!/usr/bin/env python3
"""Stage 4b: one structured-output call per submission that assigns a
response type to each of its analyzed positions (classified/response_types).

The analysis record is the input; this sidecar reruns only when that record,
this prompt's version, the processing version or the model changes. The
segmentation and analysis caches are never touched.

Usage:
    python3 scripts/classify_response_types.py [--limit N] [--only COMMENT_ID] [--questions q1,q13]
    python3 scripts/classify_response_types.py --shadow haiku-compact --questions q1,q13

--questions restricts the run to submissions holding a position on any of
the given questions (used for small live tests).

--shadow VARIANT runs a named model/representation variant against the same
submissions and writes to classified/response_types_shadow/<variant>/
instead of the production directory, so the result can be compared with
compare_response_types.py before anything changes in production. The build
never reads shadow records.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import CLASSIFIED_DIR, LLM_MODEL, ensure_dirs  # noqa: E402
from pipeline.io_utils import read_json, write_json  # noqa: E402
from pipeline.llm import LLM, RESPONSE_TYPES_SCHEMA, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import RESPONSE_TYPES  # noqa: E402

log = logging.getLogger("response_types")
SHADOW_DIR = CLASSIFIED_DIR / "response_types_shadow"

# Representations of a position the prompt can receive. "full" is the
# production shape used in the first live test (JSON lines with question ids,
# stance, summary, concern and requested action). "compact" drops the JSON
# key overhead and question ids. "summary" sends only stance and summary.
REPRESENTATIONS = ("full", "compact", "summary")

# Named variants for shadow runs: (model, representation). None = production model.
VARIANTS = {
    "opus-full": (None, "full"),
    "opus-compact": (None, "compact"),
    "opus-summary": (None, "summary"),
    "haiku-full": ("claude-haiku-4-5-20251001", "full"),
    "haiku-compact": ("claude-haiku-4-5-20251001", "compact"),
    "haiku-summary": ("claude-haiku-4-5-20251001", "summary"),
    "sonnet-compact": ("claude-sonnet-4-5", "compact"),
}


def positions_text(positions, representation="full"):
    blocks = []
    for p in positions:
        if representation == "full":
            blocks.append(json.dumps({
                "segment_id": p["segment_id"],
                "question_ids": p["question_ids"],
                "stance": p["position"],
                "summary": p["public_summary"],
                "concern": p["stakeholder_concern"],
                "requested_fda_action": p["requested_fda_action"],
            }, ensure_ascii=False))
        elif representation == "compact":
            blocks.append(f"{p['segment_id']} | stance={p['position']} | summary: {p['public_summary']} | concern: {p['stakeholder_concern']} | asks FDA to: {p['requested_fda_action']}")
        elif representation == "summary":
            blocks.append(f"{p['segment_id']} | stance={p['position']} | {p['public_summary']}")
        else:
            raise ValueError(f"unknown representation {representation}")
    return "\n".join(blocks)


def output_budget(n_positions):
    """Enough tokens for one JSON entry per position plus headroom, so a
    large submission does not hit max_tokens and pay for a second call."""
    return max(1024, 48 * n_positions + 512)


def normalize(positions, out):
    """Every segment gets exactly one valid type; anything missing or invalid
    becomes no_clear_answer and is counted."""
    wanted = [p["segment_id"] for p in positions]
    got = {e.get("segment_id"): e.get("response_type") for e in out.get("positions", []) if isinstance(e, dict)}
    result, defaulted = {}, 0
    for seg in wanted:
        rtype = got.get(seg)
        if rtype not in RESPONSE_TYPES:
            rtype = "no_clear_answer"
            defaulted += 1
        result[seg] = rtype
    return result, defaulted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    parser.add_argument("--questions", default="", help="comma-separated question ids; restricts to submissions on them")
    parser.add_argument("--shadow", choices=sorted(VARIANTS), help="run a named variant into the shadow directory instead of production")
    parser.add_argument("--representation", choices=REPRESENTATIONS, default=None, help="override the position representation")
    parser.add_argument("--model", default=None, help="override the model")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    wanted_qs = set() if args.questions.strip().lower() == "all" else {q.strip() for q in args.questions.split(",") if q.strip()}
    model, representation = (VARIANTS[args.shadow] if args.shadow else (None, "full"))
    model = args.model or model or LLM_MODEL
    representation = args.representation or representation
    stage_name = f"response_types_shadow:{args.shadow}" if args.shadow else "response_types"
    llm = LLM(stage=stage_name, model=model)
    template = load_prompt("response_types")
    shadow_dir = (SHADOW_DIR / args.shadow) if args.shadow else None
    if shadow_dir:
        shadow_dir.mkdir(parents=True, exist_ok=True)
    log.info("model %s, representation %s, target %s", model, representation, shadow_dir or "classified/response_types")

    def load_target(comment_id):
        return read_json(shadow_dir / f"{comment_id}.json") if shadow_dir else load_stage("response_types", comment_id)

    def save_target(comment_id, record):
        if shadow_dir:
            record = dict(record, variant=args.shadow, representation=representation)
            write_json(shadow_dir / f"{comment_id}.json", record)
        else:
            save_stage("response_types", comment_id, record)

    pending, fresh, skipped = [], 0, 0
    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        analysis = load_stage("analysis", comment_id)
        if not analysis or not analysis.get("positions"):
            continue
        if wanted_qs and not any(set(p["question_ids"]) & wanted_qs for p in analysis["positions"]):
            skipped += 1
            continue
        input_hash = hash_of_record(analysis)
        existing = load_target(comment_id)
        if stage_is_fresh(existing, input_hash, "response_types", uses_model=False) and (existing or {}).get("model") == model:
            fresh += 1
            continue
        pending.append((comment_id, input_hash, analysis))
        if args.limit and len(pending) >= args.limit:
            break

    saved = []

    def run(task):
        comment_id, input_hash, analysis = task
        out = llm.json(render(template, POSITIONS=positions_text(analysis["positions"], representation)), RESPONSE_TYPES_SCHEMA,
                       max_tokens=output_budget(len(analysis["positions"])), effort="low")
        result, defaulted = normalize(analysis["positions"], out)
        if defaulted:
            llm.metrics.add("response_types_defaulted", defaulted)
        # Persist as soon as this submission is done, so an aborted run keeps
        # every completed record and the next run resumes from the cache.
        record = stage_envelope(comment_id, input_hash, {"response_types": result}, "response_types")
        record["model"] = model
        save_target(comment_id, record)
        saved.append(comment_id)
        log.info("%s: %d response types", comment_id, len(result))
        return comment_id

    try:
        llm.map(run, pending)
    finally:
        metrics = llm.finish(records_processed=len(saved), records_pending_at_exit=len(pending) - len(saved),
                             records_reused=fresh, records_outside_questions=skipped)
        log.info("done: %d processed, %d already fresh, %d outside requested questions; %d model calls in %.0fs (est. $%s)",
                 len(saved), fresh, skipped, metrics["llm_calls"], metrics["elapsed_seconds"], metrics["estimated_cost_usd"])


if __name__ == "__main__":
    main()
