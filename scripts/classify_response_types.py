#!/usr/bin/env python3
"""Stage 4b: one structured-output call per submission that assigns a
response type to each of its analyzed positions (classified/response_types).

The analysis record is the input; this sidecar reruns only when that record,
this prompt's version, the processing version or the model changes. The
segmentation and analysis caches are never touched.

Usage:
    python3 scripts/classify_response_types.py [--limit N] [--only COMMENT_ID] [--questions q1,q13]

--questions restricts the run to submissions holding a position on any of
the given questions (used for small live tests).
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import ensure_dirs  # noqa: E402
from pipeline.llm import LLM, RESPONSE_TYPES_SCHEMA, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import RESPONSE_TYPES  # noqa: E402

log = logging.getLogger("response_types")


def positions_text(positions):
    blocks = []
    for p in positions:
        blocks.append(json.dumps({
            "segment_id": p["segment_id"],
            "question_ids": p["question_ids"],
            "stance": p["position"],
            "summary": p["public_summary"],
            "concern": p["stakeholder_concern"],
            "requested_fda_action": p["requested_fda_action"],
        }, ensure_ascii=False))
    return "\n".join(blocks)


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
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    wanted_qs = {q.strip() for q in args.questions.split(",") if q.strip()}
    llm = LLM(stage="response_types")
    template = load_prompt("response_types")

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
        if stage_is_fresh(load_stage("response_types", comment_id), input_hash, "response_types"):
            fresh += 1
            continue
        pending.append((comment_id, input_hash, analysis))
        if args.limit and len(pending) >= args.limit:
            break

    saved = []

    def run(task):
        comment_id, input_hash, analysis = task
        out = llm.json(render(template, POSITIONS=positions_text(analysis["positions"])), RESPONSE_TYPES_SCHEMA, max_tokens=2048, effort="low")
        result, defaulted = normalize(analysis["positions"], out)
        if defaulted:
            llm.metrics.add("response_types_defaulted", defaulted)
        # Persist as soon as this submission is done, so an aborted run keeps
        # every completed record and the next run resumes from the cache.
        save_stage("response_types", comment_id, stage_envelope(comment_id, input_hash, {"response_types": result}, "response_types"))
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
