"""Data integrity tests. Run with `python3 -m pytest tests/` or `python3 tests/test_data_integrity.py`."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import aggregate, taxonomies  # noqa: E402
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
        if path.is_dir() or any(part in ("node_modules", ".git", "raw", "classified", "screenshots", "__pycache__", ".pytest_cache") for part in path.parts):
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


def test_seed_is_deterministic(tmp_path):
    before = (ROOT / "data" / "positions.json").read_bytes()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_synthetic_data.py")], check=True, capture_output=True)
    after = json.loads((ROOT / "data" / "positions.json").read_text(encoding="utf-8"))
    assert json.loads(before)["positions"] == after["positions"]


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(Path("/tmp")) if "tmp_path" in fn.__code__.co_varnames else fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
