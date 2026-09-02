Determine whether this substantive position raises a cross-cutting issue that is not fully captured by FDA's question as framed.

Choose zero to three:

- dynamic_intended_use
- human_ai_system_performance
- deployment_assurance_scalability
- operational_harm
- evidence_burden_commercial_viability
- ai_supplier_quality
- cybersecurity_as_safety
- distributed_accountability
- delegated_authority

Only assign a gap when the comment substantively supports it.

Return:
- gap_tags
- one-sentence explanation for each selected gap

Return structured JSON only, in this shape:

{
  "gap_tags": ["deployment_assurance_scalability"],
  "explanations": [{"gap": "deployment_assurance_scalability", "explanation": "one sentence"}]
}

Gap definitions:
{{GAP_LIST}}

FDA question(s) addressed: {{QUESTION_IDS}}
Classified position: {{POSITION}}

Source passage:

<passage>
{{PASSAGE}}
</passage>
