#!/usr/bin/env python3
"""Print the question synthesis for review, exactly as the page renders it,
with the response-type distribution, evidence, counts and stage metrics.

Usage:
    python3 scripts/report_synthesis.py --questions q1,q13 [--markdown]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import DATA_DIR, RUN_METRICS_PATH  # noqa: E402
from pipeline.io_utils import read_json  # noqa: E402
from pipeline.store import load_stage  # noqa: E402
from pipeline.taxonomies import DISAGREEMENT_TOPICS, RESPONSE_TYPES, STAKEHOLDER_TYPES  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    wanted = [q.strip() for q in args.questions.split(",") if q.strip()]
    questions = {q["id"]: q for q in read_json(DATA_DIR / "questions.json")["questions"]}
    analyses = {a["question_id"]: a for a in read_json(DATA_DIR / "analyses.json", {"analyses": []})["analyses"]}
    positions = {p["id"]: p for p in read_json(DATA_DIR / "positions.json", {"positions": []})["positions"]}
    commenters = {c["id"]: c for c in read_json(DATA_DIR / "commenters.json", {"commenters": []})["commenters"]}
    h = (lambda t: f"### {t}") if args.markdown else (lambda t: f"\n== {t} ==")
    for qid in wanted or [q for q in analyses if analyses[q].get("status") != "pending"]:
        q = questions[qid]
        a = analyses.get(qid) or {"status": "pending"}
        print(h(f"Q{q['question_number']}: {q['short_title']}"))
        print(f"Status: {a['status']}")
        if a["status"] == "pending":
            print()
            continue
        print()
        print("What commenters are saying")
        print(a["saying"])
        print()
        print("Where the real disagreement is")
        print(a["disagreement"]["text"])
        topics = ", ".join(DISAGREEMENT_TOPICS.get(t, t) for t in a["disagreement"]["about"])
        print(f"Debate is about: {topics or 'not specified'} | disagreement detected: {a['disagreement']['exists']}")
        for side in a["disagreement"].get("sides", []):
            print(f"  side: {side['summary']} [{', '.join(side['position_ids'])}]")
        div = a["stakeholder_divide"]
        print(f"Stakeholder divide: {div['exists']}" + (f" ({', '.join(div['groups'])}) {div['text']}" if div["exists"] else "") + (f" | note: {div['note']}" if div.get("note") else ""))
        print()
        print("Evidence")
        for pid in a["evidence_position_ids"]:
            p = positions.get(pid)
            if not p:
                print(f"  {pid}: (not in public positions)")
                continue
            c = commenters.get(p["commenter_id"], {})
            print(f"  {pid} | {c.get('display_name')} ({STAKEHOLDER_TYPES.get(c.get('stakeholder_type'), {}).get('label')}) | {RESPONSE_TYPES.get(p.get('response_type'), 'unknown')} | {p['public_summary']}")
        print()
        dist = a["response_type_distribution"]
        print(f"Distinct commenters: {a['distinct_commenters']} | submissions: {a['distinct_submissions']} | positions: {a['positions']}")
        print("Response types by distinct commenters: " + ", ".join(f"{RESPONSE_TYPES.get(k, k)} {v}" for k, v in dist["by_distinct_commenters"].items()))
        print("Response types by positions: " + ", ".join(f"{RESPONSE_TYPES.get(k, k)} {v}" for k, v in dist["by_positions"].items()))
        print(f"Dominant response type: {RESPONSE_TYPES.get(a['dominant_response_type'], a['dominant_response_type'])}")
        rec = load_stage("synthesis", qid) or {}
        print(f"Quality flags: {rec.get('quality_flags') or 'none'} | guard downgrades: {rec.get('downgrades') or 'none'}")
        print()
    metrics = read_json(RUN_METRICS_PATH, {})
    stages = metrics.get("stages", {})
    print(h("Stage metrics"))
    for stage in ("response_types", "synthesize"):
        m = stages.get(stage)
        if not m:
            print(f"{stage}: no metrics recorded in this run")
            continue
        print(f"{stage}: calls {m.get('llm_calls')}, retries {m.get('retries')}, input tokens {m.get('input_tokens')}, output tokens {m.get('output_tokens')}, "
              f"cache read {m.get('cache_read_tokens')}, cache write {m.get('cache_write_tokens')}, elapsed {m.get('elapsed_seconds')}s, est. cost ${m.get('estimated_cost_usd')}"
              + (f", extra {json.dumps({k: v for k, v in m.items() if k not in ('llm_calls', 'retries', 'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'elapsed_seconds', 'estimated_cost_usd', 'model', 'finished_at')})}" ))


if __name__ == "__main__":
    main()
