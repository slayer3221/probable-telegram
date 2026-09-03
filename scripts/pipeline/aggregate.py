"""Aggregation rules that turn commenters, submissions and positions into the
public JSON consumed by the frontend.

Counting rules (conservative by design):
- distinct commenters, distinct submissions and substantive positions are
  always counted separately;
- several positions from one submission never count as several commenters;
- stakeholder-level conclusions require MIN_COMMENTERS_FOR_CONCLUSION
  distinct commenters, otherwise "limited data" language is used;
- curated tension blocks render only when the question meets
  MIN_COMMENTERS_FOR_TENSION and MIN_GROUPS_FOR_TENSION.
"""
from collections import Counter, defaultdict

from .taxonomies import (
    GAPS,
    MIN_COMMENTERS_FOR_CONCLUSION,
    MIN_COMMENTERS_FOR_TENSION,
    MIN_GROUPS_FOR_TENSION,
    POSITIONS,
    STAKEHOLDER_TYPES,
    THEMES,
)

PUBLIC_POSITION_FIELDS = (
    "id", "submission_id", "commenter_id", "question_ids", "position",
    "primary_issue", "secondary_issue", "stakeholder_concern",
    "requested_fda_action", "public_summary", "supporting_text", "gap_tags",
    "featured",
)
PUBLIC_SUBMISSION_FIELDS = (
    "id", "regulations_gov_comment_id", "commenter_id", "received_date",
    "posted_date", "source_url", "has_attachments",
)
PUBLIC_COMMENTER_FIELDS = ("id", "display_name", "organization", "stakeholder_type")


def _index(items):
    return {item["id"]: item for item in items}


def public_positions(positions, submissions_by_id):
    out = []
    for p in positions:
        sub = submissions_by_id.get(p["submission_id"])
        if sub is None:
            continue
        record = {k: p.get(k) for k in PUBLIC_POSITION_FIELDS if k != "commenter_id"}
        record["commenter_id"] = sub["commenter_id"]
        record["secondary_issue"] = record.get("secondary_issue") or None
        record["gap_tags"] = list(record.get("gap_tags") or [])
        record["featured"] = bool(record.get("featured"))
        out.append(record)
    return out


def public_submissions(submissions):
    out = []
    for s in submissions:
        record = {k: s.get(k) for k in PUBLIC_SUBMISSION_FIELDS if k != "has_attachments"}
        record["has_attachments"] = bool(s.get("attachment_urls"))
        out.append(record)
    return out


def public_commenters(commenters):
    return [{k: c.get(k) for k in PUBLIC_COMMENTER_FIELDS} for c in commenters]


def question_stats(question_ids, positions, submissions_by_id, commenters_by_id):
    """Per-question counts over the full (unfiltered) dataset."""
    stats = {}
    for qid in question_ids:
        qpos = [p for p in positions if qid in p["question_ids"]]
        commenter_ids = set()
        submission_ids = set()
        by_type = Counter()
        by_position = Counter()
        for p in qpos:
            sub = submissions_by_id[p["submission_id"]]
            submission_ids.add(sub["id"])
            cid = sub["commenter_id"]
            if cid not in commenter_ids:
                commenter_ids.add(cid)
                by_type[commenters_by_id[cid]["stakeholder_type"]] += 1
            by_position[p["position"]] += 1
        stats[qid] = {
            "distinct_commenters": len(commenter_ids),
            "distinct_submissions": len(submission_ids),
            "positions": len(qpos),
            "stakeholder_mix": {k: by_type[k] for k in STAKEHOLDER_TYPES if by_type[k]},
            "position_distribution": {k: by_position[k] for k in POSITIONS if by_position[k]},
            "tension_eligible": len(commenter_ids) >= MIN_COMMENTERS_FOR_TENSION and len(by_type) >= MIN_GROUPS_FOR_TENSION,
            "conclusion_eligible": len(commenter_ids) >= MIN_COMMENTERS_FOR_CONCLUSION,
        }
    return stats


def gap_stats(editorial_gaps, positions, submissions_by_id, commenters_by_id, max_examples=3):
    out = []
    for g in editorial_gaps:
        gid = g["id"]
        gpos = [p for p in positions if gid in (p.get("gap_tags") or [])]
        commenter_ids = set()
        groups = Counter()
        qcount = Counter()
        for p in gpos:
            cid = submissions_by_id[p["submission_id"]]["commenter_id"]
            if cid not in commenter_ids:
                commenter_ids.add(cid)
                groups[commenters_by_id[cid]["stakeholder_type"]] += 1
            for qid in p["question_ids"]:
                qcount[qid] += 1
        # Representative examples: featured first, then one per commenter, up to max_examples.
        examples = []
        seen = set()
        ordered = sorted(gpos, key=lambda p: (not p.get("featured"), p["id"]))
        for p in ordered:
            cid = submissions_by_id[p["submission_id"]]["commenter_id"]
            if cid in seen or not p.get("supporting_text"):
                continue
            seen.add(cid)
            examples.append({
                "position_id": p["id"],
                "commenter_id": cid,
                "display_name": commenters_by_id[cid]["display_name"],
                "question_id": p["question_ids"][0],
                "excerpt": p["supporting_text"],
            })
            if len(examples) >= max_examples:
                break
        related = [q for q, _ in qcount.most_common(3)]
        out.append({
            "id": gid,
            "title": g["title"],
            "explanation": g["explanation"],
            "question_ids": related,
            "distinct_commenters": len(commenter_ids),
            "positions": len(gpos),
            "stakeholder_types": [k for k, _ in groups.most_common()],
            "examples": examples,
        })
    return out


