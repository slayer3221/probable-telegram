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


def test_tiny_dataset_yields_four_signals(tmp_path):
    """A first live run may have only a couple of commenters; the signal strip
    must still hold four cards and the dataset must validate."""
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
    assert len(summary["signals"]) == 4, [c["label"] for c in summary["signals"]]
    assert all("Limited data" in c["evidence"] or "Not enough" in c["headline"] for c in summary["signals"][1:])
    assert summary["metrics"]["comments_analyzed"] == 3
    assert summary["metrics"]["commenters_represented"] == 2
    out = tmp_path / "data"
    out.mkdir()
    (out / "questions.json").write_text(json.dumps({"questions": questions}), encoding="utf-8")
    for name, payload in files.items():
        (out / name).write_text(json.dumps(payload), encoding="utf-8")
    errors, _ = validate(out, ROOT / "editorial")
    assert errors == [], "\n".join(errors)


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
