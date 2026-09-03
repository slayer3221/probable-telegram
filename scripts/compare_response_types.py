#!/usr/bin/env python3
"""Compare a shadow response-type run with the production records.

Reports overall and per-type agreement, the confusion pairs, and whether the
dominant response type per question would change. Only segments present in
both runs are compared.

Usage:
    python3 scripts/compare_response_types.py --shadow haiku-compact [--questions q1,q13] [--markdown]
"""
import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import CLASSIFIED_DIR, CLASSIFIED_RESPONSE_TYPES, RUN_METRICS_PATH  # noqa: E402
from pipeline.io_utils import read_json  # noqa: E402
from pipeline.store import load_stage  # noqa: E402
from pipeline.taxonomies import RESPONSE_TYPES  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--questions", default="")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    wanted = {q.strip() for q in args.questions.split(",") if q.strip()}
    shadow_dir = CLASSIFIED_DIR / "response_types_shadow" / args.shadow
    h = (lambda t: f"### {t}") if args.markdown else (lambda t: f"\n== {t} ==")

    pairs = []  # (comment_id, segment_id, production, shadow, question_ids)
    per_question = defaultdict(lambda: {"prod": defaultdict(set), "shadow": defaultdict(set)})
    submissions = 0
    for path in sorted(glob.glob(str(shadow_dir / "*.json"))):
        shadow = read_json(path)
        cid = shadow["comment_id"]
        prod = read_json(CLASSIFIED_RESPONSE_TYPES / f"{cid}.json")
        analysis = load_stage("analysis", cid)
        if not prod or not analysis:
            continue
        if prod.get("input_hash") != shadow.get("input_hash"):
            print(f"{cid}: production and shadow were derived from different analysis records; skipped")
            continue
        submissions += 1
        for p in analysis["positions"]:
            seg = p["segment_id"]
            a, b = prod["response_types"].get(seg), shadow["response_types"].get(seg)
            if a is None or b is None:
                continue
            pairs.append((cid, seg, a, b, p["question_ids"]))
            for qid in p["question_ids"]:
                per_question[qid]["prod"][a].add(cid)
                per_question[qid]["shadow"][b].add(cid)

    if not pairs:
        print("nothing to compare: run the shadow variant first")
        return
    agree = sum(1 for _, _, a, b, _ in pairs if a == b)
    print(h(f"Shadow variant '{args.shadow}' vs production ({shadow.get('model')} / {shadow.get('representation')} vs {prod.get('model')} / full)"))
    print(f"Submissions compared: {submissions} | segments compared: {len(pairs)} | agreement: {agree}/{len(pairs)} ({100 * agree / len(pairs):.1f}%)")
    print()
    print("Per production type (production count, agreement):")
    by_type = defaultdict(lambda: [0, 0])
    for _, _, a, b, _ in pairs:
        by_type[a][0] += 1
        by_type[a][1] += int(a == b)
    for t in RESPONSE_TYPES:
        n, ok = by_type[t]
        if n:
            print(f"  {RESPONSE_TYPES[t]:<22} {n:>4}  {100 * ok / n:5.1f}%")
    print()
    confusion = Counter((a, b) for _, _, a, b, _ in pairs if a != b)
    print("Most common disagreements (production -> shadow):")
    for (a, b), n in confusion.most_common(8):
        print(f"  {RESPONSE_TYPES[a]} -> {RESPONSE_TYPES[b]}: {n}")
    print()
    print("Dominant response type by distinct commenters, per question (production -> shadow):")
    changed = 0
    for qid in sorted(per_question, key=lambda q: int(q[1:])):
        if wanted and qid not in wanted:
            continue
        pq = per_question[qid]
        top = lambda d: max(d, key=lambda t: (len(d[t]), t)) if d else None  # noqa: E731
        a, b = top(pq["prod"]), top(pq["shadow"])
        mark = "" if a == b else "  <- changes"
        changed += int(a != b)
        print(f"  {qid:<4} {RESPONSE_TYPES.get(a, a)} ({len(pq['prod'].get(a, []))}) -> {RESPONSE_TYPES.get(b, b)} ({len(pq['shadow'].get(b, []))}){mark}")
    print(f"Questions whose dominant response type would change: {changed}")
    print()
    metrics = read_json(RUN_METRICS_PATH, {}).get("stages", {})
    for stage in ("response_types", f"response_types_shadow:{args.shadow}"):
        m = metrics.get(stage)
        if m:
            print(f"{stage}: model {m.get('model')}, calls {m.get('llm_calls')}, retries {m.get('retries')}, input {m.get('input_tokens')}, output {m.get('output_tokens')}, "
                  f"cache read {m.get('cache_read_tokens')}, est. cost ${m.get('estimated_cost_usd')}, elapsed {m.get('elapsed_seconds')}s")
    print()
    print("Segment-level disagreements (comment, segment, production -> shadow):")
    for cid, seg, a, b, qids in pairs:
        if a != b:
            print(f"  {cid} {seg} [{','.join(qids)}]: {a} -> {b}")


if __name__ == "__main__":
    main()
