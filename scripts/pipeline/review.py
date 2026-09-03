"""Question-level change detection.

Each build snapshots what materially describes a question (who commented,
which groups, which issue and response-type combinations, the disagreement
state, the synthesis text) and compares it with the previous snapshot. Only
material changes flag a question for editorial review; another commenter
repeating an existing point, a wording change with the same substance, or a
metadata change does not.
"""
import difflib
from collections import Counter, defaultdict

from .taxonomies import MIN_COMMENTERS_FOR_CONCLUSION

STATE_VERSION = "1.0.0"
SYNTHESIS_CHANGE_RATIO = 0.6  # below this, the synthesis text changed materially


def question_snapshot(qid, rows, synthesis, has_vahana_read):
    """rows: positions on the question with commenter fields (assemble.positions_by_question)."""
    commenters = sorted({r["commenter_id"] for r in rows})
    groups = sorted({r["stakeholder_type"] for r in rows})
    issue_commenters = defaultdict(set)
    combos = set()
    for r in rows:
        issue_commenters[r["primary_issue"]].add(r["commenter_id"])
        combos.add(f"{r['primary_issue']}|{r.get('response_type') or 'unknown'}")
    syn = synthesis or {}
    dis = syn.get("disagreement") or {}
    return {
        "distinct_commenters": len(commenters),
        "commenter_ids": commenters,
        "stakeholder_groups": groups,
        "issue_commenters": {k: len(v) for k, v in sorted(issue_commenters.items())},
        "combos": sorted(combos),
        "dominant_response_type": syn.get("dominant_response_type"),
        "disagreement_exists": bool(dis.get("exists")),
        "disagreement_about": list(dis.get("about") or []),
        "stakeholder_divide_exists": bool((syn.get("stakeholder_divide") or {}).get("exists")),
        "saying": syn.get("saying") or "",
        "synthesis_status": syn.get("status") or ("generated" if syn else "pending"),
        "has_vahana_read": bool(has_vahana_read),
    }


def compare_snapshots(prior, new):
    """Return the list of material change reasons between two snapshots."""
    reasons = []
    if prior is None:
        return reasons
    new_groups = sorted(set(new["stakeholder_groups"]) - set(prior["stakeholder_groups"]))
    if new_groups:
        reasons.append({"reason": "new_stakeholder_group", "detail": f"new group(s): {', '.join(new_groups)}"})
    # Before the response-type stage has run, combos carry "unknown"; the first
    # build with real types compares issues only, so it does not flag every question.
    prior_typed = any(not c.endswith("|unknown") for c in prior["combos"])
    if prior_typed:
        new_combos = sorted(set(new["combos"]) - set(prior["combos"]))
    else:
        prior_issues = {c.split("|")[0] for c in prior["combos"]}
        new_combos = sorted(c for c in new["combos"] if c.split("|")[0] not in prior_issues)
    if new_combos:
        reasons.append({"reason": "new_substantive_position",
                        "detail": "new issue and response-type combination(s): " + ", ".join(c.replace("|", " / ") for c in new_combos)})
    # Synthesis-derived comparisons need a prior synthesis. The first build
    # after a question is synthesized establishes its baseline instead of
    # reporting that a disagreement "emerged" from nothing.
    if prior["synthesis_status"] == "pending" or not prior["saying"] or new["synthesis_status"] == "pending":
        return reasons
    if prior["dominant_response_type"] and new["dominant_response_type"] \
            and prior["dominant_response_type"] != new["dominant_response_type"]:
        reasons.append({"reason": "dominant_response_type_changed",
                        "detail": f"{prior['dominant_response_type']} -> {new['dominant_response_type']}"})
    if prior["disagreement_exists"] != new["disagreement_exists"]:
        reasons.append({"reason": "disagreement_emerged" if new["disagreement_exists"] else "disagreement_resolved",
                        "detail": "about: " + ", ".join(new["disagreement_about"] or prior["disagreement_about"] or ["unspecified"])})
    if prior["stakeholder_divide_exists"] != new["stakeholder_divide_exists"]:
        reasons.append({"reason": "stakeholder_divide_changed",
                        "detail": "a stakeholder divide is now " + ("reported" if new["stakeholder_divide_exists"] else "no longer supported")})
    crossed = [issue for issue, n in new["issue_commenters"].items()
               if n >= MIN_COMMENTERS_FOR_CONCLUSION and prior["issue_commenters"].get(issue, 0) < MIN_COMMENTERS_FOR_CONCLUSION]
    if crossed:
        reasons.append({"reason": "issue_crossed_threshold",
                        "detail": f"{', '.join(crossed)} now raised by at least {MIN_COMMENTERS_FOR_CONCLUSION} distinct commenters"})
    if prior["saying"] and new["saying"] and prior["saying"] != new["saying"]:
        ratio = difflib.SequenceMatcher(None, prior["saying"], new["saying"], autojunk=False).ratio()
        if ratio < SYNTHESIS_CHANGE_RATIO:
            reasons.append({"reason": "synthesis_changed", "detail": f"synthesis text similarity {ratio:.2f}"})
    if new["synthesis_status"] == "stale" and prior["synthesis_status"] != "stale":
        reasons.append({"reason": "synthesis_stale", "detail": "positions changed since the synthesis was generated"})
    return reasons


def build_review_queue(prior_state, new_state, generated_at):
    """prior_state/new_state: {qid: snapshot}. Returns the queue payload."""
    flagged = []
    for qid, new in new_state.items():
        prior = (prior_state or {}).get(qid)
        reasons = compare_snapshots(prior, new)
        if not reasons:
            continue
        flagged.append({
            "question_id": qid,
            "reasons": reasons,
            "what_changed": "; ".join(r["detail"] for r in reasons),
            "prior_distinct_commenters": prior["distinct_commenters"] if prior else None,
            "new_distinct_commenters": new["distinct_commenters"],
            "new_stakeholder_groups": sorted(set(new["stakeholder_groups"]) - set(prior["stakeholder_groups"])) if prior else [],
            "vahana_read_may_need_review": bool(new["has_vahana_read"]),
        })
    flagged.sort(key=lambda f: int(f["question_id"][1:]))
    return {
        "generated_at": generated_at,
        "state_version": STATE_VERSION,
        "baseline": prior_state is None or not prior_state,
        "note": "Private editorial review queue. Not published. A question is listed only when something material changed since the previous build.",
        "flagged": flagged,
    }
