// Public vocabularies. Internal values must match scripts/pipeline/taxonomies.py.
export const THEMES = [
  { id: 'risk', slug: 'risk', label: 'Risk Assessment', filterLabel: 'Risk', range: 'Q1–Q6',
    blurb: 'How risk should be characterized for systems whose output is not fixed, and where intended use begins and ends.' },
  { id: 'premarket', slug: 'premarket', label: 'Premarket Evaluation', filterLabel: 'Premarket Evidence', range: 'Q7–Q17',
    blurb: 'What evidence FDA should expect before market, and how performance should be measured and reported.' },
  { id: 'postmarket', slug: 'postmarket', label: 'Postmarket Monitoring & Change', filterLabel: 'Postmarket', range: 'Q18–Q24',
    blurb: 'What happens after clearance: monitoring, drift, change control, and the site where the product actually runs.' },
  { id: 'foundation_models_agents', slug: 'foundation', label: 'Foundation Models & Agentic AI', filterLabel: 'Foundation Models & Agents', range: 'Q25–Q26',
    blurb: 'Dependence on third-party models, and systems that take action rather than produce text.' },
];

export const STAKEHOLDERS = [
  { id: 'device_manufacturer', slug: 'manufacturers', label: 'Manufacturers' },
  { id: 'health_system_provider', slug: 'health-systems', label: 'Health Systems' },
  { id: 'clinician_professional_society', slug: 'professional-societies', label: 'Professional Societies' },
  { id: 'foundation_model_ai_platform', slug: 'ai-companies', label: 'AI Companies' },
  { id: 'trade_association', slug: 'trade-associations', label: 'Trade Associations' },
  { id: 'academic_research', slug: 'researchers', label: 'Researchers' },
  { id: 'patient_consumer_group', slug: 'patient-groups', label: 'Patient Groups' },
  { id: 'investor_vc', slug: 'investors', label: 'Investors' },
  { id: 'individual', slug: 'individuals', label: 'Individuals' },
  { id: 'other', slug: 'other', label: 'Other' },
];

export const POSITIONS = [
  { id: 'support', slug: 'support', label: 'Support', short: 'Support', filterLabel: 'Support', cssVar: '--pos-support' },
  { id: 'support_with_modification', slug: 'modify', label: 'Support with modification', short: 'Modify', filterLabel: 'Support with Modification', cssVar: '--pos-modify' },
  { id: 'oppose', slug: 'oppose', label: 'Oppose', short: 'Oppose', filterLabel: 'Oppose', cssVar: '--pos-oppose' },
  { id: 'mixed', slug: 'mixed', label: 'Mixed', short: 'Mixed', filterLabel: 'Mixed', cssVar: '--pos-mixed' },
  { id: 'unclear', slug: 'unclear', label: 'Unclear', short: 'Unclear', filterLabel: 'Unclear', cssVar: '--pos-unclear' },
];

export const ISSUES = {
  regulatory_scope: 'Regulatory scope', risk_classification: 'Risk classification', intended_use: 'Intended use',
  directiveness: 'Directiveness', human_factors: 'Human factors', evidence_standards: 'Evidence standards',
  benchmarking: 'Benchmarking', clinical_validation: 'Clinical validation', statistical_methods: 'Statistical methods',
  synthetic_data: 'Synthetic data', comparator_standard_of_care: 'Comparator / standard of care',
  postmarket_monitoring: 'Postmarket monitoring', change_control: 'Change control', pccp: 'PCCP',
  foundation_model_dependency: 'Foundation model dependency', supplier_controls: 'Supplier controls',
  cybersecurity: 'Cybersecurity', agentic_autonomy: 'Agentic autonomy',
  health_system_implementation: 'Health system implementation', economics_burden: 'Economics / burden',
  accountability_liability: 'Accountability / liability',
};

export const GAPS = {
  dynamic_intended_use: 'Dynamic intended use / behavioral envelope',
  human_ai_system_performance: 'Human-AI system performance',
  deployment_assurance_scalability: 'Deployment assurance & scalability',
  operational_harm: 'Operational harm',
  evidence_burden_commercial_viability: 'Evidence burden & commercial viability',
  ai_supplier_quality: 'AI supplier quality',
  cybersecurity_as_safety: 'Cybersecurity as clinical safety',
  distributed_accountability: 'Distributed accountability',
  delegated_authority: 'Delegated authority',
};

export const RESPONSE_TYPES = {
  direct_answer: 'Direct answer',
  recommendation: 'Recommendation',
  concern: 'Concern',
  proposed_criterion: 'Proposed criterion',
  evidence_suggestion: 'Evidence suggestion',
  scope_challenge: 'Scope challenge',
  implementation_issue: 'Implementation issue',
  no_clear_answer: 'No clear answer',
};

export const DISAGREEMENT_TOPICS = {
  thresholds: 'Thresholds',
  scope: 'Scope',
  evidence_burden: 'Evidence burden',
  ownership: 'Ownership',
  implementation: 'Implementation',
  definitions: 'Definitions',
  timing: 'Timing',
  degree_of_autonomy: 'Degree of autonomy',
};

export const VAHANA_FIELDS = [
  ['alignment', 'Where there is alignment'],
  ['tension', 'Where there is tension'],
  ['commercialization', 'Commercialization implication'],
  ['deployment', 'Real-world deployment implication'],
  ['missing', 'What FDA may be missing'],
];

export const VIEWS = [
  { id: 'questions', label: 'FDA Questions' },
  { id: 'tensions', label: 'Stakeholder Tensions' },
  { id: 'missed', label: 'What FDA Missed' },
];

const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]));
const bySlug = (list) => Object.fromEntries(list.map((x) => [x.slug, x]));
export const THEME_BY_ID = byId(THEMES);
export const THEME_BY_SLUG = bySlug(THEMES);
export const STAKEHOLDER_BY_ID = byId(STAKEHOLDERS);
export const STAKEHOLDER_BY_SLUG = bySlug(STAKEHOLDERS);
export const POSITION_BY_ID = byId(POSITIONS);
export const POSITION_BY_SLUG = bySlug(POSITIONS);

export const stakeholderLabel = (id) => (STAKEHOLDER_BY_ID[id] || STAKEHOLDER_BY_ID.other).label;
export const positionLabel = (id) => (POSITION_BY_ID[id] || POSITION_BY_ID.unclear).label;
export const issueLabel = (id) => ISSUES[id] || null;
export const gapLabel = (id) => GAPS[id] || null;
export const responseTypeLabel = (id) => RESPONSE_TYPES[id] || null;
export const disagreementTopicLabel = (id) => DISAGREEMENT_TOPICS[id] || id;
