Classify the substantive position below.

Return:

1. FDA question(s): Q1-Q26
2. Position:
   - support
   - support_with_modification
   - oppose
   - mixed
   - unclear
3. Primary issue
4. Secondary issue, if applicable
5. Main stakeholder concern
6. What the commenter wants FDA to do
7. Confidence:
   - high
   - medium
   - low

Rules:

- Support with modification means the commenter accepts the general direction but requests a substantive change.
- Criticism of implementation details does not automatically mean opposition.
- Use mixed when a commenter supports some aspects and rejects others.
- Use unclear when the source does not justify a confident interpretation.
- Do not infer motive.
- Do not infer a position from the commenter's organization or stakeholder category.
- Preserve qualifiers.
- Base every field on the source passage.

Issue values (use exactly one for primary_issue and at most one for secondary_issue):
{{ISSUE_LIST}}

Return structured JSON only, in this shape:

{
  "question_ids": ["q7"],
  "position": "support_with_modification",
  "primary_issue": "evidence_standards",
  "secondary_issue": "economics_burden",
  "stakeholder_concern": "one or two sentences",
  "requested_fda_action": "one or two sentences",
  "confidence": "high"
}

Proposed question mapping from segmentation: {{QUESTION_IDS}}

Source passage:

<passage>
{{PASSAGE}}
</passage>