def _pattern(qstats, totals):
    """Docket-wide check for the 'how, not whether' pattern: on every question
    with enough commenters, positions asking for modification outnumber every
    other category, and outright opposition is rare across the docket.
    `totals` counts distinct positions by stance (a position mapped to several
    questions counts once). Returns (holds, totals)."""
    eligible = [st for st in qstats.values() if st["conclusion_eligible"]]
    totals = Counter(totals or {})
    total = sum(totals.values())
    if not eligible or total == 0:
        return False, totals
    plurality = all(
        st["position_distribution"].get("support_with_modification", 0) > max(
            (v for k, v in st["position_distribution"].items() if k != "support_with_modification"), default=0)
        for st in eligible)
    modify = totals.get("support_with_modification", 0)
    oppose = totals.get("oppose", 0)
    holds = plurality and modify > total / 2 and oppose * 10 < total
    return holds, totals


def _label(stakeholder_type):
    return STAKEHOLDER_TYPES[stakeholder_type]["label"]


SIGNAL_COUNT = 3


def compute_signals(questions, qstats, gap_rows, editorial_cards, position_totals=None):
    """Return exactly SIGNAL_COUNT signal cards, selected from computed
    findings and editorial implication cards. Cards make no strong claim
    below threshold, and none is derived from a per-question stance majority."""
    by_id = {q["id"]: q for q in questions}
    ranked = sorted(qstats.items(), key=lambda kv: (kv[1]["distinct_commenters"], kv[1]["positions"]), reverse=True)
    cards = []

    # Most discussed section (by distinct commenters across its questions)
    theme_commenters = defaultdict(set)
    theme_positions = Counter()
    for qid, st in qstats.items():
        theme = by_id[qid]["theme"]
        theme_positions[theme] += st["positions"]
    if ranked and ranked[0][1]["distinct_commenters"] > 0:
        top_qid, top = ranked[0]
        theme = by_id[top_qid]["theme"]
        theme_qs = [q["id"] for q in questions if q["theme"] == theme]
        cards.append({
            "category": "most_discussed",
            "label": "Most discussed",
            "headline": by_id[top_qid]["short_title"],
            "detail": f"{THEMES[theme]['label']} ({THEMES[theme]['range']}) draws {theme_positions[theme]} positions across {len(theme_qs)} questions; Q{by_id[top_qid]['question_number']} draws the most distinct commenters.",
            "evidence": f"Q{by_id[top_qid]['question_number']} · {top['distinct_commenters']} commenters · {top['positions']} positions",
            "target_question_id": top_qid,
        })

    # Notable pattern (docket-wide, threshold applies). The stance labels are
    # not read as agreement or disagreement with FDA; the card only reports
    # that positions overwhelmingly accept the direction and argue the terms.
    holds, totals = _pattern(qstats, position_totals)
    if holds:
        eligible_n = sum(1 for st in qstats.values() if st["conclusion_eligible"])
        cards.append({
            "category": "pattern",
            "label": "Notable pattern",
            "headline": "The debate is about how, not whether",
            "detail": "Commenters rarely reject FDA's direction. They argue over the terms: where the boundaries sit, how much evidence is enough, and who carries the burden.",
            "evidence": f"{totals.get('support_with_modification', 0)} of {sum(totals.values())} positions ask for modification · {totals.get('oppose', 0)} oppose · plurality on {eligible_n} of {len(qstats)} questions",
            "target_question_id": ranked[0][0] if ranked else "q1",
        })

    # Editorial implication cards. They are hedged editorial interpretation,
    # so they always render; the evidence line states the sample honestly.
    gap_by_id = {g["id"]: g for g in gap_rows}
    for card in editorial_cards:
        qids = [q for q in card.get("question_ids", []) if q in qstats]
        qlabel = ", ".join(f"Q{by_id[q]['question_number']}" for q in qids) or "the docket"
        gap = gap_by_id.get(card.get("gap_id"))
        commenters = gap["distinct_commenters"] if gap else sum(qstats[q]["distinct_commenters"] for q in qids)
        if commenters >= MIN_COMMENTERS_FOR_CONCLUSION:
            evidence = f"Drawn from {qlabel} · {commenters} commenters"
        else:
            evidence = f"Limited data · {commenters} commenter{'s' if commenters != 1 else ''} so far on {qlabel}"
        cards.append({
            "category": card["category"],
            "label": card["label"],
            "headline": card["headline"],
            "detail": card["detail"],
            "evidence": evidence,
            "target_question_id": card.get("target_question_id") or (qids[0] if qids else "q1"),
        })

    # Emerging blind spot (gap with most distinct commenters)
    if len(cards) < SIGNAL_COUNT and gap_rows:
        g = max(gap_rows, key=lambda r: r["distinct_commenters"])
        if g["distinct_commenters"] > 0:
            cards.append({
                "category": "blind_spot",
                "label": "Emerging blind spot",
                "headline": g["title"],
                "detail": g["explanation"],
                "evidence": (f"{g['distinct_commenters']} commenters · " if g["distinct_commenters"] >= MIN_COMMENTERS_FOR_CONCLUSION else "Limited data · ")
                            + ", ".join(f"Q{by_id[q]['question_number']}" for q in g["question_ids"]),
                "target_question_id": g["question_ids"][0] if g["question_ids"] else "q1",
            })

    # Fallbacks so the strip always holds three cards without overstating anything.
    fallbacks = [
        ("most_discussed", "Most discussed", "No positions yet", "The tracker shows the most discussed question once comments have been classified."),
        ("pattern", "Notable pattern", "Not enough comments yet", f"Docket-wide patterns are reported only once questions have at least {MIN_COMMENTERS_FOR_CONCLUSION} distinct commenters."),
        ("blind_spot", "Emerging blind spot", "Not enough comments yet", "Cross-cutting issues are surfaced once commenters raise them across several questions."),
    ]
    present = {c["category"] for c in cards}
    for category, label, headline, detail in fallbacks:
        if len(cards) >= SIGNAL_COUNT:
            break
        if category in present:
            continue
        cards.append({"category": category, "label": label, "headline": headline, "detail": detail,
                      "evidence": "Limited data", "target_question_id": ranked[0][0] if ranked else "q1"})
    order = {"most_discussed": 0, "pattern": 1, "commercialization": 2, "deployment": 3, "blind_spot": 4}
    cards.sort(key=lambda c: order.get(c["category"], 9))
    return cards[:SIGNAL_COUNT]


