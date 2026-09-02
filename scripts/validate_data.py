#!/usr/bin/env python3
"""Validate the public dataset in data/ and the curated editorial files.

Checks referential integrity, controlled vocabularies, counting rules and
the absence of any review/verification workflow fields. Exit code 1 on
failure so it can gate the GitHub Actions refresh.

Usage:
    python3 scripts/validate_data.py [--data-dir data]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.taxonomies import GAPS, ISSUES, POSITIONS, QUESTION_IDS, STAKEHOLDER_TYPES, THEMES  # noqa: E402
from pipeline.io_utils import ROOT, read_json  # noqa: E402

FORBIDDEN_FIELDS = {"verified", "review_status", "reviewer", "reviewer_notes", "human_verified", "ai_classified", "verification_count", "review_queue"}
FORBIDDEN_TEXT = re.compile(r"human[ -]verified|ai[ -]classified|review status|reviewer", re.I)
MAX_SUMMARY_WORDS = 45


def walk_keys(obj, path="", out=None):
    out = out if out is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((f"{path}.{k}", k))
            walk_keys(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_keys(v, f"{path}[{i}]", out)
    return out


def validate(data_dir: Path, editorial_dir: Path):
    errors, warnings = [], []
    q = read_json(data_dir / "questions.json")
    c = read_json(data_dir / "commenters.json")
    s = read_json(data_dir / "submissions.json")
    p = read_json(data_dir / "positions.json")
    g = read_json(data_dir / "gaps.json")
    summary = read_json(data_dir / "site-summary.json")
    editorial = read_json(editorial_dir / "vahana-read.json")
    editorial_gaps = read_json(editorial_dir / "gaps.json")
    for name, payload in (("questions", q), ("commenters", c), ("submissions", s), ("positions", p), ("gaps", g), ("site-summary", summary), ("editorial", editorial)):
        if payload is None:
            errors.append(f"{name}.json missing")
    if errors:
        return errors, warnings

    # Questions
    questions = q["questions"]
    ids = [x["id"] for x in questions]
    if ids != QUESTION_IDS:
        errors.append(f"questions must be q1..q26 in order, got {ids[:3]}...")
    for x in questions:
        if x["theme"] not in THEMES:
            errors.append(f"{x['id']}: unknown theme {x['theme']}")
        if not x.get("short_title") or not x.get("source_url"):
            errors.append(f"{x['id']}: short_title and source_url are required")
        if not (x.get("question_text") or "").strip():
            warnings.append(f"{x['id']}: exact FDA question_text not yet imported")
        n = x["question_number"]
        expected = "risk" if n <= 6 else "premarket" if n <= 17 else "postmarket" if n <= 24 else "foundation_models_agents"
        if x["theme"] != expected:
            warnings.append(f"{x['id']}: theme {x['theme']} differs from section range default {expected}")

    # Commenters / submissions / positions
    commenters = {x["id"]: x for x in c["commenters"]}
    for x in c["commenters"]:
        if x["stakeholder_type"] not in STAKEHOLDER_TYPES:
            errors.append(f"commenter {x['id']}: unknown stakeholder_type {x['stakeholder_type']}")
        if not x.get("display_name"):
            errors.append(f"commenter {x['id']}: display_name required")
    submissions = {x["id"]: x for x in s["submissions"]}
    for x in s["submissions"]:
        if x["commenter_id"] not in commenters:
            errors.append(f"submission {x['id']}: unknown commenter {x['commenter_id']}")
        if not x.get("regulations_gov_comment_id") or not x.get("source_url"):
            errors.append(f"submission {x['id']}: regulations_gov_comment_id and source_url required")
    seen_ids = Counter(x["id"] for x in p["positions"])
    for pid, n in seen_ids.items():
        if n > 1:
            errors.append(f"position id {pid} duplicated")
    for x in p["positions"]:
        pid = x["id"]
        if x["submission_id"] not in submissions:
            errors.append(f"{pid}: unknown submission {x['submission_id']}")
        elif submissions[x["submission_id"]]["commenter_id"] != x.get("commenter_id"):
            errors.append(f"{pid}: commenter_id does not match its submission")
        if not x["question_ids"] or any(qid not in QUESTION_IDS for qid in x["question_ids"]):
            errors.append(f"{pid}: invalid question_ids {x['question_ids']}")
        if x["position"] not in POSITIONS:
            errors.append(f"{pid}: invalid position {x['position']}")
        if x["primary_issue"] not in ISSUES:
            errors.append(f"{pid}: invalid primary_issue {x['primary_issue']}")
        if x.get("secondary_issue") and x["secondary_issue"] not in ISSUES:
            errors.append(f"{pid}: invalid secondary_issue {x['secondary_issue']}")
        if len(x.get("gap_tags", [])) > 3 or any(t not in GAPS for t in x.get("gap_tags", [])):
            errors.append(f"{pid}: gap_tags must be 0-3 known gaps, got {x.get('gap_tags')}")
        if not x.get("supporting_text", "").strip():
            errors.append(f"{pid}: supporting_text (source excerpt) required for traceability")
        words = len(x.get("public_summary", "").split())
        if words == 0:
            errors.append(f"{pid}: public_summary required")
        elif words > MAX_SUMMARY_WORDS:
            errors.append(f"{pid}: public_summary has {words} words (max {MAX_SUMMARY_WORDS})")
        if "model_confidence" in x:
            errors.append(f"{pid}: model_confidence must not be published")

    # Counting rules: distinct commenters never exceed submissions or positions per question.
    for qid, st in summary["question_stats"].items():
        if st["distinct_commenters"] > st["distinct_submissions"] or st["distinct_submissions"] > st["positions"]:
            errors.append(f"{qid}: counts violate commenters <= submissions <= positions")
        if sum(st["position_distribution"].values()) != st["positions"]:
            errors.append(f"{qid}: position_distribution does not sum to positions")
        if sum(st["stakeholder_mix"].values()) != st["distinct_commenters"]:
            errors.append(f"{qid}: stakeholder_mix does not sum to distinct commenters")
    m = summary["metrics"]
    if m["commenters_represented"] != len(commenters) or m["comments_analyzed"] != len(submissions) or m["positions_identified"] != len(p["positions"]):
        errors.append("site-summary metrics do not match dataset sizes")
    if m["questions_tracked"] != 26:
        errors.append("questions_tracked must be 26")
    if len(summary.get("signals", [])) != 4:
        errors.append(f"exactly four signal cards required, got {len(summary.get('signals', []))}")
    for card in summary.get("signals", []):
        if card["target_question_id"] not in QUESTION_IDS:
            errors.append(f"signal '{card['label']}' targets unknown question")

    # Gaps
    gap_ids = [x["id"] for x in g["gaps"]]
    if sorted(gap_ids) != sorted(GAPS):
        errors.append("data/gaps.json must contain exactly the nine cross-cutting gaps")
    if sorted(x["id"] for x in editorial_gaps["gaps"]) != sorted(GAPS):
        errors.append("editorial/gaps.json must define exactly the nine cross-cutting gaps")
    position_ids = {x["id"] for x in p["positions"]}
    for x in g["gaps"]:
        if len(x["examples"]) > 3:
            errors.append(f"gap {x['id']}: at most three representative examples")
        for e in x["examples"]:
            if e["position_id"] not in position_ids or e["commenter_id"] not in commenters:
                errors.append(f"gap {x['id']}: example references unknown position or commenter")
        if any(qid not in QUESTION_IDS for qid in x["question_ids"]):
            errors.append(f"gap {x['id']}: invalid question_ids")

    # Editorial layer is structurally separate and keyed by question
    for qid, entry in editorial["questions"].items():
        if qid not in QUESTION_IDS:
            errors.append(f"editorial entry for unknown question {qid}")
        for key in entry.get("vahana_read", {}):
            if key not in ("alignment", "tension", "commercialization", "deployment", "missing"):
                errors.append(f"editorial {qid}: unknown vahana_read field {key}")
        t = entry.get("tension")
        if t and (not t.get("synthesis") or len(t.get("groups", [])) < 2):
            errors.append(f"editorial {qid}: tension needs a synthesis and at least two groups")

    # No review / verification workflow anywhere in public data
    for payload, name in ((q, "questions"), (c, "commenters"), (s, "submissions"), (p, "positions"), (g, "gaps"), (summary, "site-summary"), (editorial, "editorial")):
        for path, key in walk_keys(payload):
            if key in FORBIDDEN_FIELDS:
                errors.append(f"{name}{path}: review/verification field '{key}' is not allowed")
        text = json.dumps(payload)
        if FORBIDDEN_TEXT.search(text):
            errors.append(f"{name}.json contains review/verification wording")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--editorial-dir", default=str(ROOT / "editorial"))
    args = parser.parse_args()
    errors, warnings = validate(Path(args.data_dir), Path(args.editorial_dir))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
