# Data schema

Three layers are kept apart: `raw/` (source-faithful), `classified/` (AI-derived, with prompt and model metadata) and `data/` (the minimal public layer the page reads). The curated editorial layer lives in `editorial/`. Controlled vocabularies are defined once in `scripts/pipeline/taxonomies.py` and mirrored in `js/taxonomies.js`.

## Vocabularies

**Themes** `risk`, `premarket`, `postmarket`, `foundation_models_agents`
Public sections: Risk Assessment (Q1–Q6), Premarket Evaluation (Q7–Q17), Postmarket Monitoring & Change (Q18–Q24), Foundation Models & Agentic AI (Q25–Q26).

**Stakeholder types** and public labels

| Internal value | Public label | URL slug |
|---|---|---|
| device_manufacturer | Manufacturers | manufacturers |
| health_system_provider | Health Systems | health-systems |
| clinician_professional_society | Professional Societies | professional-societies |
| foundation_model_ai_platform | AI Companies | ai-companies |
| trade_association | Trade Associations | trade-associations |
| academic_research | Researchers | researchers |
| patient_consumer_group | Patient Groups | patient-groups |
| investor_vc | Investors | investors |
| individual | Individuals | individuals |
| other | Other | other |

**Positions** `support`, `support_with_modification`, `oppose`, `mixed`, `unclear` (public labels: Support, Support with modification, Oppose, Mixed, Unclear). These are never collapsed into positive/negative sentiment.

**Issues** `regulatory_scope`, `risk_classification`, `intended_use`, `directiveness`, `human_factors`, `evidence_standards`, `benchmarking`, `clinical_validation`, `statistical_methods`, `synthetic_data`, `comparator_standard_of_care`, `postmarket_monitoring`, `change_control`, `pccp`, `foundation_model_dependency`, `supplier_controls`, `cybersecurity`, `agentic_autonomy`, `health_system_implementation`, `economics_burden`, `accountability_liability`

**Cross-cutting gaps** (zero to three per position) `dynamic_intended_use`, `human_ai_system_performance`, `deployment_assurance_scalability`, `operational_harm`, `evidence_burden_commercial_viability`, `ai_supplier_quality`, `cybersecurity_as_safety`, `distributed_accountability`, `delegated_authority`

**Confidence** `high`, `medium`, `low`. Internal only; never written to `data/`.

## Public layer (`data/`)

### questions.json

```json
{
  "source": {"title": "", "pdf_url": "", "docket_id": "", "docket_url": "", "document_id": "", "comment_deadline": ""},
  "questions": [{
    "id": "q1", "question_number": 1,
    "question_text": "exact FDA wording from Appendix B of the discussion paper",
    "short_title": "tracker label", "theme": "risk", "source_url": "", "high_impact": true,
    "summary_ask": "one-sentence neutral description of what FDA asks",
    "about": "neutral explanation shown under 'What this is really about' (optional)",
    "tags": ["topic tag"]
  }]
}
```

This file is curated by hand. Only `question_text` is written by `scripts/fetch_fda_questions.py`.

### commenters.json

```json
{"commenters": [{"id": "", "display_name": "", "organization": "", "stakeholder_type": ""}]}
```

`source_identity_text` exists in the classified layer and is not published. Individuals are shown as "Individual commenter" plus a stated role; personal names are not surfaced.

### submissions.json

```json
{"submissions": [{"id": "", "regulations_gov_comment_id": "", "commenter_id": "", "received_date": "YYYY-MM-DD", "posted_date": "YYYY-MM-DD", "source_url": "", "has_attachments": false}]}
```

Comment bodies, attachment URLs and raw text stay in `raw/`.

### positions.json

```json
{"positions": [{
  "id": "", "submission_id": "", "commenter_id": "", "question_ids": ["q19"],
  "position": "support_with_modification", "primary_issue": "", "secondary_issue": null,
  "stakeholder_concern": "", "requested_fda_action": "", "public_summary": "max 45 words",
  "supporting_text": "verbatim source excerpt", "gap_tags": [], "featured": false
}]}
```

Every position keeps its submission id (which resolves to a source URL and Regulations.gov id), its supporting excerpt and its FDA question mapping. `commenter_id` is denormalized from the submission for convenience and is validated to match.

### gaps.json

Computed at build time from `editorial/gaps.json` plus positions.

