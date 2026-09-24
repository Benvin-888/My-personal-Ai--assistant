from market.limited_live_eligibility import *


def good(**overrides):
    data = dict(
        forward_records=40, forward_pnl_records=30, forward_total_pnl=125.0,
        forward_cost_coverage=True, forward_risk_coverage=True,
        oos_status="OOS_STABILITY", statistical_status="WITHIN_SAMPLE_STABILITY",
        regime_session_status="STABLE", economic_edge_status="EDGE_CANDIDATE",
        operational_readiness=True, evidence_classes=("forward", "oos"),
    )
    data.update(overrides)
    return EligibilityEvidence(**data)


def test_eligible_when_all_gates_pass():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good())
    assert d.status is EligibilityStatus.ELIGIBLE
    assert d.execution_authorized is False


def test_operational_readiness_is_independent_gate():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good(operational_readiness=False))
    assert d.status is EligibilityStatus.OPERATIONALLY_BLOCKED
    assert "operational_readiness_not_confirmed" in d.reasons


def test_missing_cost_or_risk_is_insufficient():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good(forward_cost_coverage=False, forward_risk_coverage=False))
    assert d.status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "forward_cost_coverage_missing" in d.reasons


def test_positive_pnl_is_not_enough_without_research_evidence():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good(oos_status="INSUFFICIENT_DATA", statistical_status="DESCRIPTIVE_STATISTICS"))
    assert d.status is EligibilityStatus.INSUFFICIENT_EVIDENCE


def test_degradation_limit_is_optional_and_enforced_when_configured():
    c=LimitedLiveCriteria(maximum_forward_degradation_ratio=0.5)
    assert assess_limited_live_eligibility(c, good(forward_degradation_ratio=0.4)).status is EligibilityStatus.ELIGIBLE
    assert assess_limited_live_eligibility(c, good(forward_degradation_ratio=0.8)).status is EligibilityStatus.INELIGIBLE


def test_missing_degradation_ratio_when_required_is_insufficient():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(maximum_forward_degradation_ratio=0.5), good())
    assert d.status is EligibilityStatus.INSUFFICIENT_EVIDENCE


def test_invalid_samples_are_rejected():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good(forward_pnl_records=41))
    assert d.status is EligibilityStatus.INVALID_EVIDENCE


def test_fingerprints_are_deterministic_and_change_with_inputs():
    a=assess_limited_live_eligibility(LimitedLiveCriteria(), good())
    b=assess_limited_live_eligibility(LimitedLiveCriteria(), good())
    c=assess_limited_live_eligibility(LimitedLiveCriteria(), good(forward_total_pnl=126.0))
    assert a.assessment_fingerprint == b.assessment_fingerprint
    assert a.evidence_fingerprint != c.evidence_fingerprint
    assert a.assessment_fingerprint != c.assessment_fingerprint


def test_no_execution_authority():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good())
    assert eligibility_is_not_execution_authorization(d)
    assert d.execution_authorized is False


def test_live_evidence_is_not_required_or_merged():
    d=assess_limited_live_eligibility(LimitedLiveCriteria(), good(evidence_classes=("historical", "simulated", "oos", "forward", "live")))
    assert d.status is EligibilityStatus.ELIGIBLE
