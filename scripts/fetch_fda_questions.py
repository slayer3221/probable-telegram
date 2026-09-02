#!/usr/bin/env python3
"""Import the exact FDA question wording into data/questions.json.

Downloads the discussion paper PDF (or reads a local copy), extracts text
with pypdf, and finds the 26 numbered questions. The extraction is
heuristic, so by default it prints the candidates for review; pass --write
to store them. Only question_text is updated; titles, themes and
explanations stay as curated.

Usage:
    python3 scripts/fetch_fda_questions.py                 # preview
    python3 scripts/fetch_fda_questions.py --write         # store into data/questions.json
    python3 scripts/fetch_fda_questions.py --pdf paper.pdf --write
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import DATA_DIR, DOCKET_META  # noqa: E402
from pipeline.io_utils import read_json, write_json  # noqa: E402

NUMBERED = re.compile(r"(?:^|\n)\s*(?:Question\s+)?(\d{1,2})[.)]\s+(.+?)(?=(?:\n\s*(?:Question\s+)?\d{1,2}[.)]\s)|\Z)", re.S)


def download(url, dest):
    import requests
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def pdf_text(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def find_questions(text):
    """Return {number: text} for a consecutive run 1..26 of numbered items
    whose text ends with a question mark."""
    candidates = {}
    for m in NUMBERED.finditer(text):
        n = int(m.group(1))
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        if 1 <= n <= 26 and "?" in body and n not in candidates:
            candidates[n] = body
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", help="local PDF path (skips download)")
    parser.add_argument("--url", default=DOCKET_META["discussion_paper_url"])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    path = Path(args.pdf) if args.pdf else download(args.url, Path("raw") / "fda-discussion-paper.pdf")
    text = pdf_text(path)
    found = find_questions(text)
    missing = [n for n in range(1, 27) if n not in found]
    for n in range(1, 27):
        print(f"Q{n}: {found.get(n, '(not found)')}\n")
    if missing:
        print(f"WARNING: could not extract {len(missing)} question(s): {missing}. Fill them in by hand from the PDF.")
    if args.write:
        data = read_json(DATA_DIR / "questions.json")
        for q in data["questions"]:
            n = q["question_number"]
            if n in found:
                q["question_text"] = found[n]
        write_json(DATA_DIR / "questions.json", data)
        print(f"wrote {len(found)} question texts to data/questions.json")


if __name__ == "__main__":
    main()
