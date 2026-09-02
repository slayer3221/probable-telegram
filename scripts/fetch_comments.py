#!/usr/bin/env python3
"""Stage 1 of ingestion: pull comment metadata, bodies and attachment
metadata from Regulations.gov into raw/comments and raw/attachments.

Idempotent. A comment is re-fetched only when its lastModifiedDate changed.

Usage:
    python3 scripts/fetch_comments.py [--docket FDA-2026-N-7874] [--limit N] [--no-download]
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import DOCKET_ID, DOCUMENT_ID, RAW_ATTACHMENTS, ensure_dirs  # noqa: E402
from pipeline.io_utils import now_iso, write_json  # noqa: E402
from pipeline.regulations import RegulationsClient  # noqa: E402
from pipeline.store import load_raw_comment, raw_comment_path  # noqa: E402

log = logging.getLogger("fetch")
# Metadata kept from each comment. Personal names and the representative's
# postal address are deliberately not stored: the tracker never displays
# them, and the source_url points to the full public record on Regulations.gov.
KEEP_ATTRS = (
    "title", "comment", "organization", "category", "postedDate",
    "receiveDate", "lastModifiedDate", "docketId", "commentOnDocumentId", "submitterRep",
    "govAgency", "govAgencyType", "stateProvinceRegion", "country",
    "duplicateComments", "withdrawn", "openForComment", "pageCount", "trackingNbr", "modifyDate",
)


def resolve_document(client, docket_id, document_id):
    """Find the request-for-feedback document and its objectId."""
    if document_id:
        doc = client.get_document(document_id)
        if doc:
            return doc
    docs = client.list_documents(docket_id)
    if not docs:
        raise SystemExit(f"no documents found in docket {docket_id}")
    # Prefer a document open for comment; otherwise the first notice.
    docs.sort(key=lambda d: (not d["attributes"].get("openForComment"), d["attributes"].get("postedDate") or ""))
    return client.get_document(docs[0]["id"])


def save_attachments(client, comment_id, included, download=True):
    out = []
    for item in included:
        if item.get("type") != "attachments":
            continue
        attrs = item.get("attributes", {})
        for fmt in attrs.get("fileFormats") or []:
            url = fmt.get("fileUrl")
            if not url:
                continue
            ext = "." + (fmt.get("format") or url.rsplit(".", 1)[-1]).lower().strip(".")
            local = RAW_ATTACHMENTS / comment_id / f"{item['id']}{ext}"
            record = {
                "id": item["id"], "title": attrs.get("title"), "format": fmt.get("format"),
                "size": fmt.get("size"), "file_url": url, "local_path": str(local.relative_to(local.parents[3])),
                "downloaded": False, "error": None,
            }
            if download:
                try:
                    local.parent.mkdir(parents=True, exist_ok=True)
                    if not local.exists():
                        client.download(url, local)
                    record["downloaded"] = True
                except Exception as exc:  # noqa: BLE001
                    record["error"] = str(exc)
                    log.warning("attachment download failed %s: %s", url, exc)
            out.append(record)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docket", default=DOCKET_ID)
    parser.add_argument("--document", default=DOCUMENT_ID)
    parser.add_argument("--limit", type=int, default=0, help="stop after N comments (testing)")
    parser.add_argument("--no-download", action="store_true", help="record attachment metadata without downloading")
    parser.add_argument("--force", action="store_true", help="re-fetch every comment")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_dirs()

    client = RegulationsClient()
    document = resolve_document(client, args.docket, args.document)
    object_id = document["attributes"]["objectId"]
    log.info("document %s (%s) objectId=%s", document["id"], document["attributes"].get("title"), object_id)

    fetched = skipped = 0
    for summary in client.iter_comments(object_id):
        comment_id = summary["id"]
        last_modified = summary.get("attributes", {}).get("lastModifiedDate")
        existing = load_raw_comment(comment_id)
        if existing and not args.force and existing.get("last_modified_date") == last_modified:
            skipped += 1
            continue
        data, included = client.get_comment(comment_id)
        attrs = data.get("attributes", {})
        record = {
            "regulations_gov_comment_id": comment_id,
            "document_id": document["id"],
            "docket_id": args.docket,
            "source_url": f"https://www.regulations.gov/comment/{comment_id}",
            "last_modified_date": last_modified or attrs.get("lastModifiedDate"),
            "attributes": {k: attrs.get(k) for k in KEEP_ATTRS if k in attrs},
            "attachments": save_attachments(client, comment_id, included, download=not args.no_download),
            "fetched_at": now_iso(),
        }
        write_json(raw_comment_path(comment_id), record)
        fetched += 1
        log.info("fetched %s (%d attachments)", comment_id, len(record["attachments"]))
        if args.limit and fetched >= args.limit:
            break
    log.info("done: %d fetched, %d unchanged", fetched, skipped)


if __name__ == "__main__":
    main()
