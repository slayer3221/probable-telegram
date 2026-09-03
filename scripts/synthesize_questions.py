#!/usr/bin/env python3
"""Stage 5: one structured-output call per FDA question that writes a short,
descriptive synthesis of the positions on it (classified/synthesis).

Inputs are the assembled public positions for the question (commenter,
stakeholder type, response type, stance, issue, summary). The record is
keyed by a hash of those inputs, so a question is regenerated only when its
positions change, this prompt's version changes, or the model changes.

Deterministic guards run after the call: evidence ids must exist and span
distinct commenters, a disagreement needs two distinct commenters in
conflict, and a stakeholder divide needs the stronger threshold in
taxonomies.py. The stage describes; it never adds implications.

Usage:
    python3 scripts/synthesize_questions.py [--questions q1,q13] [--limit N]
"""
import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.aggregate import public_positions  # noqa: E402
from pipeline.assemble import assemble_dataset, positions_by_question  # noqa: E402
from pipeline.config import PROMPT_CONFIG, ensure_dirs  # noqa: E402
from pipeline.io_utils import content_hash  # noqa: E402
from pipeline.llm import LLM, SYNTHESIS_SCHEMA, load_prompt, render  # noqa: E402
from pipeline.store import load_stage, save_stage, stage_envelope, stage_is_fresh  # noqa: E402
from pipeline.taxonomies import (DISAGREEMENT_TOPICS, MIN_COMMENTERS_FOR_CONCLUSION, MIN_COMMENTERS_FOR_TENSION,  # noqa: E402
                                 MIN_COMMENTERS_PER_SIDE_FOR_DIVIDE, RESPONSE_TYPES, STAKEHOLDER_TYPES)

log = logging.getLogger("synthesize")
LIMITS = PROMPT_CONFIG.get("synthesis_max_words", {"saying": 60, "disagreement": 60})
MAX_EVIDENCE = 5
MIN_EVIDENCE = 3
BANNED = ("this is important", "broadly agree", "broad agreement", "industry consensus", "stakeholders agree")


def word_count(text):
    return len(re.findall(r"\S+", text or ""))


def cut(text, max_words):
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out = []
    for s in sentences:
        if word_count(" ".join(out + [s])) > max_words:
            break
        out.append(s)
    return " ".join(out) if out else " ".join((text or "").split()[:max_words])


def comparable_groups(rows):
    counts = defaultdict(set)
    for r in rows:
        counts[r["stakeholder_type"]].add(r["commenter_id"])
    return sorted(g for g, ids in counts.items() if len(ids) >= MIN_COMMENTERS_FOR_TENSION)


def synthesis_input(qid, question, rows):
    """The exact inputs the model sees, and their hash."""
    compact = [{k: r[k] for k in ("position_id", "commenter", "stakeholder_type", "response_type", "stance", "primary_issue", "summary")} for r in rows]
    payload = {
        "question_id": qid,
        "question_text": question.get("question_text", ""),
        "positions": compact,
        "distinct_commenters": len({r["commenter_id"] for r in rows}),
        "distinct_submissions": len({r["submission_id"] for r in rows}),
        "comparable_groups": comparable_groups(rows),
    }
    return payload, content_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def positions_text(rows):
    lines = []
    for r in rows:
        lines.append(f"{r['position_id']} | {r['commenter']} ({STAKEHOLDER_TYPES.get(r['stakeholder_type'], {}).get('label', r['stakeholder_type'])}; group id {r['stakeholder_type']}) | response_type={r['response_type'] or 'unknown'} | stance={r['stance']} | issue={r['primary_issue']} | {r['summary']}")
    return "\n".join(lines)


def response_type_distribution(rows):
    """By distinct commenters (a commenter counts once per type it uses) and by positions."""
    by_commenter = defaultdict(set)
    by_position = Counter()
    for r in rows:
        t = r.get("response_type") or "unknown"
        by_commenter[t].add(r["commenter_id"])
        by_position[t] += 1
    order = list(RESPONSE_TYPES) + ["unknown"]
    return {
        "by_distinct_commenters": {t: len(by_commenter[t]) for t in order if by_commenter.get(t)},
        "by_positions": {t: by_position[t] for t in order if by_position.get(t)},
    }


