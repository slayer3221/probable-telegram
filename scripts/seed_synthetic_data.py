#!/usr/bin/env python3
"""Generate the synthetic seed dataset used by the static frontend before
live Regulations.gov ingestion is switched on.

All organizations, submissions and excerpts produced here are fictional.
Public summaries and excerpts are prefixed or labelled accordingly so the
demo cannot be mistaken for real docket content.

Usage:
    python3 scripts/seed_synthetic_data.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.aggregate import build_public_dataset  # noqa: E402
from pipeline.io_utils import ROOT, now_iso, read_json, write_json  # noqa: E402
from pipeline.taxonomies import GAPS, ISSUES, POSITIONS  # noqa: E402

SEED = 20260818
DATA_DIR = ROOT / "data"

# (id, display name, stakeholder type)
POOL = [
    ("c-meridian", "Meridian Medical Systems", "device_manufacturer"),
    ("c-calder", "Calder Diagnostics", "device_manufacturer"),
    ("c-northlight", "Northlight Imaging", "device_manufacturer"),
    ("c-halden", "Halden Surgical Robotics", "device_manufacturer"),
    ("c-ashford", "Ashford Health Network", "health_system_provider"),
    ("c-greatlakes", "Great Lakes Health Alliance", "health_system_provider"),
    ("c-perrin", "Perrin Valley Health", "health_system_provider"),
    ("c-stmarrow", "St. Marrow Regional Medical Center", "health_system_provider"),
    ("c-acci", "American College of Clinical Informatics", "clinician_professional_society"),
    ("c-sacm", "Society for Acute Care Medicine", "clinician_professional_society"),
    ("c-nrpc", "National Radiology Practice Council", "clinician_professional_society"),
    ("c-lumen", "Lumen Clinical AI", "foundation_model_ai_platform"),
    ("c-ravel", "Ravel Foundation Models", "foundation_model_ai_platform"),
    ("c-orbis", "Orbis Language Systems", "foundation_model_ai_platform"),
    ("c-amtc", "Advanced Medical Technology Council", "trade_association"),
    ("c-dhif", "Digital Health Industry Forum", "trade_association"),
    ("c-weston", "Weston Institute for Health Policy", "academic_research"),
    ("c-cces", "Center for Clinical Evaluation Science", "academic_research"),
    ("c-tallis", "Tallis University Biomedical Informatics Lab", "academic_research"),
    ("c-psa", "Patients for Safe Automation", "patient_consumer_group"),
    ("c-crdf", "Coalition of Rare Disease Families", "patient_consumer_group"),
    ("c-bramble", "Bramble Health Ventures", "investor_vc"),
    ("c-kestrel", "Kestrel Growth Partners", "investor_vc"),
    ("c-ind-1", "Individual commenter (clinical pharmacist)", "individual"),
    ("c-ind-2", "Individual commenter (emergency physician)", "individual"),
    ("c-ind-3", "Individual commenter (software engineer)", "individual"),
    ("c-rpc", "Regional Payer Consortium", "other"),
    ("c-sla", "State Licensing Alliance", "other"),
]

# Curated demonstration positions, adapted from the design prototype.
# Fields: commenter id, question numbers, position, summary, concern, want,
# primary issue, secondary issue, gap tags, excerpt, featured
CURATED = [
    # Q1 (two-axis risk framework)
    ("c-amtc", [1], "support_with_modification",
     "Supports a risk-based frame but argues variability alone is not a risk driver; risk should be tied to the clinical action the output can trigger.",
     "A variability-first definition would sweep in low-consequence informational features.",
     "Anchor risk to the consequence of acting on the output, not to whether the output is deterministic.",
     "risk_classification", "intended_use", [],
     "Variability in phrasing is not the hazard. The hazard is the clinical action a user is likely to take, and that should remain the organizing principle.", True),
    ("c-ashford", [5], "mixed",
     "Agrees risk should be action-linked, but notes that in practice the same tool moves between informational and directive use inside one conversation.",
     "Risk assessed at clearance may not describe how the tool behaves at the bedside.",
     "Require manufacturers to state the behavioral envelope and what happens when a session drifts outside it.",
     "intended_use", "directiveness", ["dynamic_intended_use"],
     "In our pilot the same assistant summarized, then recommended, then produced an order draft, all in one exchange.", True),
    ("c-weston", [1], "support_with_modification",
     "Supports distributional risk characterization: performance described as a distribution over responses rather than a point estimate.",
     "Point estimates hide tail behavior that matters clinically.",
     "Expect reporting of worst-case and tail performance, not only central tendency.",
     "statistical_methods", "risk_classification", [],
     "A mean accuracy figure tells a regulator very little about the responses that would actually cause harm.", False),
    ("c-psa", [3, 2], "support_with_modification",
     "Supports action-linked risk but asks that patient-facing outputs be treated as directive by default, since patients cannot always tell information from advice.",
     "Patients experience informational output as a recommendation.",
     "Treat patient-facing output as directive unless the sponsor shows otherwise.",
     "directiveness", "intended_use", ["dynamic_intended_use"],
     "A patient reading a confident paragraph does not see an informational feature. They see an instruction.", False),
    ("c-orbis", [1], "support",
     "Supports the two-axis framing and says independence of action is the right first axis for generative functions.",
     "Sponsors need a shared vocabulary for autonomy levels.",
     "Adopt the independence axis with defined levels that sponsors can cite in labeling.",
     "risk_classification", "agentic_autonomy", [],
     "A shared scale for how independently a function acts would remove most of the ambiguity we see in early submissions.", False),

    # Q8 (level of evidence by risk)
    ("c-meridian", [8], "support_with_modification",
     "Supports tiered evidence and asks FDA to publish worked examples so sponsors can predict the bar before starting studies.",
     "Uncertainty about the bar delays programs more than the bar itself.",
     "Publish illustrative evidence packages for two or three representative device types.",
     "evidence_standards", "economics_burden", ["evidence_burden_commercial_viability"],
     "We can build to a demanding standard. We cannot build to an unstated one.", True),
    ("c-sacm", [8, 11], "support_with_modification",
     "Supports tiering but argues any tool that reaches a clinical decision should require prospective evidence in a care setting.",
     "Retrospective benchmark performance has repeatedly failed to hold up in live workflow.",
     "Require at least one prospective evaluation in the intended setting for decision-supporting tools.",
     "clinical_validation", "evidence_standards", ["human_ai_system_performance"],
     "Benchmark performance and bedside performance have not matched in any deployment we have reviewed.", True),
    ("c-dhif", [8, 11], "oppose",
     "Opposes a fixed prospective requirement, arguing it would make lower-risk documentation tools economically unviable.",
     "A uniform prospective study requirement is disproportionate at the low end.",
     "Keep prospective evidence tied to the highest tier only.",
     "economics_burden", "evidence_standards", ["evidence_burden_commercial_viability", "operational_harm"],
     "A prospective study for a discharge summary drafting aid costs more than the product will ever return.", True),
    ("c-cces", [9, 8], "support",
     "Supports the tiered approach as drafted and asks FDA to specify reporting standards rather than study designs.",
     "Inconsistent reporting makes submissions hard to compare.",
     "Define a minimum reporting set: population, prompts, failure modes, and human involvement.",
     "benchmarking", "evidence_standards", [],
     "Comparability is the missing ingredient. Standardize the reporting, not the design.", False),
    ("c-bramble", [8, 18], "support_with_modification",
     "Supports proportional evidence and warns that an unstated bar is priced into every financing as regulatory risk.",
     "Investors cannot underwrite an evidence requirement that is not written down.",
     "State the evidence floor per tier so capital can be sized to it.",
     "economics_burden", "evidence_standards", ["evidence_burden_commercial_viability"],
     "Every unstated requirement shows up in our models as a discount on the round.", False),
    ("c-lumen", [8, 11], "support_with_modification",
     "Supports competency-based evaluation and asks that non-clinical benchmarking be allowed to carry more weight for lower-consequence functions.",
     "Clinical confirmation for every function would slow iteration without adding safety.",
     "Let benchmarking substitute for clinical confirmation where consequence of error is limited.",
     "benchmarking", "clinical_validation", ["evidence_burden_commercial_viability"],
     "For a low-consequence function, a rigorous benchmark tells you more than a small clinical study does.", False),

    # Q9 (benchmarking structure: safety behavior)
    ("c-northlight", [9], "support_with_modification",
     "Supports adversarial testing expectations and asks that retrieval poisoning and prompt injection be treated as clinical hazards, not IT controls.",
     "Security testing is currently reviewed separately from clinical risk.",
     "Fold adversarial evaluation into the device risk analysis rather than cybersecurity documentation alone.",
     "cybersecurity", "risk_classification", ["cybersecurity_as_safety"],
     "A retrieval poisoning event is not an IT incident. It is a clinical one.", True),
    ("c-tallis", [9], "support",
     "Supports red-teaming requirements and proposes that sponsors report attack categories tested and the residual failure rate.",
     "Unstructured red-teaming produces unverifiable claims.",
     "Require a reported adversarial test matrix with residual failure rates.",
     "cybersecurity", "benchmarking", ["cybersecurity_as_safety"],
     "Red-teaming without a reported matrix is an anecdote, not evidence.", False),
    ("c-stmarrow", [9, 19], "mixed",
     "Supports adversarial testing but notes that site-specific retrieval content is where most injection risk lives, which premarket testing cannot see.",
     "The attack surface is assembled at the site, not by the sponsor.",
     "Define what sites must test locally when they connect their own content.",
     "cybersecurity", "health_system_implementation", ["cybersecurity_as_safety", "deployment_assurance_scalability"],
     "The documents that poisoned our pilot were our own. No sponsor could have tested against them.", False),

    # Q14 (human-AI team performance)
    ("c-acci", [14], "support",
     "Supports explicit human-AI team evaluation and cites automation bias as the dominant failure mode observed in practice.",
     "Model-only metrics say nothing about whether a clinician will catch an error.",
     "Require evaluation of the combined human-AI system, including override rates.",
     "human_factors", "clinical_validation", ["human_ai_system_performance"],
     "The question is not whether the model is right. It is whether a tired clinician at hour ten will notice when it is not.", True),
    ("c-northlight", [14], "support_with_modification",
     "Agrees in principle but says sponsors cannot control the human half, which varies by site, staffing, and training.",
     "Manufacturers would be held to outcomes determined by local practice.",
     "Scope team evaluation to representative conditions and hold sites responsible for training fidelity.",
     "human_factors", "accountability_liability", ["human_ai_system_performance", "distributed_accountability"],
     "We can characterize the tool under representative use. We cannot warrant a staffing model.", False),
    ("c-psa", [14], "mixed",
     "Supports team-level evaluation but questions whether override rate is a safety measure or a compliance measure.",
     "High override rates could be read as safety when they reflect distrust.",
     "Pair override metrics with outcome measures before treating them as evidence of oversight.",
     "human_factors", "evidence_standards", ["human_ai_system_performance"],
     "An override number without an outcome behind it tells a patient nothing.", False),
    ("c-cces", [14, 11], "support_with_modification",
     "Supports human-AI evaluation and asks that study designs specify who the human is, since results do not transfer between specialist and generalist users.",
     "Results from expert evaluators overstate real-world performance.",
     "Require the evaluated user population to match the labeled user population.",
     "human_factors", "clinical_validation", ["human_ai_system_performance"],
     "A study run with subspecialists tells you nothing about the nurse practitioner who will actually use it.", False),
    ("c-ind-2", [14, 4], "support",
     "Supports team-level evaluation from the perspective of a practicing emergency physician and describes reliance creeping in over weeks of use.",
     "Vigilance decays with familiarity in ways short studies do not capture.",
     "Evaluate oversight behavior over sustained use, not a single session.",
     "human_factors", "postmarket_monitoring", ["human_ai_system_performance"],
     "In week one I checked everything. By week six I was signing drafts I had skimmed.", False),

    # Q21 (stakeholder roles in monitoring)
    ("c-amtc", [21], "support_with_modification",
     "Supports a monitoring obligation on manufacturers but wants a scalable framework rather than site-by-site surveillance.",
     "Per-site monitoring does not scale across thousands of deployments.",
     "Define a sampling-based framework with defined data feeds from sites.",
     "postmarket_monitoring", "economics_burden", ["deployment_assurance_scalability"],
     "Site-by-site surveillance of every deployment is not a program. It is a headcount problem with no ceiling.", True),
    ("c-greatlakes", [21], "mixed",
     "Supports monitoring and resists becoming the unpaid operator of manufacturer surveillance obligations.",
     "Data extraction and review burden lands on the health system without funding.",
     "Specify what sites must provide and what manufacturers must fund or build.",
     "health_system_implementation", "economics_burden", ["operational_harm", "distributed_accountability"],
     "We are willing to monitor. We are not willing to staff someone else's compliance program.", True),
    ("c-lumen", [21], "support",
     "Supports manufacturer-led monitoring and offers telemetry as the mechanism, provided privacy constraints are addressed.",
     "Without a data pathway, monitoring obligations are unmeetable.",
     "Clarify that de-identified performance telemetry is permissible for safety monitoring.",
     "postmarket_monitoring", "health_system_implementation", [],
     "The obligation is workable only if the data pathway is explicitly permitted.", False),
    ("c-perrin", [21], "support_with_modification",
     "Supports shared monitoring with a named accountable party per deployment.",
     "Diffuse responsibility means no one holds the signal.",
     "Require a named monitoring owner recorded at deployment.",
     "accountability_liability", "postmarket_monitoring", ["distributed_accountability"],
     "Every deployment should have a name attached to it before go-live.", True),
    ("c-nrpc", [21, 19], "support_with_modification",
     "Supports monitoring and asks that clinician review time be counted as a cost of the program rather than assumed to be free.",
     "Sample-based clinician review is unfunded labor.",
     "Recognize clinician adjudication as a funded monitoring activity.",
     "economics_burden", "postmarket_monitoring", ["operational_harm", "distributed_accountability"],
     "Sample-based review by independent clinicians is a good idea with no line item.", False),
    ("c-rpc", [21, 18], "unclear",
     "Raises questions about whether payers would be expected to supply utilization data for monitoring without stating a position on the allocation.",
     "Monitoring data may be expected from parties the paper does not name.",
     "Clarify whether payer data is in scope for monitoring programs.",
     "postmarket_monitoring", "accountability_liability", ["distributed_accountability"],
     "We note that the data most useful for detecting over-utilization sits with payers, who are not mentioned.", False),
    ("c-kestrel", [21], "support_with_modification",
     "Supports monitoring and asks FDA to say whether the obligation is a cost of the manufacturer or a cost of the deployment.",
     "Unallocated obligations are unpriceable.",
     "Allocate monitoring cost explicitly in any framework.",
     "economics_burden", "accountability_liability", ["evidence_burden_commercial_viability", "distributed_accountability"],
     "An obligation no one is assigned is an obligation no one will fund.", False),

    # Q22 (re-evaluating modifications)
    ("c-calder", [22, 24], "support_with_modification",
     "Supports re-evaluating modifications against the premarket baseline but says the construct does not fit changes the sponsor did not initiate.",
     "Upstream base-model updates fall outside the sponsor's change schedule.",
     "Extend change control to cover supplier-initiated changes with a defined re-verification trigger.",
     "change_control", "foundation_model_dependency", ["ai_supplier_quality"],
     "We can plan our own releases. The base model changed twice during our submission review.", True),
    ("c-ravel", [22, 24], "mixed",
     "Neutral on the regulatory construct; notes that model deprecation timelines are commercially driven and short.",
     "Deprecation schedules may be shorter than re-verification cycles.",
     "Recognize supplier change notice periods in any re-verification requirement.",
     "foundation_model_dependency", "change_control", ["ai_supplier_quality"],
     "A ninety-day deprecation notice is standard commercially and may be short for a regulated re-verification.", False),
    ("c-ashford", [22, 19], "support_with_modification",
     "Supports change control and asks that sites be notified of behavior-changing updates before they take effect.",
     "Sites learn about changed behavior from clinicians, not from release notes.",
     "Require advance notice to deployed sites for changes that alter output behavior.",
     "change_control", "health_system_implementation", ["deployment_assurance_scalability"],
     "The first signal we received was a nurse saying the summaries had started sounding different.", True),
    ("c-halden", [22, 23], "support_with_modification",
     "Supports PCCPs for generative products and asks that prompt and retrieval-content changes be treated as modifications with defined verification.",
     "Non-model changes alter behavior as much as model changes.",
     "Define prompt, retrieval and tool-access changes as PCCP-eligible modifications.",
     "pccp", "change_control", [],
     "Half of our behavior changes last year were prompt edits. None of them touched the model.", False),

    # Q19 (postmarket evaluation approaches: local assurance)
    ("c-perrin", [19], "support",
     "Supports explicit deployment-level assurance expectations and reports material behavior differences between two of its own hospitals.",
     "Clearance describes a configuration few sites actually run.",
     "Define a minimum local validation step at go-live and after configuration changes.",
     "health_system_implementation", "evidence_standards", ["deployment_assurance_scalability"],
     "Same product, same version, two hospitals, materially different output quality.", True),
    ("c-meridian", [19], "mixed",
     "Accepts that configuration matters but resists responsibility for site choices made after delivery.",
     "Sponsors cannot validate every local configuration.",
     "Publish supported configuration ranges; treat deviations as site responsibility.",
     "accountability_liability", "health_system_implementation", ["deployment_assurance_scalability", "distributed_accountability"],
     "We can define the supported envelope. We cannot test every combination a site will assemble.", False),
    ("c-weston", [19], "support_with_modification",
     "Supports local assurance and warns that no current mechanism captures site-level performance data.",
     "There is no infrastructure to observe deployment-level performance.",
     "Fund or specify a mechanism for site-level performance reporting.",
     "postmarket_monitoring", "health_system_implementation", ["deployment_assurance_scalability"],
     "Deployment is where performance is decided and where nobody is currently measuring.", True),
    ("c-greatlakes", [19, 21], "support_with_modification",
     "Supports deployment assurance and asks for a template sites can run without a research team.",
     "Local validation is only realistic if it is scoped to what a community hospital can execute.",
     "Publish a minimum local validation protocol proportionate to site resources.",
     "health_system_implementation", "economics_burden", ["deployment_assurance_scalability", "operational_harm"],
     "A validation protocol that needs a biostatistician excludes most of the hospitals in this country.", False),
    ("c-ind-1", [19], "support",
     "Supports local validation from the perspective of a clinical pharmacist who found formulary-specific errors after go-live.",
     "Errors tied to local formularies are invisible in premarket testing.",
     "Require sites to test against their own reference content before go-live.",
     "health_system_implementation", "clinical_validation", ["deployment_assurance_scalability"],
     "The model recommended a drug we do not stock, in a dose our protocol does not allow.", False),

    # Q24 (third-party foundation model changes)
    ("c-dhif", [24], "support_with_modification",
     "Supports treating foundation model providers as suppliers under existing quality system expectations.",
     "Current supplier controls assume component stability.",
     "Adapt supplier qualification to cover model versioning and change notification.",
     "supplier_controls", "foundation_model_dependency", ["ai_supplier_quality"],
     "The supplier control framework already exists. It was written for parts that do not change themselves.", True),
    ("c-ravel", [24, 25], "mixed",
     "Open to change-notification commitments; cautions that full transparency into training data is not commercially feasible.",
     "Disclosure obligations may exceed what suppliers can provide.",
     "Distinguish behavior-change notification from training data disclosure.",
     "foundation_model_dependency", "supplier_controls", ["ai_supplier_quality"],
     "We can commit to telling customers when behavior changes. We cannot open the training corpus.", True),
    ("c-calder", [24], "support",
     "Supports formal supplier obligations and reports difficulty obtaining change notice today.",
     "Sponsors carry regulatory liability without contractual visibility.",
     "Require documented change notification as a condition of reliance.",
     "supplier_controls", "accountability_liability", ["ai_supplier_quality", "distributed_accountability"],
     "The liability sits with us and the visibility sits with them.", True),
    ("c-orbis", [25], "support_with_modification",
     "Supports voluntary Foundation Model Master Files and says they will only be maintained if FDA staff actually rely on them.",
     "A master file nobody reads will not be kept current.",
     "Specify how a master file would be used in review so suppliers have a reason to maintain it.",
     "foundation_model_dependency", "supplier_controls", ["ai_supplier_quality"],
     "We will keep a master file current if it shortens our customers' reviews. Otherwise it is a document that rots.", False),
    ("c-kestrel", [24, 22], "support_with_modification",
     "Supports supplier obligations and notes that model dependency is now a diligence item in every financing.",
     "Unmanaged supplier risk is unpriceable at the portfolio level.",
     "Require sponsors to document supplier change terms in submissions.",
     "supplier_controls", "economics_burden", ["ai_supplier_quality"],
     "We now ask every company which model they depend on and what happens when it is deprecated.", False),

    # Q26
    ("c-sacm", [26], "support_with_modification",
     "Supports a distinct treatment for action-taking systems and asks for defined intervention points.",
     "An error that executes is different from an error that is displayed.",
     "Require a documented intervention point before any clinically consequential action executes.",
     "agentic_autonomy", "human_factors", ["delegated_authority"],
     "A wrong sentence is a draft. A wrong action is an event.", True),
    ("c-lumen", [26], "support",
     "Supports action-scoped evaluation and proposes describing permitted actions explicitly in labeling.",
     "Ambiguous action scope leads to inconsistent site configuration.",
     "Require an explicit action inventory in labeling.",
     "agentic_autonomy", "intended_use", ["delegated_authority", "dynamic_intended_use"],
     "Say what the system is allowed to do, in a list, in the labeling.", False),
    ("c-greatlakes", [26], "mixed",
     "Supports the direction; notes that delegation decisions are made locally and often informally.",
     "Sites enable capabilities without a formal delegation decision.",
     "Require sites to record what authority has been delegated and to whom errors escalate.",
     "agentic_autonomy", "accountability_liability", ["delegated_authority", "distributed_accountability"],
     "Nobody in our organization signed a document saying the assistant could do that.", True),
    ("c-halden", [26], "support_with_modification",
     "Supports agentic competency testing and asks that irreversible actions be defined by the sponsor rather than by FDA.",
     "A single list of irreversible actions will not fit every clinical setting.",
     "Let sponsors define irreversible actions in labeling and test checkpoints against that list.",
     "agentic_autonomy", "risk_classification", ["delegated_authority"],
     "What is irreversible in an operating room is not what is irreversible in a scheduling queue.", False),
    ("c-crdf", [26, 4], "support_with_modification",
     "Supports human checkpoints and asks that patients be told when an agent, rather than a clinician, initiated an action affecting their care.",
     "Patients cannot contest an action they do not know was automated.",
     "Require disclosure to patients when an agentic system initiated a care action.",
     "agentic_autonomy", "directiveness", ["delegated_authority"],
     "Our families want to know whether a person or a program sent the refill.", False),
    ("c-ind-3", [26, 12], "oppose",
     "Opposes allowing autonomous action in regulated devices until tool-use failure modes are better characterized.",
     "Tool errors compound across steps in ways single-output testing does not capture.",
     "Defer clearance of fully autonomous action until multi-step failure evaluation methods exist.",
     "agentic_autonomy", "cybersecurity", ["delegated_authority", "cybersecurity_as_safety"],
     "A chain of five ninety-five-percent steps is a seventy-seven-percent system.", False),
]

# Generic templates for questions without curated positions.
GENERIC = {
    "support": ("Supports the direction FDA describes for {topic} and asks for clarification on how it would apply to its members' products.",
                "Sees the current framing as workable but underspecified.",
                "Clarify expectations and publish worked examples before finalizing guidance."),
    "support_with_modification": ("Accepts the general direction on {topic} but requests a substantive change to how the expectation would be applied.",
                                  "The proposal as framed may not fit the commenter's use cases.",
                                  "Narrow the expectation to the situations where it adds safety."),
    "oppose": ("Opposes the approach FDA describes for {topic} and argues it would not improve safety in the commenter's setting.",
               "The proposal may add burden without a corresponding safety benefit.",
               "Withdraw or substantially rethink the approach before guidance."),
    "mixed": ("Supports some elements of FDA's framing on {topic} and rejects others, with the split depending on device risk.",
              "One framing cannot fit both low- and high-consequence functions.",
              "Split the expectation by risk tier."),
    "unclear": ("Discusses {topic} at length without stating a clear recommendation FDA could act on.",
                "Raises open questions rather than a position.",
                "No specific request is made."),
}
ISSUE_BY_QUESTION = {
    2: ("directiveness", "intended_use"), 3: ("directiveness", "human_factors"),
    4: ("human_factors", "risk_classification"), 5: ("intended_use", "directiveness"),
    6: ("risk_classification", "clinical_validation"), 7: ("evidence_standards", "benchmarking"),
    10: ("benchmarking", "evidence_standards"), 11: ("clinical_validation", "evidence_standards"),
    12: ("statistical_methods", "synthetic_data"), 13: ("synthetic_data", "statistical_methods"),
    15: ("comparator_standard_of_care", "clinical_validation"), 16: ("evidence_standards", "regulatory_scope"),
    17: ("regulatory_scope", "benchmarking"), 18: ("postmarket_monitoring", "evidence_standards"),
    20: ("postmarket_monitoring", "agentic_autonomy"), 23: ("pccp", "change_control"),
    25: ("foundation_model_dependency", "supplier_controls"),
}
GAP_BY_QUESTION = {
    2: ["dynamic_intended_use"], 3: ["dynamic_intended_use"], 4: ["human_ai_system_performance"],
    5: ["dynamic_intended_use"], 6: ["operational_harm"], 10: ["evidence_burden_commercial_viability"],
    15: ["human_ai_system_performance"], 16: ["evidence_burden_commercial_viability"],
    18: ["evidence_burden_commercial_viability", "operational_harm"], 20: ["delegated_authority"],
    23: ["ai_supplier_quality"], 25: ["ai_supplier_quality"],
}


def main():
    rng = random.Random(SEED)
    questions = read_json(DATA_DIR / "questions.json")["questions"]
    q_by_n = {q["question_number"]: q for q in questions}
    editorial_gaps = read_json(ROOT / "editorial" / "gaps.json")["gaps"]
    editorial_cards = read_json(ROOT / "editorial" / "signals.json")["cards"]

    commenters = [{
        "id": cid, "display_name": name, "organization": "" if stype == "individual" else name,
        "stakeholder_type": stype,
        "source_identity_text": f"[Synthetic] Self-identified in the demo submission as {name}.",
    } for cid, name, stype in POOL]

    # One submission per commenter, so multiple positions never inflate commenter counts.
    submissions = {}
    for idx, (cid, name, _) in enumerate(POOL, start=1):
        rg_id = f"FDA-2026-N-7874-DEMO-{idx:04d}"
        day = 20 + (idx % 9)
        submissions[cid] = {
            "id": f"s-{cid[2:]}",
            "regulations_gov_comment_id": rg_id,
            "commenter_id": cid,
            "received_date": f"2026-08-{day:02d}",
            "posted_date": f"2026-08-{min(day + 1, 31):02d}",
            "comment_body": "[Synthetic demo submission body]",
            "attachment_urls": ["https://example.invalid/synthetic-attachment.pdf"] if idx % 2 == 0 else [],
            "extracted_attachment_text": "",
            "source_url": f"https://www.regulations.gov/comment/{rg_id}",
            "raw_text": "[Synthetic demo submission text]",
            "ingestion_timestamp": "2026-09-01T00:00:00Z",
        }

    positions = []
    counter = 0

    def add(cid, qnums, position, summary, concern, want, primary, secondary, gaps, excerpt, featured):
        nonlocal counter
        counter += 1
        positions.append({
            "id": f"p-{counter:04d}",
            "submission_id": submissions[cid]["id"],
            "question_ids": [f"q{n}" for n in qnums],
            "position": position,
            "primary_issue": primary,
            "secondary_issue": secondary,
            "stakeholder_concern": concern,
            "requested_fda_action": want,
            "public_summary": summary,
            "supporting_text": excerpt,
            "model_confidence": "high",
            "gap_tags": gaps,
            "featured": featured,
        })

    for row in CURATED:
        add(*row)

    covered = {n for row in CURATED for n in row[1]}
    curated_pairs = {(row[0], n) for row in CURATED for n in row[1]}
    position_keys = list(POSITIONS)
    for n in range(1, 27):
        target = 5 if n in (18, 20) else (3 if n in covered else 4)
        existing = len({row[0] for row in CURATED if n in row[1]})
        if existing >= target:
            continue
        candidates = [c for c in POOL if (c[0], n) not in curated_pairs]
        rng.shuffle(candidates)
        for cid, name, stype in candidates[: target - existing]:
            pos = rng.choices(position_keys, weights=[3, 5, 1, 2, 1])[0]
            topic = q_by_n[n]["short_title"].lower()
            summary, concern, want = GENERIC[pos]
            primary, secondary = ISSUE_BY_QUESTION.get(n, ("regulatory_scope", None))
            gaps = GAP_BY_QUESTION.get(n, [])
            gaps = gaps if rng.random() < 0.7 else []
            add(cid, [n], pos, summary.format(topic=topic), concern, want, primary, secondary, gaps,
                f"[Synthetic demo excerpt] The submission addresses {topic} directly in its response to Question {n}.", False)

    meta = {
        "generated_at": now_iso(),
        "dataset_kind": "synthetic",
        "processing_version": "seed-1",
        "docket": {
            "docket_id": "FDA-2026-N-7874",
            "docket_url": "https://www.regulations.gov/docket/FDA-2026-N-7874",
            "document_id": "FDA-2026-N-7874-0001",
            "discussion_paper_url": "https://www.fda.gov/media/194242/download",
            "discussion_paper_landing_url": "https://www.fda.gov/medical-devices/digital-health-center-excellence/considerations-regulation-generative-ai-enabled-medical-devices-discussion-paper-and-request",
            "comment_deadline": "2026-10-19",
            "paper_date": "2026-08-18",
        },
    }
    files = build_public_dataset(questions, commenters, list(submissions.values()), positions, editorial_gaps, editorial_cards, meta)
    for name, payload in files.items():
        write_json(DATA_DIR / name, payload)
    s = files["site-summary.json"]["metrics"]
    print(f"seeded: {s['comments_analyzed']} submissions, {s['commenters_represented']} commenters, {s['positions_identified']} positions")
    for card in files["site-summary.json"]["signals"]:
        print(" signal:", card["label"], "->", card["headline"], "|", card["evidence"])


if __name__ == "__main__":
    main()
