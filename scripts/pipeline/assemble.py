"""Assemble the analyzed docket from raw/ and classified/ into the record
shapes the build and the question synthesis share.

This is the single place that decides which submissions and positions are
publishable: withdrawn or unusable submissions are excluded, unclear
low-confidence positions are dropped, near-duplicate positions within a
submission are folded, and each position carries the response type from the
sidecar stage when that record is fresh against the analysis it describes.
"""
import logging
import re
from collections import Counter

from .config import CLASSIFIED_COMMENTERS, CLASSIFIED_CONSOLIDATION, DATA_DIR, EDITORIAL_DIR
from .consolidate import RULE_VERSION as CONSOLIDATION_RULE_VERSION, consolidate_positions
from .io_utils import now_iso, read_json, write_json
from .store import hash_of_record, list_raw_comment_ids, load_raw_comment, load_stage, load_text_meta, stage_is_fresh

log = logging.getLogger("assemble")


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


def response_types_for(comment_id, pos_stage):
    """Response types for a submission, only when the sidecar is fresh
    against the analysis record it was derived from."""
    record = load_stage("response_types", comment_id)
    if stage_is_fresh(record, hash_of_record(pos_stage), "response_types"):
        return record.get("response_types", {}), True
    return {}, False


def assemble_dataset(write_provenance=False):
    """Return the assembled docket: questions, commenters, submissions and
    positions in build shape, plus exclusion accounting."""
    questions = read_json(DATA_DIR / "questions.json")["questions"]
    identities = read_json(CLASSIFIED_COMMENTERS, {"commenters": {}})["commenters"]
    commenters, commenter_index = [], {}
    submissions, positions = [], []
    exclusions = Counter()
    excluded_ids, consolidation_log = [], []
    response_types_missing = []

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
        if write_provenance:
            record_consolidation(comment_id, pos_stage, clusters)
        if clusters:
            merged_count = sum(len(c["merged_segment_ids"]) for c in clusters)
            exclusions["near_duplicate_positions_consolidated"] += merged_count
            consolidation_log.append({"id": comment_id, "clusters": len(clusters), "positions_merged": merged_count})
        rtypes, fresh = response_types_for(comment_id, pos_stage)
        if not fresh:
            response_types_missing.append(comment_id)
        for pos in kept:
            seg = pos["segment_id"]
            passage = pos["source_passage"]
            positions.append({
                "id": f"p-{comment_id.lower()}-{seg}",
                "submission_id": sub_id,
                "question_ids": pos["question_ids"],
                "position": pos["position"],
                "response_type": rtypes.get(seg),
                "primary_issue": pos["primary_issue"],
                "secondary_issue": pos.get("secondary_issue"),
                "stakeholder_concern": pos["stakeholder_concern"],
                "requested_fda_action": pos["requested_fda_action"],
                "public_summary": pos["public_summary"],
                "supporting_text": passage,
                "model_confidence": pos["confidence"],
                "gap_tags": pos.get("gap_tags", []),
                "featured": pos["confidence"] == "high" and 40 <= len(passage) <= 420,
            })

    with_positions = {p["submission_id"] for p in positions}
    for s in submissions:
        if s["id"] not in with_positions:
            exclusions["submissions_without_published_positions"] += 1
            excluded_ids.append({"id": s["regulations_gov_comment_id"], "reason": "analyzed, but no substantive position survived classification"})
    return {
        "questions": questions,
        "commenters": commenters,
        "submissions": submissions,
        "positions": positions,
        "exclusions": exclusions,
        "excluded_ids": excluded_ids,
        "consolidation_log": consolidation_log,
        "response_types_missing": response_types_missing,
        "editorial_gaps": read_json(EDITORIAL_DIR / "gaps.json")["gaps"],
        "editorial_cards": read_json(EDITORIAL_DIR / "signals.json")["cards"],
        "vahana_read": read_json(EDITORIAL_DIR / "vahana-read.json", {"questions": {}})["questions"],
    }


def positions_by_question(public_positions, commenters_by_id):
    """Group public positions by question with commenter fields attached,
    in a stable order (commenter, then position id)."""
    grouped = {}
    for p in public_positions:
        c = commenters_by_id.get(p["commenter_id"])
        if not c:
            continue
        for qid in p["question_ids"]:
            grouped.setdefault(qid, []).append({
                "position_id": p["id"],
                "commenter_id": p["commenter_id"],
                "commenter": c["display_name"],
                "stakeholder_type": c["stakeholder_type"],
                "submission_id": p["submission_id"],
                "response_type": p.get("response_type"),
                "stance": p["position"],
                "primary_issue": p["primary_issue"],
                "summary": p["public_summary"],
            })
    for qid in grouped:
        grouped[qid].sort(key=lambda r: (r["commenter"].lower(), r["position_id"]))
    return grouped
