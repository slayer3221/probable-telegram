#!/usr/bin/env python3
"""Import the exact FDA question wording into data/questions.json.

Reads the discussion paper (downloaded PDF, a local PDF, or an already
extracted text file), locates "Appendix B. Consolidated Discussion
Questions", and parses the 26 numbered questions verbatim. Only
question_text is updated; titles, themes and explanations stay as curated.

Usage:
    python3 scripts/fetch_fda_questions.py                    # download + preview
    python3 scripts/fetch_fda_questions.py --pdf paper.pdf --write
    python3 scripts/fetch_fda_questions.py --text paper.txt --write
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import DATA_DIR, DOCKET_META  # noqa: E402
from pipeline.io_utils import read_json, write_json  # noqa: E402

PAGE_BREAK = "\n\n=====PAGE=====\n\n"
START = re.compile(r"Appendix B\.?\s+Consolidated Discussion Questions", re.I)
NUMBER = re.compile(r"^\s*(\d{1,2})\.\s+(.*)$")
SKIP = re.compile(r"^\s*(Section\s+[IVX]+:|Discussion questions from|Appendix B|=====PAGE=====|\d{1,3}\s*)$")


def download(url, dest):
    import requests
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def pdf_text(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return PAGE_BREAK.join((p.extract_text() or "") for p in reader.pages)


def clean(lines):
    """Join wrapped lines, repairing words hyphenated across a line break."""
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if text.endswith("-") and line and line[0].isalpha() and not text.endswith("—-"):
            # e.g. "real-" + "world", "non-" + "agentic", "GenAI-" + "Enabled"
            text = text + line
        else:
            text = f"{text} {line}" if text else line
    return re.sub(r"\s+", " ", text).strip()


def find_questions(text):
    """Return {number: verbatim text} parsed from Appendix B."""
    m = START.search(text)
    if not m:
        # Appendix heading appears in the table of contents too; use the last match.
        return {}
    matches = list(START.finditer(text))
    body = text[matches[-1].end():]
    found, current, buffer = {}, None, []
    for line in body.splitlines():
        if SKIP.match(line):
            continue
        n = NUMBER.match(line)
        if n and 1 <= int(n.group(1)) <= 26 and (current is None or int(n.group(1)) == current + 1):
            if current is not None:
                found[current] = clean(buffer)
            current, buffer = int(n.group(1)), [n.group(2)]
            continue
        if current is not None:
            # A section heading can share a line with the end of a question.
            buffer.append(re.sub(r"\s*Section\s+[IVX]+:.*$", "", line))
    if current is not None:
        found[current] = clean(buffer)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", help="local PDF path (skips download)")
    parser.add_argument("--text", help="already extracted text file (skips PDF parsing)")
    parser.add_argument("--url", default=DOCKET_META["discussion_paper_url"])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.text:
        text = Path(args.text).read_text(encoding="utf-8")
    else:
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
