# FDA GenAI Comment Tracker

A public intelligence resource from Vahana Labs for FDA's August 18, 2026 discussion paper, *Considerations for the Regulation of Generative AI-Enabled Medical Devices* (docket [FDA-2026-N-7874](https://www.regulations.gov/docket/FDA-2026-N-7874), comments due October 19, 2026).

The tracker reads every public submission to the docket, maps each substantive position to the FDA question it answers, classifies the position, and keeps the source excerpt attached to the claim. Vahana Labs' editorial analysis (stakeholder tensions, commercialization and real-world deployment implications, and what FDA may be missing) is stored and rendered separately from what commenters said.

Everything happens on one scrolling page: accordion question cards, sticky filters, in-page views, hash anchors and query parameters, an evidence drawer and a mobile filter drawer.

## Repository layout

```text
index.html                 The single page
css/styles.css             Vahana Labs visual language (tokens, components, responsive rules)
js/app.js                  Bootstrap, state, URL sync, drawers, focus management
js/filters.js              Filter state, URL parsing, matching and per-question counts
js/tracker.js              Rendering (hero, signals, question cards, gaps, evidence drawer)
js/taxonomies.js           Public labels; mirrors scripts/pipeline/taxonomies.py
data/                      Public JSON the page loads (questions, commenters, submissions, positions, gaps, site-summary)
editorial/                 Curated Vahana Labs layer: vahana-read.json, gaps.json, signals.json (never touched by ingestion)
scripts/                   Python ingestion and build pipeline (see below)
scripts/pipeline/          Shared modules: taxonomies, aggregation rules, Regulations.gov client, LLM client, storage
prompts/                   Versioned classification prompts and prompts/config.json
raw/                       Source-faithful Regulations.gov records and extracted text (attachment binaries are git-ignored)
classified/                AI-derived segments, classifications, gap tags, summaries with prompt/model metadata
public/                    Build manifest (versions, counts, exclusions)
tests/                     Data integrity tests and a Playwright end-to-end script
docs/DATA_SCHEMA.md        Field-level schema documentation
.github/workflows/         Scheduled refresh and GitHub Pages deployment
```

## Running locally

The page loads JSON with `fetch`, so serve the folder over HTTP rather than opening the file directly.

```bash
python3 -m http.server 8000
# open http://localhost:8000/
```

Regenerate the synthetic demo dataset at any time (deterministic):

```bash
python3 scripts/seed_synthetic_data.py
python3 scripts/validate_data.py
```

Run the tests:

```bash
python3 tests/test_data_integrity.py          # or: python3 -m pytest tests/
node tests/e2e.mjs http://127.0.0.1:8000       # needs the playwright package and a Chromium build
```

## Deploying to GitHub Pages

1. In the repository settings, under **Pages**, set the source to **GitHub Actions**.
2. Push to `main`. The `Deploy to GitHub Pages` workflow validates `data/` and publishes only `index.html`, `css/`, `js/`, `data/` and `editorial/`. The `raw/` and `classified/` folders stay in the repository for provenance but are not served.
3. The workflow also runs after every successful `Refresh comments` run, so refreshed data goes live automatically.

If you prefer branch-based Pages (serve from `main`, root), the site still works because all paths are relative. In that case the provenance folders are also publicly reachable, which is acceptable for public docket data but not required.

## Deep links and filters

| URL | Effect |
|---|---|
| `#q19` or `?q=19` | Loads, scrolls to and expands question 19 |
| `?theme=postmarket` | Theme filter: `risk`, `premarket`, `postmarket`, `foundation` |
| `?stakeholder=health-systems` | Stakeholder filter (slugs in `js/taxonomies.js`) |
| `?position=modify` | Position filter: `support`, `modify`, `oppose`, `mixed`, `unclear` |
| `?view=tensions` | View: `questions`, `tensions`, `missed` |
| `?search=telemetry` | Search organization, issue, gap and summary text |

Filters combine, and the URL is kept in sync as you change them.

## Data refresh pipeline (Milestone 2)

All AI processing happens during ingestion. The browser only reads static JSON.

