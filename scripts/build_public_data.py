#!/usr/bin/env python3
"""Stage 7: assemble the public JSON in data/ from raw/ and classified/,
write public/build-manifest.json, snapshot each question's state and write
the private editorial review queue.

Curated editorial files in editorial/ are read, never written.

Usage:
    python3 scripts/build_public_data.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.aggregate import build_public_dataset  # noqa: E402
from pipeline.assemble import assemble_dataset, positions_by_question  # noqa: E402
from pipeline.config import (DATA_DIR, DOCKET_META, LLM_MODEL, PROCESSING_VERSION, PROMPT_VERSIONS, PUBLIC_DIR,  # noqa: E402
                             QUESTION_STATE_PATH, REVIEW_QUEUE_PATH, ensure_dirs)
from pipeline.consolidate import RULE_VERSION as CONSOLIDATION_RULE_VERSION  # noqa: E402
from pipeline.io_utils import now_iso, read_json, write_json  # noqa: E402
from pipeline.review import STATE_VERSION, build_review_queue, question_snapshot  # noqa: E402
from pipeline.store import load_stage, stage_is_fresh  # noqa: E402
from pipeline.textclean import clean_text, has_broken_escapes  # noqa: E402

log = logging.getLogger("build")
PUBLIC_ANALYSIS_FIELDS = ("saying", "dominant_response_type", "response_type_distribution", "disagreement",
                          "stakeholder_divide", "evidence_position_ids", "distinct_commenters", "distinct_submissions",
                          "positions", "comparable_groups")


def question_analyses(questions, grouped):
    """One public record per question from classified/synthesis. A record is
    'generated' when it matches the current positions, 'stale' when the
    positions changed since it was written, and 'pending' when none exists."""
    from synthesize_questions import synthesis_input  # local import: script module, not a package
    out, internal, broken = [], {}, []
    for q in questions:
        qid = q["id"]
        rows = grouped.get(qid, [])
        record = load_stage("synthesis", qid)
        if not rows or not record:
            out.append({"question_id": qid, "status": "pending", "distinct_commenters": len({r["commenter_id"] for r in rows}),
                        "positions": len(rows)})
            internal[qid] = None
            continue
        _, input_hash = synthesis_input(qid, q, rows)
        status = "generated" if stage_is_fresh(record, input_hash, "synthesis") else "stale"
        public = {"question_id": qid, "status": status}
        public.update({k: record.get(k) for k in PUBLIC_ANALYSIS_FIELDS})
        # Records written before text cleanup existed are cleaned here; a record
        # whose text is still broken after cleanup is reported for regeneration.
        public["saying"] = clean_text(record.get("saying"))
        public["disagreement"] = dict(record["disagreement"])
        public["disagreement"]["text"] = clean_text(record["disagreement"].get("text"))
        public["disagreement"]["sides"] = [{"summary": clean_text(s["summary"]), "position_ids": s["position_ids"]} for s in record["disagreement"].get("sides", [])]
        public["stakeholder_divide"] = dict(record["stakeholder_divide"], text=clean_text(record["stakeholder_divide"].get("text")))
        if any(has_broken_escapes(t) for t in (record.get("saying"), record["disagreement"].get("text"))):
            broken.append(qid)
        out.append(public)
        internal[qid] = dict(record, status=status)
    if broken:
        log.warning("synthesis text with broken escapes (regenerate these questions): %s", ", ".join(broken))
    return out, internal


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    data = assemble_dataset(write_provenance=True)
    if not data["positions"]:
        log.error("no classified positions found; data/ left unchanged. Run the earlier stages first.")
        sys.exit(2)

    meta = {
        "generated_at": now_iso(),
        "dataset_kind": "live",
        "processing_version": f"{PROCESSING_VERSION}+analyze-{PROMPT_VERSIONS.get('analyze', '0')}",
        "docket": DOCKET_META,
    }
    files = build_public_dataset(data["questions"], data["commenters"], data["submissions"], data["positions"],
                                 data["editorial_gaps"], data["editorial_cards"], meta)
    commenters_by_id = {c["id"]: c for c in files["commenters.json"]["commenters"]}
    grouped = positions_by_question(files["positions.json"]["positions"], commenters_by_id)
    analyses, internal = question_analyses(data["questions"], grouped)
    files["analyses.json"] = {"generated_at": meta["generated_at"], "analyses": analyses}
    for name, payload in files.items():
        write_json(DATA_DIR / name, payload)

    # Question-level change detection: compare with the previous build's snapshot.
    prior = read_json(QUESTION_STATE_PATH, None)
    prior_state = (prior or {}).get("questions") or None
    new_state = {q["id"]: question_snapshot(q["id"], grouped.get(q["id"], []), internal.get(q["id"]), q["id"] in data["vahana_read"])
                 for q in data["questions"]}
    queue = build_review_queue(prior_state, new_state, meta["generated_at"])
    queue["compared_against"] = (prior or {}).get("generated_at")
    write_json(REVIEW_QUEUE_PATH, queue)
    write_json(QUESTION_STATE_PATH, {"generated_at": meta["generated_at"], "state_version": STATE_VERSION, "questions": new_state})

    statuses = {s: sum(1 for a in analyses if a["status"] == s) for s in ("generated", "stale", "pending")}
    manifest = {
        "generated_at": meta["generated_at"],
        "processing_version": PROCESSING_VERSION,
        "prompt_versions": PROMPT_VERSIONS,
        "model": LLM_MODEL,
        "counts": files["site-summary.json"]["metrics"],
        "exclusions": dict(data["exclusions"]),
        "excluded_submissions": data["excluded_ids"],
        "consolidation": {
            "rule_version": CONSOLIDATION_RULE_VERSION,
            "submissions_affected": len(data["consolidation_log"]),
            "positions_merged": sum(c["positions_merged"] for c in data["consolidation_log"]),
            "submissions": data["consolidation_log"],
        },
        "response_types": {"submissions_without_fresh_response_types": data["response_types_missing"]},
        "question_analyses": statuses,
        "review_queue": {"flagged_questions": [f["question_id"] for f in queue["flagged"]], "baseline": queue["baseline"]},
    }
    write_json(PUBLIC_DIR / "build-manifest.json", manifest)
    log.info("built data/: %s", files["site-summary.json"]["metrics"])
    if data["exclusions"]:
        log.info("exclusions: %s", dict(data["exclusions"]))
    if data["consolidation_log"]:
        log.info("consolidated %d near-duplicate positions across %d submissions",
                 manifest["consolidation"]["positions_merged"], len(data["consolidation_log"]))
    log.info("question analyses: %s; review queue: %s", statuses,
             ", ".join(manifest["review_queue"]["flagged_questions"]) or ("baseline" if queue["baseline"] else "nothing flagged"))


if __name__ == "__main__":
    main()