def build_site_summary(questions, commenters, submissions, positions, qstats, gap_rows, signals, meta):
    usable_submissions = [s for s in submissions if s.get("id")]
    return {
        "generated_at": meta["generated_at"],
        "dataset_kind": meta["dataset_kind"],
        "processing_version": meta.get("processing_version"),
        "docket": meta["docket"],
        "metrics": {
            "comments_analyzed": len(usable_submissions),
            "commenters_represented": len({p["commenter_id"] for p in positions}),
            "positions_identified": len(positions),
            "questions_tracked": len(questions),
            "comment_deadline": meta["docket"]["comment_deadline"],
            "last_updated": meta["generated_at"][:10],
        },
        "thresholds": {
            "min_commenters_for_conclusion": MIN_COMMENTERS_FOR_CONCLUSION,
            "min_commenters_for_tension": MIN_COMMENTERS_FOR_TENSION,
            "min_groups_for_tension": MIN_GROUPS_FOR_TENSION,
        },
        "signals": signals,
        "question_stats": qstats,
        "gap_totals": {g["id"]: g["distinct_commenters"] for g in gap_rows},
    }


def build_public_dataset(questions, commenters, submissions, positions, editorial_gaps, editorial_cards, meta):
    """Return a dict of file basename -> payload for the data/ directory."""
    commenters_by_id = _index(commenters)
    submissions_by_id = _index(submissions)
    # Only positions whose submission and commenter exist are published.
    positions = [p for p in positions if p["submission_id"] in submissions_by_id
                 and submissions_by_id[p["submission_id"]]["commenter_id"] in commenters_by_id]
    # Every analyzed submission is published (comments_analyzed counts them all);
    # commenters_represented counts only commenters with a published position.
    analyzed_commenters = {s["commenter_id"] for s in submissions}
    pub_commenters = public_commenters([c for c in commenters if c["id"] in analyzed_commenters])
    pub_submissions = public_submissions(submissions)
    pub_positions = public_positions(positions, submissions_by_id)
    qids = [q["id"] for q in questions]
    qstats = question_stats(qids, pub_positions, submissions_by_id, commenters_by_id)
    gap_rows = gap_stats(editorial_gaps, pub_positions, submissions_by_id, commenters_by_id)
    signals = compute_signals(questions, qstats, gap_rows, editorial_cards, Counter(p["position"] for p in pub_positions))
    summary = build_site_summary(questions, pub_commenters, pub_submissions, pub_positions, qstats, gap_rows, signals, meta)
    return {
        "commenters.json": {"commenters": pub_commenters},
        "submissions.json": {"submissions": pub_submissions},
        "positions.json": {"positions": pub_positions},
        "gaps.json": {"gaps": gap_rows},
        "site-summary.json": summary,
    }
