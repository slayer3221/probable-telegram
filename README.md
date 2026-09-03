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
data/                      Public JSON the page loads (questions, commenters, submissions, positions, gaps, site-summary); live docket data only
editorial/                 Curated Vahana Labs layer: vahana-read.json, gaps.json, signals.json (never touched by ingestion)
scripts/                   Python ingestion and build pipeline (see below)
scripts/pipeline/          Shared modules: taxonomies, aggregation rules, Regulations.gov client, LLM client, storage
prompts/                   Versioned classification prompts and prompts/config.json
raw/                       Source-faithful Regulations.gov records and extracted text (attachment binaries are git-ignored)
classified/                AI-derived segments, classifications, gap tags, summaries with prompt/model metadata; consolidation/ records near-duplicate positions folded at build time
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

Until the first committed refresh, `data/` holds an empty live dataset: the page renders all 26 questions with zero commenters and the signal strip shows "Not enough comments yet". There is no demo or synthetic data in this repository.

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
analyze_positions.py   Stage 2 prompt, one structured-output call per substantive position: classification, zero to three cross-cutting gaps, and the neutral public summary (max 45 words) as separate fields -> classified/analysis
build_public_data.py   Aggregation -> data/*.json, public/build-manifest.json and public/run-metrics.json
validate_data.py       Integrity rules; non-zero exit blocks the workflow
fetch_fda_questions.py Imports exact FDA question wording from the discussion paper PDF into data/questions.json
```

Set up credentials:

```bash
cp .env.example .env      # fill in REGULATIONS_GOV_API_KEY and REGULATION_TRACKER_ANTHROPIC
pip install -r requirements.txt
set -a; source .env; set +a
python3 scripts/fetch_comments.py --limit 5     # small test run
python3 scripts/parse_attachments.py
python3 scripts/segment_comments.py
python3 scripts/analyze_positions.py
python3 scripts/build_public_data.py
python3 scripts/validate_data.py
```

### Reprocessing rules

Each stage stores an `input_hash`, its own `prompt_version`, `processing_version` and `model`. A stage reruns for a submission only when the source text changed, the upstream stage output changed, that stage's prompt version in `prompts/config.json` changed, or `PROCESSING_VERSION` in `scripts/pipeline/config.py` changed. Prompt versions are per stage, so editing the analysis prompt does not re-segment anything. Unchanged submissions are never re-sent to the model.

### Runtime, concurrency and cost

Model calls within a stage run through a bounded pool (`llm_concurrency` in `prompts/config.json`, or the `LLM_CONCURRENCY` environment variable; the workflow reads a repository variable of the same name, default 4). Every stage writes calls, retries, input and output tokens, cache reads and writes, elapsed time and an estimated cost to `public/run-metrics.json`, which the workflow prints in its run summary. Prices per model live in `prompts/config.json`.

### Attachments

Many institutional comments put the substance in an attachment. Supported formats are PDF, DOCX and TXT. If extraction fails, the submission keeps its metadata, the failure is logged in `raw/text/<id>.meta.json`, and the submission is excluded from all position counts until usable text exists. The build manifest lists every exclusion and its reason.

### Aggregation rules

- Distinct commenters, distinct submissions and substantive positions are counted separately. Several positions from one submission never inflate the commenter count.
- When one submission states the same point more than once on the same question (an executive summary and a per-question response, a passage that straddles a chunk boundary), the build folds those records into one position. The rule is deterministic and makes no model call: same submission, a shared question, the same position label, and either the shorter passage is largely contained in the longer one or the two summaries are close (`scripts/pipeline/consolidate.py`). The most complete record is kept; the merged segment ids are written to `classified/consolidation/<id>.json` and counted in `public/build-manifest.json`. Positions with different stances are never merged.
- Stakeholder-level conclusions (biggest divide, strongest alignment, implication cards) require at least 5 distinct commenters; below that the tracker says "Limited data" or "Not enough comments yet".
- A curated tension block renders only when a question has at least 3 distinct commenters from at least 2 stakeholder groups.
- No percentages are shown.
- Positions classified `unclear` with `low` confidence are not published. Model confidence is never published.

### Scheduled refresh

`.github/workflows/refresh-comments.yml` runs on demand, and daily once the repository variable `REFRESH_SCHEDULE_ENABLED` is set to `true` (scheduled runs process the whole docket and commit, so they stay off until you turn them on). It needs two repository secrets: `REGULATIONS_GOV_API_KEY` and `REGULATION_TRACKER_ANTHROPIC`. If the Anthropic key is identity-linked (the API returns "anthropic-workspace-id is required"), also set `ANTHROPIC_WORKSPACE_ID` as a secret or repository variable; a workspace-scoped key needs nothing extra. The workflow runs `scripts/check_llm_access.py` first so a bad key or workspace fails before any docket calls. Manual runs accept `fetch_limit` and `stage_limit` inputs for small live tests, and `commit_results` can be set to `false` to leave the repository untouched. It commits changes to `raw/`, `classified/`, `data/` and `public/` only. Optionally set the `LLM_MODEL` variable to override the model in `prompts/config.json`.

## Editorial layer

`editorial/vahana-read.json` holds the curated Vahana read fields per question (alignment, tension, commercialization implication, real-world deployment implication, what FDA may be missing) and the stakeholder tension blocks. It ships empty: entries are written only after reading the real submissions for a question, and ingestion never modifies the file. `editorial/gaps.json` holds the nine cross-cutting issue definitions. `editorial/signals.json` holds optional implication signal cards and also ships empty; computed cards fill the strip until it has content. Counts, stakeholder groups and representative examples under each gap are computed from commenter data at build time.

## FDA question text

`data/questions.json` carries the exact wording of all 26 discussion questions, imported verbatim from Appendix B (Consolidated Discussion Questions) of the discussion paper with `scripts/fetch_fda_questions.py`. The script downloads the PDF (or reads a local `--pdf` or `--text` file), parses the appendix and writes only `question_text`; short titles, neutral explanations, tags and the `high_impact` flag are tracker labels curated by hand. Section boundaries follow the paper: Section IV risk (Q1–Q6), Section V competency-based premarket evaluation (Q7–Q17), Section VI postmarket monitoring (Q18–Q24), Section VII other topics (Q25–Q26).

## License

Copyright Vahana Labs. All rights reserved. The source is published for transparency; no permission is granted to copy, modify, distribute or reuse it. See `LICENSE`.

## Trust model

Every interpretation is traceable to source evidence. Each commenter card offers **View evidence** (excerpt, question mapping, classification, submission date, Regulations.gov ID) and **Original comment**. There is no review or verification workflow in the data model or the code.
