#!/usr/bin/env python3
"""Stage 4: classify each substantive position (classified/positions).

Usage:
    python3 scripts/classify_positions.py [--limit N] [--only COMMENT_ID]
"""
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import ensure_dirs  # noqa: E402
from pipeline.llm import LLM, POSITION_SCHEMA, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import ISSUES  # noqa: E402

log = logging.getLogger("classify")
ISSUE_LIST = "\n".join(f"- {k}: {v}" for k, v in ISSUES.items())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    llm = LLM()
    template = load_prompt("classify_position")
    processed = fresh = 0

    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        segments = load_stage("segments", comment_id)
        if not segments:
            continue
        input_hash = hash_of_record(segments)
        existing = load_stage("positions", comment_id)
        if stage_is_fresh(existing, input_hash):
            fresh += 1
            continue
        results = []
        for seg in segments["positions"]:
            prompt = render(template, ISSUE_LIST=ISSUE_LIST, QUESTION_IDS=", ".join(seg["question_ids"]), PASSAGE=seg["source_passage"])
            out = llm.json(prompt, POSITION_SCHEMA, max_tokens=2048)
            qids = [q for q in out.get("question_ids") or [] if re.fullmatch(r"q([1-9]|1\d|2[0-6])", q)]
            if not qids:
                qids = seg["question_ids"]
            primary = out.get("primary_issue") if out.get("primary_issue") in ISSUES else "regulatory_scope"
            secondary = out.get("secondary_issue") if out.get("secondary_issue") in ISSUES else None
            results.append({
                "segment_id": seg["segment_id"],
                "question_ids": sorted(set(qids)),
                "position": out["position"],
                "primary_issue": primary,
                "secondary_issue": secondary if secondary != primary else None,
                "stakeholder_concern": out.get("stakeholder_concern", "").strip(),
                "requested_fda_action": out.get("requested_fda_action", "").strip(),
                "confidence": out.get("confidence", "low"),
                "source_passage": seg["source_passage"],
            })
        save_stage("positions", comment_id, stage_envelope(comment_id, input_hash, {"positions": results}))
        log.info("%s: classified %d positions", comment_id, len(results))
        processed += 1
        if args.limit and processed >= args.limit:
            break
    log.info("done: %d processed, %d already fresh; %d model calls", processed, fresh, llm.calls)


if __name__ == "__main__":
    main()
