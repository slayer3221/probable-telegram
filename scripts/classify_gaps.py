#!/usr/bin/env python3
"""Stage 5: tag each classified position with zero to three cross-cutting
gaps (classified/gaps).

Usage:
    python3 scripts/classify_gaps.py [--limit N] [--only COMMENT_ID]
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import ensure_dirs  # noqa: E402
from pipeline.llm import GAP_SCHEMA, LLM, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import GAPS  # noqa: E402

log = logging.getLogger("gaps")
GAP_LIST = "\n".join(f"- {k}: {v}" for k, v in GAPS.items())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    llm = LLM()
    template = load_prompt("classify_gaps")
    processed = fresh = 0

    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        positions = load_stage("positions", comment_id)
        if not positions:
            continue
        input_hash = hash_of_record(positions)
        existing = load_stage("gaps", comment_id)
        if stage_is_fresh(existing, input_hash):
            fresh += 1
            continue
        results = {}
        for pos in positions["positions"]:
            prompt = render(template, GAP_LIST=GAP_LIST, QUESTION_IDS=", ".join(pos["question_ids"]),
                            POSITION=pos["position"], PASSAGE=pos["source_passage"])
            out = llm.json(prompt, GAP_SCHEMA, max_tokens=1024)
            tags = [t for t in out.get("gap_tags", []) if t in GAPS][:3]
            results[pos["segment_id"]] = {"gap_tags": tags, "explanations": {t: out.get("explanations", {}).get(t, "") for t in tags}}
        save_stage("gaps", comment_id, stage_envelope(comment_id, input_hash, {"gaps": results}))
        processed += 1
        if args.limit and processed >= args.limit:
            break
    log.info("done: %d processed, %d already fresh; %d model calls", processed, fresh, llm.calls)


if __name__ == "__main__":
    main()