def finalize(qid, raw, rows, shorten=None):
    """Apply the deterministic guards to a raw model output. Pure apart from
    the optional shorten(text, max_words) callback for over-long text."""
    by_id = {r["position_id"]: r for r in rows}
    commenter_of = lambda pid: by_id[pid]["commenter_id"]  # noqa: E731
    n_commenters = len({r["commenter_id"] for r in rows})
    flags, downgrades = [], []

    def limit(text, key):
        text = (text or "").strip().strip('"')
        if word_count(text) > LIMITS[key]:
            if shorten:
                text = shorten(text, LIMITS[key]).strip().strip('"')
            if word_count(text) > LIMITS[key]:
                text = cut(text, LIMITS[key])
                flags.append(f"{key}_cut_at_sentence")
        return text

    saying = limit(raw.get("saying"), "saying")
    for phrase in BANNED:
        if phrase in saying.lower():
            flags.append(f"banned_phrase:{phrase}")
    if "consensus" in saying.lower() and n_commenters < MIN_COMMENTERS_FOR_CONCLUSION:
        flags.append("consensus_below_threshold")

    dominant = raw.get("dominant_response_type")
    dist = response_type_distribution(rows)
    if dominant not in RESPONSE_TYPES:
        dominant = max(dist["by_distinct_commenters"], key=dist["by_distinct_commenters"].get) if dist["by_distinct_commenters"] else "no_clear_answer"
        downgrades.append("dominant_response_type_recomputed")

    # Disagreement: two distinct commenters in material conflict.
    dis = raw.get("disagreement") or {}
    about = [t for t in dis.get("about") or [] if t in DISAGREEMENT_TOPICS][:3]
    sides = []
    for side in dis.get("sides") or []:
        ids = [i for i in side.get("position_ids") or [] if i in by_id]
        if ids:
            sides.append({"summary": (side.get("summary") or "").strip(), "position_ids": ids,
                          "commenter_ids": sorted({commenter_of(i) for i in ids})})
    exists = bool(dis.get("exists"))
    if exists:
        side_sets = [set(s["commenter_ids"]) for s in sides]
        supported = len(side_sets) >= 2 and all(side_sets) and len(set.union(*side_sets)) >= 2 \
            and not (side_sets[0] <= side_sets[1] or side_sets[1] <= side_sets[0])
        if not supported:
            exists = False
            sides = []
            downgrades.append("disagreement_unsupported")
    text = limit(dis.get("text"), "disagreement")
    if not exists and "disagreement_unsupported" in downgrades:
        topics = ", ".join(DISAGREEMENT_TOPICS[t].lower() for t in about) or "how to apply the approach"
        text = f"No material disagreement among distinct commenters is on the record yet. The debate is about {topics}."
    if not exists:
        sides = []

    # Stakeholder divide: stronger evidence than a disagreement.
    div = raw.get("stakeholder_divide") or {}
    groups = [g for g in div.get("groups") or [] if g in STAKEHOLDER_TYPES]
    comparable = comparable_groups(rows)
    claimed = bool(div.get("claimed"))
    divide_ok = False
    if claimed and exists and len(groups) >= 2 and all(g in comparable for g in groups):
        per_side = [len(s["commenter_ids"]) for s in sides]
        divide_ok = all(n >= MIN_COMMENTERS_PER_SIDE_FOR_DIVIDE for n in per_side)
    note = None
    if claimed and not divide_ok:
        note = "The current docket does not yet support a reliable stakeholder comparison on this question."
        downgrades.append("stakeholder_divide_unsupported")
    divide = {"exists": divide_ok, "groups": groups if divide_ok else [],
              "text": (div.get("text") or "").strip() if divide_ok else "", "note": note}

    # Evidence: valid ids, distinct commenters, both sides when a disagreement exists.
    evidence = []
    for pid in raw.get("evidence_position_ids") or []:
        if pid in by_id and pid not in evidence:
            evidence.append(pid)
    if exists:
        for side in sides:
            if not any(pid in evidence for pid in side["position_ids"]):
                evidence.append(side["position_ids"][0])
    evidence = evidence[:MAX_EVIDENCE]
    need_commenters = min(2, n_commenters)
    ranked = sorted(rows, key=lambda r: (r["response_type"] == "no_clear_answer", r["position_id"]))
    for r in ranked:
        if len(evidence) >= MIN_EVIDENCE and len({commenter_of(p) for p in evidence}) >= need_commenters:
            break
        if r["position_id"] not in evidence and (len(evidence) < MIN_EVIDENCE or commenter_of(r["position_id"]) not in {commenter_of(p) for p in evidence}):
            evidence.append(r["position_id"])
            if "evidence_filled" not in downgrades:
                downgrades.append("evidence_filled")
    evidence = evidence[:MAX_EVIDENCE]

    return {
        "question_id": qid,
        "saying": saying,
        "dominant_response_type": dominant,
        "response_type_distribution": dist,
        "disagreement": {"exists": exists, "about": about, "text": text, "sides": sides},
        "stakeholder_divide": divide,
        "evidence_position_ids": evidence,
        "distinct_commenters": n_commenters,
        "distinct_submissions": len({r["submission_id"] for r in rows}),
        "positions": len(rows),
        "comparable_groups": comparable,
        "quality_flags": flags,
        "downgrades": downgrades,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="", help="comma-separated question ids (default: all with positions)")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()
    wanted = [q.strip() for q in args.questions.split(",") if q.strip()]

    data = assemble_dataset()
    if data["response_types_missing"]:
        log.warning("%d submissions have no fresh response types; run classify_response_types.py first", len(data["response_types_missing"]))
    submissions_by_id = {s["id"]: s for s in data["submissions"]}
    commenters_by_id = {c["id"]: c for c in data["commenters"]}
    pub = public_positions(data["positions"], submissions_by_id)
    # public_positions drops response_type unless aggregate publishes it; carry it over by id.
    rtype_by_id = {p["id"]: p.get("response_type") for p in data["positions"]}
    for p in pub:
        p["response_type"] = rtype_by_id.get(p["id"])
    grouped = positions_by_question(pub, commenters_by_id)
    questions_by_id = {q["id"]: q for q in data["questions"]}

    llm = LLM(stage="synthesize")
    template = load_prompt("synthesize")
    template_shorten = load_prompt("shorten_synthesis")

    pending, fresh, empty = [], 0, 0
    for q in data["questions"]:
        qid = q["id"]
        if wanted and qid not in wanted:
            continue
        rows = grouped.get(qid, [])
        if not rows:
            empty += 1
            continue
        if any(r["response_type"] is None for r in rows):
            log.warning("%s: some positions lack a response type; synthesis will read them as unknown", qid)
        payload, input_hash = synthesis_input(qid, q, rows)
        if stage_is_fresh(load_stage("synthesis", qid), input_hash, "synthesis"):
            fresh += 1
            continue
        pending.append((qid, input_hash, payload, rows))
        if args.limit and len(pending) >= args.limit:
            break

    def shorten(text, max_words):
        llm.metrics.add("synthesis_rewrites")
        return llm.text(render(template_shorten, MAX_WORDS=max_words, WORDS=word_count(text), TEXT=text), max_tokens=512, effort="low")

    def run(task):
        qid, input_hash, payload, rows = task
        q = questions_by_id[qid]
        prompt = render(template, QUESTION_CODE=f"Q{q['question_number']}", QUESTION_TEXT=payload["question_text"],
                        DISTINCT_COMMENTERS=payload["distinct_commenters"], DISTINCT_SUBMISSIONS=payload["distinct_submissions"],
                        POSITION_COUNT=len(rows), MIN_GROUP=MIN_COMMENTERS_FOR_TENSION,
                        COMPARABLE_GROUPS=", ".join(payload["comparable_groups"]) or "none",
                        MAX_SAYING_WORDS=LIMITS["saying"], MAX_DISAGREEMENT_WORDS=LIMITS["disagreement"],
                        POSITIONS=positions_text(rows))
        raw = llm.json(prompt, SYNTHESIS_SCHEMA, max_tokens=4096)
        return qid, input_hash, raw, finalize(qid, raw, rows, shorten=shorten)

    for qid, input_hash, raw, record in llm.map(run, pending):
        record["raw_model_output"] = raw
        save_stage("synthesis", qid, stage_envelope(qid, input_hash, record, "synthesis"))
        log.info("%s: synthesized (%d commenters, disagreement=%s, downgrades=%s)", qid, record["distinct_commenters"],
                 record["disagreement"]["exists"], record["downgrades"] or "none")

    metrics = llm.finish(questions_processed=len(pending), questions_reused=fresh, questions_without_positions=empty)
    log.info("done: %d synthesized, %d already fresh, %d without positions; %d model calls in %.0fs (est. $%s)",
             len(pending), fresh, empty, metrics["llm_calls"], metrics["elapsed_seconds"], metrics["estimated_cost_usd"])


if __name__ == "__main__":
    main()
