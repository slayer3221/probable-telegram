"""Minimal Regulations.gov v4 API client with pagination and rate-limit handling."""
import logging
import time

import requests

from .config import REGULATIONS_API_BASE, REGULATIONS_API_KEY

log = logging.getLogger("regulations")
PAGE_SIZE = 250
MAX_PAGES = 20  # API caps page[number] at 20; beyond that, window on lastModifiedDate.


class RegulationsClient:
    def __init__(self, api_key=None, session=None, min_interval=0.35):
        self.api_key = api_key or REGULATIONS_API_KEY
        if not self.api_key:
            raise RuntimeError("REGULATIONS_GOV_API_KEY is not set")
        self.session = session or requests.Session()
        self.min_interval = min_interval
        self._last = 0.0

    def _get(self, path, params=None, absolute=False, stream=False, retries=5):
        url = path if absolute else f"{REGULATIONS_API_BASE}{path}"
        headers = {} if absolute else {"X-Api-Key": self.api_key}
        for attempt in range(retries):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            resp = self.session.get(url, params=params, headers=headers, timeout=90, stream=stream)
            if resp.status_code == 429:
                delay = int(resp.headers.get("Retry-After", "0") or 0) or min(60 * (attempt + 1), 900)
                log.warning("rate limited; sleeping %ss", delay)
                time.sleep(delay)
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError(f"request failed after retries: {url}")

    def list_documents(self, docket_id):
        resp = self._get("/documents", {"filter[docketId]": docket_id, "page[size]": PAGE_SIZE})
        return resp.json().get("data", [])

    def get_document(self, document_id):
        return self._get(f"/documents/{document_id}").json().get("data")

    def iter_comments(self, object_id):
        """Yield comment summaries for a document objectId, walking all pages."""
        last_modified_floor = None
        seen = set()
        while True:
            page = 1
            page_items = 0
            last_seen_date = None
            while page <= MAX_PAGES:
                params = {
                    "filter[commentOnId]": object_id,
                    "page[size]": PAGE_SIZE,
                    "page[number]": page,
                    "sort": "lastModifiedDate,documentId",
                }
                if last_modified_floor:
                    params["filter[lastModifiedDate][ge]"] = last_modified_floor
                payload = self._get("/comments", params).json()
                data = payload.get("data", [])
                for item in data:
                    last_seen_date = item.get("attributes", {}).get("lastModifiedDate") or last_seen_date
                    if item["id"] in seen:
                        continue
                    seen.add(item["id"])
                    page_items += 1
                    yield item
                meta = payload.get("meta", {})
                if not meta.get("hasNextPage") or not data:
                    return
                page += 1
            # More than 20 pages: continue from the last modified date seen.
            if not last_seen_date or last_seen_date == last_modified_floor or page_items == 0:
                return
            last_modified_floor = last_seen_date.replace("T", " ").replace("Z", "")

    def get_comment(self, comment_id):
        payload = self._get(f"/comments/{comment_id}", {"include": "attachments"}).json()
        return payload.get("data"), payload.get("included", [])

    def download(self, url, dest_path):
        resp = self._get(url, absolute=True, stream=True)
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
        return dest_path
