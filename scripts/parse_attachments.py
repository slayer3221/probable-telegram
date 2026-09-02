#!/usr/bin/env python3
"""Stage 2: extract attachment text and assemble the canonical raw text
(comment body + attachment text) for each submission in raw/text.

A submission is marked unusable when neither the body nor any attachment
yields substantive text; such submissions keep their metadata but are
excluded from classification until usable text exists.

Usage:
    python3 scripts/parse_attachments.py [--force]
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import PROMPT_CONFIG, ROOT, ensure_dirs  # noqa: E402
from pipeline.io_utils import content_hash, now_iso, write_json  # noqa: E402
from pipeline.store import (list_raw_comment_ids, load_raw_comment, load_text_meta,  # noqa: E402
                            raw_text_meta_path, raw_text_path)
from pipeline.text_extract import extract, normalize  # noqa: E402

log = logging.getLogger("parse")
MIN_CHARS = PROMPT_CONFIG.get("min_substantive_chars", 200)
BOILERPLATE = ("see attached", "please see attached", "see attachment", "attached please find")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()

    usable = unusable = unchanged = 0
    for comment_id in list_raw_comment_ids():
        raw = load_raw_comment(comment_id)
        meta = load_text_meta(comment_id)
        if meta and not args.force and meta.get("fetched_at") == raw.get("fetched_at"):
            unchanged += 1
            continue
        body = normalize(raw["attributes"].get("comment") or "")
        parts = []
        if body:
            parts.append(body)
        attachment_meta = []
        for att in raw.get("attachments", []):
            local = ROOT / att["local_path"]
            if not att.get("downloaded") or not local.exists():
                attachment_meta.append({"id": att["id"], "status": "missing", "chars": 0, "error": att.get("error") or "not downloaded"})
                continue
            result = extract(local)
            attachment_meta.append({"id": att["id"], "status": result["status"], "chars": len(result["text"]), "error": result["error"]})
            if result["status"] == "ok":
                parts.append(f"[Attachment: {att.get('title') or att['id']}]\n{result['text']}")
        text = "\n\n".join(parts)
        body_is_pointer = len(body) < MIN_CHARS and any(b in body.lower() for b in BOILERPLATE)
        has_usable = len(text) >= MIN_CHARS and not (body_is_pointer and len(text) == len(body))
        raw_text_path(comment_id).write_text(text, encoding="utf-8")
        write_json(raw_text_meta_path(comment_id), {
            "comment_id": comment_id,
            "fetched_at": raw.get("fetched_at"),
            "extracted_at": now_iso(),
            "content_hash": content_hash(text),
            "body_chars": len(body),
            "total_chars": len(text),
            "attachments": attachment_meta,
            "usable": has_usable,
            "exclusion_reason": None if has_usable else "no usable text extracted",
        })
        if has_usable:
            usable += 1
        else:
            unusable += 1
            log.warning("%s has no usable text; excluded from classification", comment_id)
    log.info("done: %d usable, %d unusable, %d unchanged", usable, unusable, unchanged)


if __name__ == "__main__":
    main()
