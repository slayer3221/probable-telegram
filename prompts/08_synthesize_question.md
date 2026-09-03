Write a short, descriptive synthesis of what commenters told FDA on one question of its discussion paper on generative AI-enabled medical devices. Use only the positions listed below. They are already classified and summarized from the source passages.

FDA question {{QUESTION_CODE}}: {{QUESTION_TEXT}}

Counts for this question: {{DISTINCT_COMMENTERS}} distinct commenters, {{DISTINCT_SUBMISSIONS}} submissions, {{POSITION_COUNT}} positions. Several positions can come from one commenter; count commenters, not positions, when you describe how many hold a view.
Stakeholder groups with enough representation to compare (at least {{MIN_GROUP}} distinct commenters each): {{COMPARABLE_GROUPS}}

Produce:

1. saying: one or two sentences, at most {{MAX_SAYING_WORDS}} words, stating the dominant substantive positions. Lead with the strongest sentence. Synthesize; do not list commenter asks one after another. Name an organization only when one commenter's point is singular and worth attributing.

2. dominant_response_type: the response type that best describes how most distinct commenters respond.

3. disagreement:
   - exists is true only when at least two distinct commenters take materially conflicting positions on the substance. Different wording, different emphasis, or different examples are not disagreement.
   - about: one to three topics from thresholds, scope, evidence_burden, ownership, implementation, definitions, timing, degree_of_autonomy. Fill this in whether or not exists is true; when there is no real disagreement it names what the debate is actually about.
   - text: one or two sentences, at most {{MAX_DISAGREEMENT_WORDS}} words. When exists is true, state the conflict plainly and name the sides' positions, not their organizations. When exists is false, say so explicitly and say what commenters are actually debating (for example thresholds or ownership), without inventing a tension.
   - sides: when exists is true, two entries, each with a one-line summary and the position_ids that hold it. Leave empty when exists is false.

4. stakeholder_divide:
   - claimed is true only when the disagreement falls along stakeholder-group lines among the comparable groups listed above, with more than one commenter on each side. One commenter against several others is a minority position, not a divide: describe it in disagreement text instead.
   - groups: the stakeholder group ids involved, only from the comparable list. Empty otherwise.
   - text: one sentence when claimed is true; otherwise an empty string.

5. evidence_position_ids: three to five position_ids from the list that best support the synthesis, from at least two different commenters, covering each side when a disagreement exists.

Rules:

- Describe. Do not interpret. Do not add commercialization, deployment, market, buyer, capital or operating implications, and do not speculate about consequences commenters did not raise.
- Do not infer consensus from the number of positions. Do not call anything a consensus or majority view unless most distinct commenters on the question say it.
- Do not treat "support with modification" as agreement with FDA; use the response types and summaries.
- Plain language. No "this is important", no "stakeholders broadly agree", no policy-memo phrasing.
- Use only position_ids that appear in the list.

Return structured JSON only, in this shape:

{
  "saying": "...",
  "dominant_response_type": "recommendation",
  "disagreement": {"exists": false, "about": ["thresholds"], "text": "...", "sides": []},
  "stakeholder_divide": {"claimed": false, "groups": [], "text": ""},
  "evidence_position_ids": ["p-...", "p-..."]
}

Positions on this question:

<positions>
{{POSITIONS}}
</positions>
