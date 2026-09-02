#!/usr/bin/env python3
"""Stage 4: one structured-output call per substantive position that
classifies the position, tags cross-cutting gaps and writes the public
summary (classified/analysis). Positions across all pending submissions run
with bounded concurrency.

The three outputs stay separate fields in the stored record. A summary over
the word limit gets one short rewrite call; if still long it is cut at a
sentence boundary and flagged.

Usage:
    python3 scripts/analyze_positions.py [--limit N] [--only COMMENT_ID]
"""
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import PROMPT_CONFIG, ensure_dirs  # noqa: E402
from pipeline.llm import ANALYSIS_SCHEMA, LLM, load_prompt, render  # noqa: E402
from pipeline.store import hash_of_record, list_raw_comment_ids, load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import GAPS, ISSUES  # noqa: E402

log = logging.getLogger("analyze")
ISSUE_LIST = "\n".join(f"- {k}: {v}" for k, v in ISSUES.items())
GAP_LIST = "\n".join(f"- {k}: {v}" for k, v in GAPS.items())
MAX_WORDS = PROMPT_CONFIG.get("summary_max_words", 45)


def word_count(text):
    return len(re.findall(r"\S+", text))


def shorten(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for s in sentences:
        if word_count(" ".join(out + [s])) > MAX_WORDS:
            break
        out.append(s)
    return " ".join(out) if out else " ".join(text.split()[:MAX_WORDS])


def normalize(seg, out, llm, template_shorten):
    qids = [q for q in out.get("question_ids") or [] if re.fullmatch(r"q([1-9]|1\d|2[0-6])", q)] or seg["question_ids"]
    primary = out.get("primary_issue") if out.get("primary_issue") in ISSUES else "regulatory_scope"
    secondary = out.get("secondary_issue") if out.get("secondary_issue") in ISSUES else None
    tags = []
    for t in out.get("gap_tags", []):
        if t in GAPS and t not in tags:
            tags.append(t)
    tags = tags[:3]  # zero to three gaps per position, enforced here
    explained = {e.get("gap"): e.get("explanation", "") for e in out.get("gap_explanations", []) if isinstance(e, dict)}
    summary = (out.get("public_summary") or "").strip().strip('"')
    shortened = False
    if word_count(summary) > MAX_WORDS:
        llm.metrics.add("summary_rewrites")
        summary = llm.text(render(template_shorten, WORDS=word_count(summary), MAX_WORDS=MAX_WORDS, SUMMARY=summary), max_tokens=1024, effort="low").strip().strip('"')
        if word_count(summary) > MAX_WORDS:
            llm.metrics.add("summaries_cut_at_sentence")
            summary = shorten(summary)
            shortened = True
    return {
        "segment_id": seg["segment_id"],
        "question_ids": sorted(set(qids)),
        "position": out["position"],
        "primary_issue": primary,
        "secondary_issue": secondary if secondary != primary else None,
        "stakeholder_concern": out.get("stakeholder_concern", "").strip(),
        "requested_fda_action": out.get("requested_fda_action", "").strip(),
        "confidence": out.get("confidence", "low"),
        "gap_tags": tags,
        "gap_explanations": {t: explained.get(t, "") for t in tags},
        "public_summary": summary,
        "summary_cut": shortened,
        "source_passage": seg["source_passage"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    llm = LLM(stage="analyze")
    template = load_prompt("analyze")
    template_shorten = load_prompt("shorten_summary")

    pending, fresh = [], 0
    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        segments = load_stage("segments", comment_id)
        if not segments:
            continue
        input_hash = hash_of_record(segments)
        if stage_is_fresh(load_stage("analysis", comment_id), input_hash, "analysis"):
            fresh += 1
            continue
        pending.append((comment_id, input_hash, segments))
        if args.limit and len(pending) >= args.limit:
            break

    tasks = [(comment_id, seg) for comment_id, _, segments in pending for seg in segments["positions"]]

    def run(task):
        comment_id, seg = task
        prompt = render(template, ISSUE_LIST=ISSUE_LIST, GAP_LIST=GAP_LIST, QUESTION_IDS=", ".join(seg["question_ids"]), PASSAGE=seg["source_passage"])
        out = llm.json(prompt, ANALYSIS_SCHEMA, max_tokens=4096)
        return comment_id, normalize(seg, out, llm, template_shorten)

    results = llm.map(run, tasks)

    for comment_id, input_hash, segments in pending:
        positions = [r[1] for r in results if r[0] == comment_id]
        save_stage("analysis", comment_id, stage_envelope(comment_id, input_hash, {"positions": positions}, "analysis"))
        log.info("%s: analyzed %d positions", comment_id, len(positions))

    metrics = llm.finish(records_processed=len(pending), records_reused=fresh, positions_analyzed=len(tasks))
    log.info("done: %d processed, %d already fresh; %d positions; %d model calls in %.0fs (est. $%s)",
             len(pending), fresh, len(tasks), metrics["llm_calls"], metrics["elapsed_seconds"], metrics["estimated_cost_usd"])


if __name__ == "__main__":
    main()
