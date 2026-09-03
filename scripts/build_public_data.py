#!/usr/bin/env python3
"""Stage 7: assemble the public JSON in data/ from raw/ and classified/ and
write public/build-manifest.json.

Curated editorial files in editorial/ are read, never written.

Usage:
    python3 scripts/build_public_data.py
"""
import logging
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.aggregate import build_public_dataset  # noqa: E402
from pipeline.config import (CLASSIFIED_COMMENTERS, CLASSIFIED_CONSOLIDATION, DATA_DIR, DOCKET_META, EDITORIAL_DIR,  # noqa: E402
                             LLM_MODEL, PROCESSING_VERSION, PROMPT_VERSIONS, PUBLIC_DIR, ensure_dirs)
from pipeline.consolidate import RULE_VERSION as CONSOLIDATION_RULE_VERSION, consolidate_positions  # noqa: E402
from pipeline.io_utils import now_iso, read_json, write_json  # noqa: E402
from pipeline.store import (hash_of_record, list_raw_comment_ids, load_raw_comment, load_stage,  # noqa: E402
                            load_text_meta)

log = logging.getLogger("build")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def record_consolidation(comment_id, pos_stage, clusters):
    """Keep the merged segment ids next to the analysis they came from.
    The sidecar is rewritten only when its content changes, and removed when
    a submission no longer has any near-duplicates."""
    path = CLASSIFIED_CONSOLIDATION / f"{comment_id}.json"
    if not clusters:
        if path.exists():
            path.unlink()
        return
    record = {
        "comment_id": comment_id,
        "analysis_hash": hash_of_record(pos_stage),
        "rule_version": CONSOLIDATION_RULE_VERSION,
        "clusters": clusters,
    }
    existing = read_json(path, None)
    if existing and hash_of_record(existing) == hash_of_record(record):
        return
    record["created_at"] = now_iso()
    write_json(path, record)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    questions = read_json(DATA_DIR / "questions.json")["questions"]
    editorial_gaps = read_json(EDITORIAL_DIR / "gaps.json")["gaps"]
    editorial_cards = read_json(EDITORIAL_DIR / "signals.json")["cards"]
    identities = read_json(CLASSIFIED_COMMENTERS, {"commenters": {}})["commenters"]

    commenters, commenter_index = [], {}
    submissions, positions = [], []
    exclusions = Counter()
    excluded_ids = []
    consolidation_log = []

    for comment_id in list_raw_comment_ids():
        raw = load_raw_comment(comment_id)
        meta = load_text_meta(comment_id)
        if raw["attributes"].get("withdrawn"):
            exclusions["withdrawn"] += 1
            excluded_ids.append({"id": comment_id, "reason": "withdrawn"})
            continue
        if not meta.get("usable"):
            exclusions["no_usable_text"] += 1
            excluded_ids.append({"id": comment_id, "reason": "no usable text"})
            continue
        identity = identities.get(comment_id)
        pos_stage = load_stage("analysis", comment_id)
        if not identity or not pos_stage:
            exclusions["not_yet_classified"] += 1
            excluded_ids.append({"id": comment_id, "reason": "classification pending"})
            continue

        # Commenter identity: organizations are merged across submissions; individuals are not.
        org = (identity.get("organization") or "").strip()
        key = f"org:{slug(org)}" if org and identity["stakeholder_type"] != "individual" else f"comment:{comment_id}"
        if key not in commenter_index:
            cid = f"c-{slug(org) if org else comment_id.lower()}"
            commenter_index[key] = cid
            commenters.append({
                "id": cid,
                "display_name": identity.get("display_name") or org or "Individual commenter",
                "organization": org,
                "stakeholder_type": identity["stakeholder_type"],
                "source_identity_text": identity.get("source_identity_text", ""),
            })
        cid = commenter_index[key]
        attrs = raw["attributes"]
        sub_id = f"s-{comment_id.lower()}"
        submissions.append({
            "id": sub_id,
            "regulations_gov_comment_id": comment_id,
            "commenter_id": cid,
            "received_date": (attrs.get("receiveDate") or "")[:10],
            "posted_date": (attrs.get("postedDate") or "")[:10],
            "attachment_urls": [a["file_url"] for a in raw.get("attachments", [])],
            "source_url": raw["source_url"],
        })
        publishable = []
        for pos in pos_stage["positions"]:
            if pos["position"] == "unclear" and pos["confidence"] == "low":
                exclusions["unclear_low_confidence_positions"] += 1
                continue
            if not pos.get("public_summary"):
                exclusions["positions_without_summary"] += 1
                continue
            publishable.append(pos)
        kept, clusters = consolidate_positions(publishable)
        record_consolidation(comment_id, pos_stage, clusters)
        if clusters:
            merged_count = sum(len(c["merged_segment_ids"]) for c in clusters)
            exclusions["near_duplicate_positions_consolidated"] += merged_count
            consolidation_log.append({"id": comment_id, "clusters": len(clusters), "positions_merged": merged_count})
        for pos in kept:
            seg = pos["segment_id"]
            summary = pos["public_summary"]
            gap_tags = pos.get("gap_tags", [])
            passage = pos["source_passage"]
            positions.append({
                "id": f"p-{comment_id.lower()}-{seg}",
                "submission_id": sub_id,
                "question_ids": pos["question_ids"],
                "position": pos["position"],
                "primary_issue": pos["primary_issue"],
                "secondary_issue": pos.get("secondary_issue"),
                "stakeholder_concern": pos["stakeholder_concern"],
                "requested_fda_action": pos["requested_fda_action"],
                "public_summary": summary,
                "supporting_text": passage,
                "model_confidence": pos["confidence"],
                "gap_tags": gap_tags,
                "featured": pos["confidence"] == "high" and 40 <= len(passage) <= 420,
            })

    if not positions:
        log.error("no classified positions found; data/ left unchanged. Run the earlier stages first.")
        sys.exit(2)
    with_positions = {p["submission_id"] for p in positions}
    for s in submissions:
        if s["id"] not in with_positions:
            exclusions["submissions_without_published_positions"] += 1
            excluded_ids.append({"id": s["regulations_gov_comment_id"], "reason": "analyzed, but no substantive position survived classification"})

    meta = {
        "generated_at": now_iso(),
        "dataset_kind": "live",
        "processing_version": f"{PROCESSING_VERSION}+analyze-{PROMPT_VERSIONS.get('analyze', '0')}",
        "docket": DOCKET_META,
    }
    files = build_public_dataset(questions, commenters, submissions, positions, editorial_gaps, editorial_cards, meta)
    for name, payload in files.items():
        write_json(DATA_DIR / name, payload)
    manifest = {
        "generated_at": meta["generated_at"],
        "processing_version": PROCESSING_VERSION,
        "prompt_versions": PROMPT_VERSIONS,
        "model": LLM_MODEL,
        "counts": files["site-summary.json"]["metrics"],
        "exclusions": dict(exclusions),
        "excluded_submissions": excluded_ids,
        "consolidation": {
            "rule_version": CONSOLIDATION_RULE_VERSION,
            "submissions_affected": len(consolidation_log),
            "positions_merged": sum(c["positions_merged"] for c in consolidation_log),
            "submissions": consolidation_log,
        },
    }
    write_json(PUBLIC_DIR / "build-manifest.json", manifest)
    log.info("built data/: %s", files["site-summary.json"]["metrics"])
    if exclusions:
        log.info("exclusions: %s", dict(exclusions))
    if consolidation_log:
        log.info("consolidated %d near-duplicate positions across %d submissions",
                 manifest["consolidation"]["positions_merged"], len(consolidation_log))


if __name__ == "__main__":
    main()
