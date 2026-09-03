"""Data integrity tests. Run with `python3 -m pytest tests/` or `python3 tests/test_data_integrity.py`.
The public dataset in data/ may be empty (before the first committed refresh) or live."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import aggregate, llm, store, taxonomies  # noqa: E402
from validate_data import validate  # noqa: E402


def test_public_dataset_validates():
    errors, _ = validate(ROOT / "data", ROOT / "editorial")
    assert errors == [], "\n".join(errors)


def test_js_taxonomies_match_python():
    js = (ROOT / "js" / "taxonomies.js").read_text(encoding="utf-8")
    for key, meta in taxonomies.STAKEHOLDER_TYPES.items():
        assert f"id: '{key}'" in js and f"label: '{meta['label']}'" in js, key
    for key, meta in taxonomies.POSITIONS.items():
        assert f"id: '{key}'" in js, key
    for key in taxonomies.ISSUES:
        assert re.search(rf"\b{key}:", js), key
    for key, label in taxonomies.GAPS.items():
        assert f"{key}: '{label}'" in js or f"{key}: \"{label}\"" in js, key
    for key, label in taxonomies.RESPONSE_TYPES.items():
        assert f"{key}: '{label}'" in js, key
    for key, label in taxonomies.DISAGREEMENT_TOPICS.items():
        assert f"{key}: '{label}'" in js, key


def test_counting_rules_do_not_inflate_commenters():
    commenters = [{"id": "c1", "display_name": "A", "organization": "A", "stakeholder_type": "device_manufacturer"}]
    submissions = [{"id": "s1", "commenter_id": "c1", "regulations_gov_comment_id": "X-1", "received_date": "2026-09-01", "posted_date": "2026-09-01", "source_url": "https://example.invalid", "attachment_urls": []}]
    positions = [
        {"id": f"p{i}", "submission_id": "s1", "question_ids": ["q1"], "position": "support", "primary_issue": "intended_use",
         "secondary_issue": None, "stakeholder_concern": "x", "requested_fda_action": "y", "public_summary": "z",
         "supporting_text": "quote", "model_confidence": "high", "gap_tags": [], "featured": False}
        for i in range(3)
    ]
    stats = aggregate.question_stats(["q1"], aggregate.public_positions(positions, {"s1": submissions[0]}), {"s1": submissions[0]}, {"c1": commenters[0]})
    assert stats["q1"]["distinct_commenters"] == 1
    assert stats["q1"]["distinct_submissions"] == 1
    assert stats["q1"]["positions"] == 3
    assert stats["q1"]["conclusion_eligible"] is False


def test_public_positions_drop_confidence():
    submissions = {"s1": {"id": "s1", "commenter_id": "c1"}}
    pub = aggregate.public_positions([{"id": "p1", "submission_id": "s1", "question_ids": ["q2"], "position": "mixed",
                                       "primary_issue": "intended_use", "model_confidence": "low", "public_summary": "s",
                                       "supporting_text": "t", "stakeholder_concern": "c", "requested_fda_action": "a"}], submissions)
    assert "model_confidence" not in pub[0]
    assert pub[0]["commenter_id"] == "c1"


def test_no_verification_workflow_in_codebase():
    pattern = re.compile(r"human[ -]verified|ai[ -]classified|review[ _-]status|reviewer|verified\s*[:=]\s*(true|false)|verification[ _-]count", re.I)
    offenders = []
    for path in ROOT.rglob("*"):
        # data/ holds live commenter text after a refresh; real submissions
        # talk about FDA reviewers, so only code, docs and the curated
        # editorial layer are scanned for workflow wording.
        if path.is_dir() or any(part in ("node_modules", ".git", "raw", "classified", "data", "public", "screenshots", "__pycache__", ".pytest_cache") for part in path.parts):
            continue
        if path.suffix not in (".html", ".css", ".js", ".json", ".py", ".md", ".yml", ".yaml", ".txt"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            # This test and the validator legitimately name the forbidden terms.
            if path.name in ("validate_data.py", "test_data_integrity.py"):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{line}: {m.group(0)}")
    assert offenders == [], "\n".join(offenders)


def test_editorial_layer_is_separate_from_public_data():
    editorial = json.loads((ROOT / "editorial" / "vahana-read.json").read_text(encoding="utf-8"))
    positions = json.loads((ROOT / "data" / "positions.json").read_text(encoding="utf-8"))["positions"]
    for p in positions:
        assert "vahana_read" not in p and "tension" not in p
    for qid, entry in editorial["questions"].items():
        assert set(entry).issubset({"tension", "vahana_read"}), qid


def test_tiny_dataset_yields_three_signals(tmp_path):
    """A first live run may have only a couple of commenters; the signal strip
    must still hold three cards, none derived from a stance majority, and the
    dataset must validate."""
    questions = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
    gaps = json.loads((ROOT / "editorial" / "gaps.json").read_text(encoding="utf-8"))["gaps"]
    cards = json.loads((ROOT / "editorial" / "signals.json").read_text(encoding="utf-8"))["cards"]
    commenters = [
        {"id": "c1", "display_name": "Org A", "organization": "Org A", "stakeholder_type": "device_manufacturer", "source_identity_text": ""},
        {"id": "c2", "display_name": "Org B", "organization": "Org B", "stakeholder_type": "health_system_provider", "source_identity_text": ""},
        {"id": "c3", "display_name": "Org C", "organization": "Org C", "stakeholder_type": "other", "source_identity_text": ""},
    ]
    submissions = [{"id": f"s{i}", "commenter_id": f"c{i}", "regulations_gov_comment_id": f"X-{i}", "received_date": "2026-09-01",
                    "posted_date": "2026-09-01", "source_url": "https://example.invalid", "attachment_urls": []} for i in (1, 2, 3)]
    positions = [
        {"id": "p1", "submission_id": "s1", "question_ids": ["q7"], "position": "support", "primary_issue": "evidence_standards",
         "secondary_issue": None, "stakeholder_concern": "c", "requested_fda_action": "a", "public_summary": "s",
         "supporting_text": "quote one", "model_confidence": "high", "gap_tags": ["evidence_burden_commercial_viability"], "featured": True},
        {"id": "p2", "submission_id": "s2", "question_ids": ["q7", "q21"], "position": "mixed", "primary_issue": "postmarket_monitoring",
         "secondary_issue": None, "stakeholder_concern": "c", "requested_fda_action": "a", "public_summary": "s",
         "supporting_text": "quote two", "model_confidence": "medium", "gap_tags": [], "featured": False},
    ]
    meta = {"generated_at": "2026-09-02T00:00:00Z", "dataset_kind": "live", "processing_version": "t",
            "docket": {"docket_id": "D", "docket_url": "", "document_id": "", "discussion_paper_url": "", "comment_deadline": "2026-10-19", "paper_date": "2026-08-18"}}
    files = aggregate.build_public_dataset(questions, commenters, submissions, positions, gaps, cards, meta)
    summary = files["site-summary.json"]
    assert len(summary["signals"]) == 3, [c["label"] for c in summary["signals"]]
    assert [c["category"] for c in summary["signals"]] == ["most_discussed", "pattern", "blind_spot"]
    assert all("Limited data" in c["evidence"] or "Not enough" in c["headline"] for c in summary["signals"][1:])
    assert summary["metrics"]["comments_analyzed"] == 3
    assert summary["metrics"]["commenters_represented"] == 2
    out = tmp_path / "data"
    out.mkdir()
    (out / "questions.json").write_text(json.dumps({"questions": questions}), encoding="utf-8")
    for name, payload in files.items():
        (out / name).write_text(json.dumps(payload), encoding="utf-8")
    (out / "analyses.json").write_text(json.dumps({"analyses": [{"question_id": q["id"], "status": "pending"} for q in questions]}), encoding="utf-8")
    errors, _ = validate(out, ROOT / "editorial")
    assert errors == [], "\n".join(errors)


def test_pattern_signal_requires_docket_wide_support():
    """The 'how, not whether' card is reported only when modification positions
    hold the plurality on every eligible question and opposition is rare."""
    def stat(dist, commenters=6):
        return {"distinct_commenters": commenters, "distinct_submissions": commenters, "positions": sum(dist.values()),
                "stakeholder_mix": {"other": commenters}, "position_distribution": dist,
                "tension_eligible": True, "conclusion_eligible": commenters >= 5}
    holds, totals = aggregate._pattern({"q1": stat({"support_with_modification": 20, "support": 2, "oppose": 1}),
                                        "q2": stat({"support_with_modification": 9, "oppose": 1})},
                                       {"support_with_modification": 27, "support": 2, "oppose": 2})
    assert holds and totals["support_with_modification"] == 27, "totals are distinct positions, not per-question sums"
    holds, _ = aggregate._pattern({"q1": stat({"support_with_modification": 20, "oppose": 1}),
                                   "q2": stat({"oppose": 6, "support_with_modification": 5})},
                                  {"support_with_modification": 25, "oppose": 7})
    assert not holds, "a question where opposition leads must block the pattern"
    holds, _ = aggregate._pattern({"q1": stat({"support_with_modification": 12, "oppose": 3})},
                                  {"support_with_modification": 12, "oppose": 3})
    assert not holds, "one in five positions opposing is not rare"
    holds, _ = aggregate._pattern({"q1": stat({"support_with_modification": 3}, commenters=2)},
                                  {"support_with_modification": 3})
    assert not holds, "no eligible question means no pattern"


def test_metrics_cost_and_totals():
    m = llm.Metrics("unit")

    class Usage:
        input_tokens = 1_000_000
        output_tokens = 100_000
        cache_read_input_tokens = 2_000_000
        cache_creation_input_tokens = 0

    m.record(Usage(), retries=2)
    m.record(Usage(), retries=0)
    d = m.as_dict("claude-opus-5")
    assert d["llm_calls"] == 2 and d["retries"] == 2
    assert d["input_tokens"] == 2_000_000 and d["cache_read_tokens"] == 4_000_000
    # 2M input at $5 + 0.2M output at $25 + 4M cache reads at $0.50
    assert d["estimated_cost_usd"] == round(2 * 5 + 0.2 * 25 + 4 * 0.5, 4)


def test_bounded_concurrency_preserves_order():
    import threading
    import time as _t
    client = llm.LLM.__new__(llm.LLM)
    client.concurrency = 3
    active, peak, lock = [0], [0], threading.Lock()

    def work(i):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _t.sleep(0.05)
        with lock:
            active[0] -= 1
        return i * 2

    assert client.map(work, list(range(10))) == [i * 2 for i in range(10)]
    assert 1 < peak[0] <= 3


def test_stage_freshness_is_per_stage_prompt_version():
    rec = store.stage_envelope("c", "hash", {"positions": []}, "analysis")
    assert store.stage_is_fresh(rec, "hash", "analysis")
    assert not store.stage_is_fresh(rec, "other", "analysis")
    assert rec["prompt_version"] == store.prompt_version("analyze")
    seg = store.stage_envelope("c", "hash", {"positions": []}, "segments")
    assert seg["prompt_version"] == store.prompt_version("segment")



def _pos(seg, qids, stance, passage, summary, confidence="high", gaps=None):
    return {"segment_id": seg, "question_ids": qids, "position": stance, "primary_issue": "evidence_standards",
            "secondary_issue": None, "stakeholder_concern": "c", "requested_fda_action": "a", "confidence": confidence,
            "gap_tags": gaps or [], "gap_explanations": {g: "why" for g in (gaps or [])},
            "public_summary": summary, "summary_cut": False, "source_passage": passage}


def test_consolidation_folds_restatements_but_keeps_distinct_stances():
    from pipeline import consolidate
    body = ("FDA should require ninety days of advance notice before any material foundation model version change, "
            "because shorter windows leave no time to rerun validation studies and execute change control procedures.")
    full = _pos("seg-001", ["q24"], "support_with_modification", "Executive summary. " + body + " We also ask for version pinning.",
                "Asks FDA to require 90 days' notice of model changes and version pinning.", gaps=["ai_supplier_quality"])
    fragment = _pos("seg-002", ["q24", "q19"], "support_with_modification", body,
                    "Requests a ninety-day notice window before model version changes.", confidence="medium",
                    gaps=["deployment_assurance_scalability"])
    opposite = _pos("seg-003", ["q24"], "oppose", body, "Opposes mandatory notice windows as unworkable.")
    other_question = _pos("seg-004", ["q9"], "support_with_modification", body,
                          "Asks FDA to require 90 days' notice of model changes and version pinning.")
    kept, clusters = consolidate.consolidate_positions([full, fragment, opposite, other_question])
    assert [p["segment_id"] for p in kept] == ["seg-001", "seg-003", "seg-004"]
    assert clusters == [{
        "kept_segment_id": "seg-001", "merged_segment_ids": ["seg-002"], "question_ids": ["q19", "q24"],
        "position": "support_with_modification",
        "matches": [{"segment_ids": ["seg-001", "seg-002"], "shared_question_ids": ["q24"],
                     "passage_containment": clusters[0]["matches"][0]["passage_containment"],
                     "summary_similarity": clusters[0]["matches"][0]["summary_similarity"]}],
    }]
    assert clusters[0]["matches"][0]["passage_containment"] >= consolidate.PASSAGE_CONTAINMENT
    merged = kept[0]
    assert merged["question_ids"] == ["q19", "q24"]
    assert merged["gap_tags"] == ["ai_supplier_quality", "deployment_assurance_scalability"]
    assert merged["gap_explanations"] == {"ai_supplier_quality": "why", "deployment_assurance_scalability": "why"}
    assert merged["public_summary"] == full["public_summary"]
    # Deterministic: the same input yields the same output, whatever the order.
    kept2, clusters2 = consolidate.consolidate_positions([other_question, opposite, fragment, full])
    assert {p["segment_id"] for p in kept2} == {"seg-001", "seg-003", "seg-004"}
    assert clusters2 == clusters


def test_consolidation_keeps_most_complete_record_and_caps_gaps():
    from pipeline import consolidate
    text = "Synthetic data suits rare-event stress testing and privacy-preserving scenario development but not latent relationships."
    weaker = _pos("seg-001", ["q13"], "support_with_modification", text, "Backs synthetic data for rare events only.",
                  confidence="medium", gaps=["evidence_burden_commercial_viability"])
    stronger = _pos("seg-002", ["q13"], "support_with_modification", "Response to Question 13. " + text,
                    "Backs synthetic data for rare-event testing, not for latent relationships.",
                    gaps=["human_ai_system_performance", "operational_harm", "delegated_authority"])
    kept, clusters = consolidate.consolidate_positions([weaker, stronger])
    assert [p["segment_id"] for p in kept] == ["seg-002"]
    assert kept[0]["gap_tags"] == ["human_ai_system_performance", "operational_harm", "delegated_authority"]
    assert clusters[0]["merged_segment_ids"] == ["seg-001"]


def test_consolidation_provenance_matches_analysis_records():
    """Every consolidation sidecar must describe the analysis record it was
    derived from; a stale sidecar would misattribute merged ids."""
    from pipeline import consolidate
    sidecars = sorted((ROOT / "classified" / "consolidation").glob("*.json"))
    for path in sidecars:
        record = json.loads(path.read_text(encoding="utf-8"))
        analysis = store.load_stage("analysis", record["comment_id"])
        assert analysis, f"{path.name}: analysis record missing"
        assert record["analysis_hash"] == store.hash_of_record(analysis), f"{path.name}: stale consolidation record"
        assert record["rule_version"] == consolidate.RULE_VERSION
        segment_ids = {p["segment_id"] for p in analysis["positions"]}
        for cluster in record["clusters"]:
            assert cluster["kept_segment_id"] in segment_ids
            assert set(cluster["merged_segment_ids"]) <= segment_ids
            assert cluster["kept_segment_id"] not in cluster["merged_segment_ids"]


def _row(pid, cid, rtype="recommendation", group="device_manufacturer", issue="evidence_standards"):
    return {"position_id": pid, "commenter_id": cid, "commenter": cid.upper(), "stakeholder_type": group,
            "submission_id": f"s-{cid}", "response_type": rtype, "stance": "support_with_modification",
            "primary_issue": issue, "summary": f"summary of {pid}"}


def test_synthesis_guards_downgrade_unsupported_claims():
    from synthesize_questions import finalize
    rows = [_row("p1", "c1"), _row("p2", "c2", "concern"), _row("p3", "c3", "proposed_criterion", "health_system_provider"),
            _row("p4", "c4", "recommendation", "health_system_provider"), _row("p5", "c1", "concern")]
    # A disagreement whose two "sides" are the same commenter is not a disagreement.
    raw = {"saying": "Most commenters ask for tiers.", "dominant_response_type": "recommendation",
           "disagreement": {"exists": True, "about": ["thresholds"], "text": "Commenters split on thresholds.",
                            "sides": [{"summary": "a", "position_ids": ["p1"]}, {"summary": "b", "position_ids": ["p5"]}]},
           "stakeholder_divide": {"claimed": True, "groups": ["device_manufacturer", "health_system_provider"], "text": "Makers vs systems."},
           "evidence_position_ids": ["p1", "p-bogus"]}
    out = finalize("q9", raw, rows)
    assert out["disagreement"]["exists"] is False and out["disagreement"]["sides"] == []
    assert "disagreement_unsupported" in out["downgrades"]
    assert out["disagreement"]["text"].startswith("No material disagreement")
    assert out["stakeholder_divide"]["exists"] is False and out["stakeholder_divide"]["note"]
    assert "p-bogus" not in out["evidence_position_ids"]
    assert len(out["evidence_position_ids"]) >= 3 and len({r["commenter_id"] for r in rows if r["position_id"] in out["evidence_position_ids"]}) >= 2
    assert out["response_type_distribution"]["by_distinct_commenters"] == {"recommendation": 2, "concern": 2, "proposed_criterion": 1}

    # Two distinct commenters in conflict is a disagreement, but one against several is not a stakeholder divide.
    raw["disagreement"]["sides"] = [{"summary": "a", "position_ids": ["p1", "p2"]}, {"summary": "b", "position_ids": ["p3"]}]
    rows_big = rows + [_row("p6", "c5", group="health_system_provider"), _row("p7", "c6", group="health_system_provider"),
                       _row("p8", "c7"), _row("p9", "c8")]
    out = finalize("q9", raw, rows_big)
    assert out["disagreement"]["exists"] is True
    assert out["stakeholder_divide"]["exists"] is False, "one commenter on a side cannot make a stakeholder divide"
    assert all(pid in out["evidence_position_ids"] for pid in ("p1", "p3")), "evidence must cover both sides"

    # Two or more distinct commenters on each side, from comparable groups, is a divide.
    raw["disagreement"]["sides"] = [{"summary": "a", "position_ids": ["p1", "p2"]}, {"summary": "b", "position_ids": ["p3", "p6"]}]
    out = finalize("q9", raw, rows_big)
    assert out["stakeholder_divide"]["exists"] is True and out["stakeholder_divide"]["groups"] == ["device_manufacturer", "health_system_provider"]

    # Over-long text is cut at a sentence boundary and flagged when no rewrite is available.
    raw["saying"] = " ".join(["Sentence one has words."] * 20)
    out = finalize("q9", raw, rows_big)
    assert len(out["saying"].split()) <= 60 and "saying_cut_at_sentence" in out["quality_flags"]


def test_text_cleanup_repairs_broken_escapes_without_adding_words():
    from pipeline.textclean import clean_text, has_broken_escapes
    assert clean_text("how to operationalize it \\u2014 how intended use") == "how to operationalize it, how intended use"
    assert clean_text("otherwise get\ninformationally\nunaided clinicians\nbut want") == "otherwise get, informationally, unaided clinicians, but want"
    assert clean_text("A sound start \u2014 not complete.") == "A sound start, not complete."
    assert clean_text("keeps: \u2014 the rest") == "keeps: the rest"
    assert has_broken_escapes("details \x08enchmark") and not has_broken_escapes(clean_text("plain text, fine."))


def test_review_queue_flags_only_material_changes():
    from pipeline import review
    rows = [_row("p1", "c1"), _row("p2", "c2", "concern")]
    syn = {"saying": "Commenters ask for tiers.", "dominant_response_type": "recommendation",
           "disagreement": {"exists": False, "about": ["thresholds"]}, "stakeholder_divide": {"exists": False}}
    prior = review.question_snapshot("q8", rows, syn, has_vahana_read=True)
    # One more commenter repeating an existing issue and response type: not material.
    same = review.question_snapshot("q8", rows + [_row("p3", "c3")], syn, True)
    assert review.compare_snapshots(prior, same) == []
    # A new stakeholder group and a new issue/response-type combination: material.
    changed_rows = rows + [_row("p4", "c9", "scope_challenge", "patient_consumer_group", "intended_use")]
    new = review.question_snapshot("q8", changed_rows, dict(syn, saying="Commenters now challenge the scope entirely and ask FDA to start over."), True)
    reasons = {r["reason"] for r in review.compare_snapshots(prior, new)}
    assert {"new_stakeholder_group", "new_substantive_position", "synthesis_changed"} <= reasons
    # Disagreement appearing is material; a stale synthesis is flagged once.
    dis = review.question_snapshot("q8", rows, dict(syn, disagreement={"exists": True, "about": ["ownership"]}, status="stale"), True)
    reasons = {r["reason"] for r in review.compare_snapshots(prior, dis)}
    assert {"disagreement_emerged", "synthesis_stale"} <= reasons
    queue = review.build_review_queue({"q8": prior}, {"q8": new}, "2026-09-03T00:00:00Z")
    assert queue["flagged"][0]["question_id"] == "q8" and queue["flagged"][0]["vahana_read_may_need_review"] is True
    assert queue["flagged"][0]["prior_distinct_commenters"] == 2 and queue["flagged"][0]["new_distinct_commenters"] == 3
    assert review.build_review_queue(None, {"q8": new}, "t")["baseline"] is True
    # The first synthesis of a question establishes a baseline; it does not "emerge" from a pending state.
    pending = review.question_snapshot("q8", rows, None, True)
    first = review.question_snapshot("q8", rows, dict(syn, disagreement={"exists": True, "about": ["ownership"]}), True)
    assert review.compare_snapshots(pending, first) == []


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if "tmp_path" in fn.__code__.co_varnames:
                    import tempfile
                    with tempfile.TemporaryDirectory() as d:
                        fn(Path(d))
                else:
                    fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
