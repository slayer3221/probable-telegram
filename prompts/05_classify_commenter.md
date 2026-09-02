Identify who submitted this public comment, using only what the submission itself states.

Return structured JSON only, in this shape:

{
  "display_name": "name to show publicly (organization name, or 'Individual commenter' with a short role in parentheses if the text states one)",
  "organization": "organization name if the submission is on behalf of an organization, otherwise empty string",
  "stakeholder_type": "one of the allowed values",
  "source_identity_text": "short verbatim passage or metadata field supporting the identification",
  "confidence": "high | medium | low"
}

Allowed stakeholder_type values:
- device_manufacturer
- health_system_provider
- clinician_professional_society
- foundation_model_ai_platform
- trade_association
- academic_research
- patient_consumer_group
- investor_vc
- individual
- other

Rules:
- Do not infer an organization or stakeholder identity unless the submission or its Regulations.gov metadata supports it.
- Use "individual" when a person writes on their own behalf, even if they mention an employer.
- Use "other" when the organization type does not fit any category (for example payers, government bodies, law firms, consultancies).
- Do not include personal names of individuals in display_name; use "Individual commenter" plus a stated role, e.g. "Individual commenter (clinical pharmacist)".

Regulations.gov metadata:
{{METADATA}}

Opening of the submission text:

<submission>
{{TEXT}}
</submission>