```json
{"gaps": [{
  "id": "distributed_accountability", "title": "", "explanation": "",
  "question_ids": ["q19", "q13", "q20"], "distinct_commenters": 8, "positions": 11,
  "stakeholder_types": ["health_system_provider"],
  "examples": [{"position_id": "", "commenter_id": "", "display_name": "", "question_id": "q19", "excerpt": ""}]
}]}
```

`question_ids` are the three questions most often associated with the gap. `examples` holds up to three source-backed quotes, one per commenter, featured positions first.

### site-summary.json

```json
{
  "generated_at": "ISO timestamp", "dataset_kind": "synthetic | live", "processing_version": "",
  "docket": {"docket_id": "", "docket_url": "", "document_id": "", "discussion_paper_url": "", "comment_deadline": "", "paper_date": ""},
  "metrics": {"comments_analyzed": 0, "commenters_represented": 0, "positions_identified": 0, "questions_tracked": 26, "comment_deadline": "", "last_updated": ""},
  "thresholds": {"min_commenters_for_conclusion": 5, "min_commenters_for_tension": 3, "min_groups_for_tension": 2},
  "signals": [{"category": "", "label": "", "headline": "", "detail": "", "evidence": "", "target_question_id": "q19"}],
  "question_stats": {"q1": {"distinct_commenters": 0, "distinct_submissions": 0, "positions": 0, "stakeholder_mix": {}, "position_distribution": {}, "tension_eligible": false, "conclusion_eligible": false}},
  "gap_totals": {"gap_id": 0}
}
```

Exactly four signal cards are published. Most discussed, biggest stakeholder divide, strongest alignment and emerging blind spot are computed; commercialization and deployment cards come from `editorial/signals.json` and are shown only when the referenced gap or questions meet the conclusion threshold.

## Editorial layer (`editorial/`)

### vahana-read.json

```json
{"questions": {"q19": {
  "tension": {"groups": [{"label": "Health systems", "text": ""}], "synthesis": ""},
  "vahana_read": {"alignment": "", "tension": "", "commercialization": "", "deployment": "", "missing": ""}
}}}
```

All `vahana_read` fields are optional; only fields with content render. A `tension` block renders only when the question's live data meets the tension threshold.

### gaps.json and signals.json

Titles and explanations for the nine gaps, and the two editorial signal cards (`category`, `label`, `headline`, `detail`, `question_ids`, `gap_id`, `target_question_id`).

## Raw layer (`raw/`)

- `raw/comments/<comment_id>.json`: Regulations.gov metadata subset, source URL, `last_modified_date`, attachment metadata (`file_url`, `local_path`, `downloaded`, `error`), `fetched_at`.
- `raw/text/<comment_id>.txt`: canonical raw text (comment body followed by each extracted attachment).
- `raw/text/<comment_id>.meta.json`: `content_hash`, character counts, per-attachment extraction status, `usable`, `exclusion_reason`.
- `raw/attachments/<comment_id>/`: downloaded binaries (git-ignored).

Raw text is never overwritten with interpretations.

## Classified layer (`classified/`)

Every file carries `comment_id`, `input_hash`, `prompt_version`, `processing_version`, `model`, `created_at`.

- `segments/<id>.json`: `positions[]` with `segment_id`, `question_ids`, `source_passage`, `position_gist`.
- `positions/<id>.json`: `positions[]` with `segment_id`, `question_ids`, `position`, `primary_issue`, `secondary_issue`, `stakeholder_concern`, `requested_fda_action`, `confidence`, `source_passage`.
- `gaps/<id>.json`: `gaps{segment_id: {gap_tags, explanations}}`.
- `summaries/<id>.json`: `summaries{segment_id: text}`.
- `commenters.json`: `commenters{comment_id: {display_name, organization, stakeholder_type, source_identity_text, confidence, input_hash, prompt_version, model}}`.

## Integrity rules enforced by `scripts/validate_data.py`

- 26 questions, ids `q1`..`q26` in order, valid themes.
- Every position references an existing submission; every submission references an existing commenter; `commenter_id` on a position matches its submission.
- Vocabulary values only; at most three gap tags; supporting excerpt and summary required; summaries at most 45 words.
- `model_confidence` and any review or verification field are absent from public data.
- Per question: distinct commenters <= distinct submissions <= positions; distributions sum correctly.
- Exactly nine gaps, at most three examples each, all references resolvable.
- Exactly four signal cards targeting valid questions.
- Editorial entries keyed by valid question ids with only the allowed fields.
