#!/usr/bin/env python3
"""Stage 3: identify the commenter and break each usable submission into
substantive positions mapped to FDA questions (classified/segments and
classified/commenters.json).

Long submissions are processed in overlapping chunks; chunks and commenter
identification for all pending submissions run with bounded concurrency.
Positions duplicated across chunk boundaries are merged.

Usage:
    python3 scripts/segment_comments.py [--limit N] [--only COMMENT_ID]
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import CLASSIFIED_COMMENTERS, LLM_MODEL, PROMPT_CONFIG, ensure_dirs, prompt_version  # noqa: E402
from pipeline.io_utils import read_json, write_json  # noqa: E402
from pipeline.llm import COMMENTER_SCHEMA, LLM, SEGMENT_SCHEMA, load_prompt, render  # noqa: E402
from pipeline.store import (list_raw_comment_ids, load_raw_comment, load_raw_text, load_stage,  # noqa: E402
                            load_text_meta, save_stage, stage_envelope, stage_is_fresh)
from pipeline.taxonomies import STAKEHOLDER_TYPES  # noqa: E402

log = logging.getLogger("segment")
CHUNK = PROMPT_CONFIG.get("segment_chunk_chars", 24000)
OVERLAP = PROMPT_CONFIG.get("segment_overlap_chars", 1500)


def chunks(text):
    if len(text) <= CHUNK:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):
            cut = text.rfind("\n\n", start + CHUNK // 2, end)
            if cut > start:
                end = cut
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return out


def _key(passage):
    return re.sub(r"\W+", " ", passage.lower()).strip()[:160]


def merge(positions):
    seen, out = {}, []
    for p in positions:
        if p.get("is_background_only"):
            continue
        qids = sorted(set(q for q in p.get("question_ids", []) if re.fullmatch(r"q([1-9]|1\d|2[0-6])", q)))
        if not qids or len(p.get("source_passage", "").strip()) < 40:
            continue
        k = _key(p["source_passage"])
        if k in seen:
            existing = seen[k]
            existing["question_ids"] = sorted(set(existing["question_ids"]) | set(qids))
            continue
        rec = {"question_ids": qids, "source_passage": p["source_passage"].strip(), "position_gist": p.get("position_gist", "").strip()}
        seen[k] = rec
        out.append(rec)
    for i, rec in enumerate(out, start=1):
        rec["segment_id"] = f"seg-{i:03d}"
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    llm = LLM(stage="segment")
    commenters = read_json(CLASSIFIED_COMMENTERS, {"commenters": {}})
    segment_template = load_prompt("segment")
    commenter_template = load_prompt("classify_commenter")
    commenter_version = prompt_version("classify_commenter")

    # Plan the work first so every model call across all pending submissions
    # can share one bounded pool.
    pending, fresh, skipped = [], 0, 0
    for comment_id in list_raw_comment_ids():
        if args.only and comment_id != args.only:
            continue
        meta = load_text_meta(comment_id)
        if not meta.get("usable"):
            skipped += 1
            continue
        source_hash = meta["content_hash"]
        commenter = commenters["commenters"].get(comment_id)
        commenter_fresh = bool(commenter and commenter.get("input_hash") == source_hash
                               and commenter.get("prompt_version") == commenter_version and commenter.get("model") == LLM_MODEL)
        segments_fresh = stage_is_fresh(load_stage("segments", comment_id), source_hash, "segments")
        if commenter_fresh and segments_fresh:
            fresh += 1
            continue
        pending.append((comment_id, source_hash, commenter_fresh, segments_fresh))
        if args.limit and len(pending) >= args.limit:
            break

    tasks = []
    for comment_id, source_hash, commenter_fresh, segments_fresh in pending:
        raw = load_raw_comment(comment_id)
        text = load_raw_text(comment_id)
        if not commenter_fresh:
            attrs = raw.get("attributes", {})
            meta = {k: attrs.get(k) for k in ("organization", "category", "submitterRep", "govAgency", "govAgencyType", "title") if attrs.get(k)}
            tasks.append(("commenter", comment_id, 0, render(commenter_template, METADATA=json.dumps(meta, ensure_ascii=False), TEXT=text[:6000])))
        if not segments_fresh:
            parts = chunks(text)
            for i, part in enumerate(parts, start=1):
                tasks.append(("chunk", comment_id, i, render(segment_template, TEXT=part, CHUNK_INDEX=i, CHUNK_TOTAL=len(parts))))

    def run(task):
        kind, comment_id, index, prompt = task
        if kind == "commenter":
            return kind, comment_id, index, llm.json(prompt, COMMENTER_SCHEMA, max_tokens=1024)
        return kind, comment_id, index, llm.json(prompt, SEGMENT_SCHEMA, max_tokens=8192)

    results = llm.map(run, tasks)

    for comment_id, source_hash, commenter_fresh, segments_fresh in pending:
        mine = [r for r in results if r[1] == comment_id]
        if not commenter_fresh:
            info = next(r[3] for r in mine if r[0] == "commenter")
            if info.get("stakeholder_type") not in STAKEHOLDER_TYPES:
                info["stakeholder_type"] = "other"
            info.update({"input_hash": source_hash, "prompt_version": commenter_version, "model": LLM_MODEL})
            commenters["commenters"][comment_id] = info
        if not segments_fresh:
            chunk_results = sorted((r for r in mine if r[0] == "chunk"), key=lambda r: r[2])
            found = [p for r in chunk_results for p in r[3].get("positions", [])]
            positions = merge(found)
            save_stage("segments", comment_id, stage_envelope(comment_id, source_hash, {"chunks": len(chunk_results), "positions": positions}, "segments"))
            log.info("%s: %d substantive positions from %d chunk(s)", comment_id, len(positions), len(chunk_results))
    write_json(CLASSIFIED_COMMENTERS, commenters)

    metrics = llm.finish(records_processed=len(pending), records_reused=fresh, records_skipped=skipped, chunks=sum(1 for t in tasks if t[0] == "chunk"))
    log.info("done: %d processed, %d already fresh, %d skipped (no usable text); %d model calls in %.0fs (est. $%s)",
             len(pending), fresh, skipped, metrics["llm_calls"], metrics["elapsed_seconds"], metrics["estimated_cost_usd"])


if __name__ == "__main__":
    main()