```text
fetch_comments.py      Regulations.gov -> raw/comments/*.json, raw/attachments/
parse_attachments.py   PDF/DOCX/TXT extraction -> raw/text/*.txt (+ .meta.json with usability and content hash)
segment_comments.py    Stage 1 prompt: identify commenter, split into substantive positions -> classified/segments, classified/commenters.json
classify_positions.py  Stage 2 prompt: position, issues, concern, requested action, confidence -> classified/positions
classify_gaps.py       Stage 3 prompt: zero to three cross-cutting gaps -> classified/gaps
generate_summaries.py  Stage 4 prompt: neutral public summary (max 45 words) -> classified/summaries
build_public_data.py   Aggregation -> data/*.json and public/build-manifest.json
validate_data.py       Integrity rules; non-zero exit blocks the workflow
fetch_fda_questions.py Imports exact FDA question wording from the discussion paper PDF into data/questions.json
```

Set up credentials:

```bash
cp .env.example .env      # fill in REGULATIONS_GOV_API_KEY and ANTHROPIC_API_KEY
pip install -r requirements.txt
set -a; source .env; set +a
python3 scripts/fetch_comments.py --limit 5     # small test run
python3 scripts/parse_attachments.py
python3 scripts/segment_comments.py
python3 scripts/classify_positions.py
python3 scripts/classify_gaps.py
python3 scripts/generate_summaries.py
python3 scripts/build_public_data.py
python3 scripts/validate_data.py
```

### Reprocessing rules

Each stage stores an `input_hash`, `prompt_version`, `processing_version` and `model`. A stage reruns for a submission only when the source text changed, the upstream stage output changed, the prompt version in `prompts/config.json` changed, or `PROCESSING_VERSION` in `scripts/pipeline/config.py` changed. Unchanged submissions are never re-sent to the model.

### Attachments

Many institutional comments put the substance in an attachment. Supported formats are PDF, DOCX and TXT. If extraction fails, the submission keeps its metadata, the failure is logged in `raw/text/<id>.meta.json`, and the submission is excluded from all position counts until usable text exists. The build manifest lists every exclusion and its reason.

### Aggregation rules

- Distinct commenters, distinct submissions and substantive positions are counted separately. Several positions from one submission never inflate the commenter count.
- Stakeholder-level conclusions (biggest divide, strongest alignment, implication cards) require at least 5 distinct commenters; below that the tracker says "Limited data" or "Not enough comments yet".
- A curated tension block renders only when a question has at least 3 distinct commenters from at least 2 stakeholder groups.
- No percentages are shown.
- Positions classified `unclear` with `low` confidence are not published. Model confidence is never published.

### Scheduled refresh

`.github/workflows/refresh-comments.yml` runs daily and on demand. It needs two repository secrets: `REGULATIONS_GOV_API_KEY` and `ANTHROPIC_API_KEY`. It commits changes to `raw/`, `classified/`, `data/` and `public/` only. Optionally set the `LLM_MODEL` variable to override the model in `prompts/config.json`.

## Editorial layer

`editorial/vahana-read.json` holds the curated Vahana read fields per question (alignment, tension, commercialization implication, real-world deployment implication, what FDA may be missing) and the stakeholder tension blocks. `editorial/gaps.json` holds the nine cross-cutting issue definitions. `editorial/signals.json` holds the two implication signal cards. Ingestion reads these files and never writes to them; counts, stakeholder groups and representative examples under each gap are computed from commenter data at build time.

## FDA question text

`data/questions.json` reserves `question_text` for the exact wording from the discussion paper. It is empty in the seed dataset because the paper could not be fetched from the environment where the seed was built. Run `python3 scripts/fetch_fda_questions.py` (preview) then `--write` to import it, and review the result against the PDF. Until the text is imported, the page shows a pending notice with a link to the source instead of paraphrasing FDA wording. Short titles, the neutral explanations and the section boundaries (Q1–Q6, Q7–Q17, Q18–Q24, Q25–Q26) are tracker labels and should be reconciled against the paper at the same time.

## Trust model

Every interpretation is traceable to source evidence. Each commenter card offers **View evidence** (excerpt, question mapping, classification, submission date, Regulations.gov ID) and **Original comment**. There is no review or verification workflow in the data model or the code.
