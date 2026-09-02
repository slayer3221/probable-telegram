"""Controlled vocabularies shared by ingestion, build and validation.

Every value here is the single source of truth. The frontend mirrors the
public labels in js/taxonomies.js; tests/test_data_integrity.py checks that
the two stay in sync.
"""

THEMES = {
    "risk": {"label": "Risk Assessment", "range": "Q1–Q6", "slug": "risk"},
    "premarket": {"label": "Premarket Evaluation", "range": "Q7–Q17", "slug": "premarket"},
    "postmarket": {"label": "Postmarket Monitoring & Change", "range": "Q18–Q24", "slug": "postmarket"},
    "foundation_models_agents": {"label": "Foundation Models & Agentic AI", "range": "Q25–Q26", "slug": "foundation"},
}

STAKEHOLDER_TYPES = {
    "device_manufacturer": {"label": "Manufacturers", "slug": "manufacturers"},
    "health_system_provider": {"label": "Health Systems", "slug": "health-systems"},
    "clinician_professional_society": {"label": "Professional Societies", "slug": "professional-societies"},
    "foundation_model_ai_platform": {"label": "AI Companies", "slug": "ai-companies"},
    "trade_association": {"label": "Trade Associations", "slug": "trade-associations"},
    "academic_research": {"label": "Researchers", "slug": "researchers"},
    "patient_consumer_group": {"label": "Patient Groups", "slug": "patient-groups"},
    "investor_vc": {"label": "Investors", "slug": "investors"},
    "individual": {"label": "Individuals", "slug": "individuals"},
    "other": {"label": "Other", "slug": "other"},
}

POSITIONS = {
    "support": {"label": "Support", "short": "Support", "slug": "support"},
    "support_with_modification": {"label": "Support with modification", "short": "Modify", "slug": "modify"},
    "oppose": {"label": "Oppose", "short": "Oppose", "slug": "oppose"},
    "mixed": {"label": "Mixed", "short": "Mixed", "slug": "mixed"},
    "unclear": {"label": "Unclear", "short": "Unclear", "slug": "unclear"},
}

ISSUES = {
    "regulatory_scope": "Regulatory scope",
    "risk_classification": "Risk classification",
    "intended_use": "Intended use",
    "directiveness": "Directiveness",
    "human_factors": "Human factors",
    "evidence_standards": "Evidence standards",
    "benchmarking": "Benchmarking",
    "clinical_validation": "Clinical validation",
    "statistical_methods": "Statistical methods",
    "synthetic_data": "Synthetic data",
    "comparator_standard_of_care": "Comparator / standard of care",
    "postmarket_monitoring": "Postmarket monitoring",
    "change_control": "Change control",
    "pccp": "PCCP",
    "foundation_model_dependency": "Foundation model dependency",
    "supplier_controls": "Supplier controls",
    "cybersecurity": "Cybersecurity",
    "agentic_autonomy": "Agentic autonomy",
    "health_system_implementation": "Health system implementation",
    "economics_burden": "Economics / burden",
    "accountability_liability": "Accountability / liability",
}

GAPS = {
    "dynamic_intended_use": "Dynamic intended use / behavioral envelope",
    "human_ai_system_performance": "Human-AI system performance",
    "deployment_assurance_scalability": "Deployment assurance & scalability",
    "operational_harm": "Operational harm",
    "evidence_burden_commercial_viability": "Evidence burden & commercial viability",
    "ai_supplier_quality": "AI supplier quality",
    "cybersecurity_as_safety": "Cybersecurity as clinical safety",
    "distributed_accountability": "Distributed accountability",
    "delegated_authority": "Delegated authority",
}

CONFIDENCE = ("high", "medium", "low")

# Minimum distinct commenters before the tracker states a stakeholder-level
# conclusion (broad support, strongest alignment, clear disagreement).
MIN_COMMENTERS_FOR_CONCLUSION = 5

# Minimum distinct commenters and distinct stakeholder groups before a
# curated tension block is rendered on a question.
MIN_COMMENTERS_FOR_TENSION = 3
MIN_GROUPS_FOR_TENSION = 2

QUESTION_IDS = [f"q{n}" for n in range(1, 27)]


def theme_for_question(n: int) -> str:
    if 1 <= n <= 6:
        return "risk"
    if 7 <= n <= 17:
        return "premarket"
    if 18 <= n <= 24:
        return "postmarket"
    return "foundation_models_agents"
