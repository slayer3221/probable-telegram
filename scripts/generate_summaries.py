#!/usr/bin/env python3
"""Stage 6: write a neutral public summary (max 45 words) for each classified
position (classified/summaries).

Usage:
    python3 scripts/generate_summaries.py [--limit N] [--only COMMENT_ID]
"""
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import PROMPT_CONFIG, ensure_dirs  # noqa: E402
from pipeline.llm import LLM, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402

log = logging.getLogger("summaries")
MAX_WORDS = PROMPT_CONFIG.get("summary_max_words", 45)


def word_count(text):
    return len(re.findall(r"\S+", text))


def shorten(text):
    """Last resort: keep whole sentences up to the word limit."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for s in sentences:
        if word_count(" ".join(out + [s])) > MAX_WORDS:
            break
        out.append(s)
    return " ".join(out) if out else " ".join(text.split()[:MAX_WORDS])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    llm = LLM()
    template = load_prompt("public_summary")
    processed = fresh = 0

    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        positions = load_stage("positions", comment_id)
        if not positions:
            continue
        input_hash = hash_of_record(positions)
        existing = load_stage("summaries", comment_id)
        if stage_is_fresh(existing, input_hash):
            fresh += 1
            continue
        results = {}
        for pos in positions["positions"]:
            prompt = render(template, QUESTION_IDS=", ".join(pos["question_ids"]), POSITION=pos["position"],
                            CONCERN=pos["stakeholder_concern"], ACTION=pos["requested_fda_action"], PASSAGE=pos["source_passage"])
            summary = llm.text(prompt, max_tokens=2048, effort="low")
            attempts = 1
            while word_count(summary) > MAX_WORDS and attempts < 3:
                summary = llm.text(prompt + f"\n\nYour previous answer had {word_count(summary)} words. Rewrite it in at most {MAX_WORDS} words.", max_tokens=2048, effort="low")
                attempts += 1
            if word_count(summary) > MAX_WORDS:
                log.warning("%s %s: summary still long after retries; shortened at sentence boundary", comment_id, pos["segment_id"])
                summary = shorten(summary)
            results[pos["segment_id"]] = summary.strip().strip('"')
        save_stage("summaries", comment_id, stage_envelope(comment_id, input_hash, {"summaries": results}))
        processed += 1
        if args.limit and processed >= args.limit:
            break
    log.info("done: %d processed, %d already fresh; %d model calls", processed, fresh, llm.calls)


if __name__ == "__main__":
    main()
