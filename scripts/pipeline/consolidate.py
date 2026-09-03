"""Build-time consolidation of near-duplicate positions within one submission.

Submissions often state the same point twice (an executive summary and a
per-question response, a traceability table and its narrative, or a passage
that straddles a chunk boundary). Segmentation then yields two or more
records for one commenter on one question that say the same thing.

This module folds such records into one, deterministically and without any
model call. Two positions from the same submission are near-duplicates when
all of the following hold:

- they share at least one FDA question id,
- they carry the same position label (a stance is never merged away), and
- either the shorter source passage is largely contained in the longer one
  (PASSAGE_CONTAINMENT) or their public summaries are close
  (SUMMARY_SIMILARITY).

Clusters are transitive within a submission. The most complete record is
kept (highest confidence, then longest passage, most gap tags, longest
summary, earliest segment id) and its question ids and gap tags are extended
with those of the merged records. The merged segment ids are recorded in the
classified layer (classified/consolidation/<id>.json) for provenance.
"""
import difflib
import re

RULE_VERSION = "1.0.0"
PASSAGE_CONTAINMENT = 0.6
SUMMARY_SIMILARITY = 0.6
MIN_MATCH_BLOCK = 20
MAX_GAP_TAGS = 3
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _norm(text):
    text = re.sub(r"\s+", " ", (text or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def passage_containment(a, b):
    """Share of the shorter normalized passage covered by matching runs of at
    least MIN_MATCH_BLOCK characters in the longer one."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    matcher = difflib.SequenceMatcher(None, short, long_, autojunk=False)
    covered = sum(m.size for m in matcher.get_matching_blocks() if m.size >= MIN_MATCH_BLOCK)
    return round(min(1.0, covered / len(short)), 3)


def summary_similarity(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


def _qnum(qid):
    return int(re.sub(r"\D", "", qid) or 0)


def _completeness(pos):
    return (
        _CONFIDENCE_RANK.get(pos.get("confidence"), 0),
        len(pos.get("source_passage") or ""),
        len(pos.get("gap_tags") or []),
        len(pos.get("public_summary") or ""),
    )


def near_duplicate(a, b):
    """Return the match evidence when a and b are near-duplicates, else None."""
    shared = sorted(set(a.get("question_ids", [])) & set(b.get("question_ids", [])), key=_qnum)
    if not shared or a.get("position") != b.get("position"):
        return None
    containment = passage_containment(a.get("source_passage"), b.get("source_passage"))
    similarity = summary_similarity(a.get("public_summary"), b.get("public_summary"))
    if containment >= PASSAGE_CONTAINMENT or similarity >= SUMMARY_SIMILARITY:
        return {
            "segment_ids": sorted([a["segment_id"], b["segment_id"]]),
            "shared_question_ids": shared,
            "passage_containment": containment,
            "summary_similarity": similarity,
        }
    return None


def _merge(kept, merged):
    out = dict(kept)
    qids = list(kept.get("question_ids", []))
    tags = list(kept.get("gap_tags", []))
    explanations = dict(kept.get("gap_explanations") or {})
    for pos in merged:
        for q in pos.get("question_ids", []):
            if q not in qids:
                qids.append(q)
        for t in pos.get("gap_tags", []):
            if t not in tags and len(tags) < MAX_GAP_TAGS:
                tags.append(t)
                explanation = (pos.get("gap_explanations") or {}).get(t)
                if explanation:
                    explanations[t] = explanation
    out["question_ids"] = sorted(qids, key=_qnum)
    out["gap_tags"] = tags
    out["gap_explanations"] = {t: explanations.get(t, "") for t in tags}
    return out


def consolidate_positions(positions):
    """Fold near-duplicate positions of one submission.

    Returns (kept_positions, clusters). Order of the input is preserved for
    kept records. Each cluster lists the kept segment id, the merged segment
    ids and the pairwise evidence that linked them.
    """
    positions = list(positions)
    n = len(positions)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    matches = []
    for i in range(n):
        for j in range(i + 1, n):
            evidence = near_duplicate(positions[i], positions[j])
            if evidence:
                matches.append((i, j, evidence))
                parent[find(i)] = find(j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    kept_by_index, clusters = {}, []
    for members in groups.values():
        if len(members) == 1:
            kept_by_index[members[0]] = positions[members[0]]
            continue
        ranked = sorted(members, key=lambda i: (tuple(-x for x in _completeness(positions[i])), positions[i]["segment_id"]))
        keep, rest = ranked[0], ranked[1:]
        kept_by_index[keep] = _merge(positions[keep], [positions[i] for i in rest])
        member_set = set(members)
        clusters.append({
            "kept_segment_id": positions[keep]["segment_id"],
            "merged_segment_ids": sorted(positions[i]["segment_id"] for i in rest),
            "question_ids": kept_by_index[keep]["question_ids"],
            "position": positions[keep]["position"],
            "matches": sorted((ev for i, j, ev in matches if i in member_set and j in member_set),
                              key=lambda ev: ev["segment_ids"]),
        })
    kept = [kept_by_index[i] for i in range(n) if i in kept_by_index]
    clusters.sort(key=lambda c: c["kept_segment_id"])
    return kept, clusters
