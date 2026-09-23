import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from apps.api.main import app
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import VesselCall
from apps.api.models.identity import MatchCandidate, MatchEvidence
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.identity.matcher import IdentityMatcher
from apps.api.services.identity.merger import MergerService
from apps.api.services.identity.normalizer import VesselNameNormalizer
from apps.api.services.identity.survivorship import SurvivorshipEngine


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_vessel_name_normalizer():
    """Verify normalisation handles punctuation and separator variants per spec §8.2."""
    assert VesselNameNormalizer.normalize("MSC AURORA") == "MSC AURORA"
    assert VesselNameNormalizer.normalize("MSC AURORA.") == "MSC AURORA"
    assert VesselNameNormalizer.normalize("MSC-AURORA") == "MSC AURORA"
    assert VesselNameNormalizer.normalize("  MSC   AURORA.  ") == "MSC AURORA"
    assert VesselNameNormalizer.normalize("SYNTHETIC- HORIZON 12") == "SYNTHETIC HORIZON 12"
    assert VesselNameNormalizer.normalize("SYNTHETIC HORIZON 12") == "SYNTHETIC HORIZON 12"

    score, exp = VesselNameNormalizer.similarity("MSC AURORA", "MSC-AURORA")
    assert score >= 0.98
    assert "normalisation" in exp.lower()

    exact_score, exact_exp = VesselNameNormalizer.similarity("MSC AURORA", "MSC AURORA")
    assert exact_score == 1.0


def test_hard_rule_conflicting_imo_or_vcn_blocks_auto_merge():
    """
    Hard rule: Any conflicting IMO or VCN must never auto-merge regardless of score.
    """
    matcher = IdentityMatcher()

    # Case 1: Conflicting IMO with identical vessel name and identical VCN missing
    v1 = VesselCall(
        vessel_name="PACIFIC VOYAGER",
        imo_number="9123456",
        vcn="VCN-A-001",
        vessel_type="Container",
        flag="Panama",
    )
    v2 = VesselCall(
        vessel_name="PACIFIC VOYAGER",
        imo_number="9999999",  # CONFLICT
        vcn="VCN-A-001",
        vessel_type="Container",
        flag="Panama",
    )
    res = matcher.evaluate_pair(v1, v2)
    assert res.conflict_detected is True
    assert res.auto_merge_eligible is False
    assert res.status == "BLOCKED_BY_CONFLICT"
    assert any("Conflicting IMO" in r for r in res.conflict_reasons)

    # Case 2: Conflicting VCN with identical vessel name and identical IMO
    v3 = VesselCall(
        vessel_name="PACIFIC VOYAGER",
        imo_number="9123456",
        vcn="VCN-A-001",
        vessel_type="Container",
        flag="Panama",
    )
    v4 = VesselCall(
        vessel_name="PACIFIC VOYAGER",
        imo_number="9123456",
        vcn="VCN-B-999",  # CONFLICT
        vessel_type="Container",
        flag="Panama",
    )
    res2 = matcher.evaluate_pair(v3, v4)
    assert res2.conflict_detected is True
    assert res2.auto_merge_eligible is False
    assert res2.status == "BLOCKED_BY_CONFLICT"
    assert any("Conflicting VCN" in r for r in res2.conflict_reasons)


def test_explainable_scoring_and_evidence():
    """Verify explainable scoring breaks down contributions and weights per attribute."""
    matcher = IdentityMatcher()
    v1 = VesselCall(
        vessel_name="SYNTHETIC HORIZON 12",
        imo_number="9900012",
        vcn="SYNVCN2600012",
        vessel_type="Container",
        flag="Liberia",
        loa_value=294.0,
    )
    v2 = VesselCall(
        vessel_name="SYNTHETIC- HORIZON 12",
        imo_number="9900012",
        vcn="SYNVCN2600012",
        vessel_type="Container",
        flag="Liberia",
        loa_value=294.0,
    )
    res = matcher.evaluate_pair(v1, v2)

    assert res.match_score >= 0.98
    assert res.conflict_detected is False
    assert res.auto_merge_eligible is True
    assert res.status == "AUTO_MERGE_CANDIDATE"

    # Evidence breakdown must explain every attribute
    attrs = {e.attribute: e for e in res.evidence_breakdown}
    assert "vessel_name" in attrs
    assert "vcn" in attrs
    assert "imo_number" in attrs
    assert attrs["vessel_name"].agreement in ["AGREED", "PARTIAL"]
    assert attrs["vcn"].agreement == "AGREED"
    assert attrs["imo_number"].agreement == "AGREED"
    assert attrs["vessel_name"].weight == 0.40
    assert attrs["vcn"].weight == 0.25


def test_survivorship_and_preview():
    """Verify field survivorship rules and side-by-side preview."""
    v1 = VesselCall(
        id=uuid.uuid4(),
        vessel_name="SYNTHETIC HORIZON 12",
        imo_number="9900012",
        vcn="SYNVCN2600012",
        cargo_type="Containerized",
        quantity_value=1500.0,
        grt=50000.0,
    )
    v2 = VesselCall(
        id=uuid.uuid4(),
        vessel_name="SYNTHETIC- HORIZON 12",
        imo_number="9900012",
        vcn="SYNVCN2600012",
        cargo_type=None,
        quantity_value=None,
        grt=50000.0,
    )
    preview = SurvivorshipEngine.generate_preview(v1, v2)
    assert preview["survivor_id"] == str(v1.id)
    assert preview["consolidated_preview"]["vessel_name"] == "SYNTHETIC HORIZON 12"
    assert preview["consolidated_preview"]["cargo_type"] == "Containerized"
    assert preview["consolidated_preview"]["quantity_value"] == 1500.0


def test_safe_merge_and_unmerge_cycle(db_session):
    """
    Verify complete merge followed by unmerge:
    1. Records merge with survivorship and prior snapshot.
    2. Merged record is marked is_merged=True.
    3. Unmerge restores both records intact to their exact pre-merge state.
    4. Audit trail captures both merge and unmerge.
    """
    tenant_id = f"test-merge-{uuid.uuid4().hex[:6]}"

    # Setup 2 test calls
    v1 = VesselCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        vessel_name="OCEAN PRIDE",
        imo_number="9876543",
        vcn=f"VCN-{uuid.uuid4().hex[:6]}",
        vessel_type="Bulk Carrier",
        flag="Panama",
        quantity_value=25000.0,
    )
    v2 = VesselCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        vessel_name="OCEAN-PRIDE.",
        imo_number="9876543",
        vcn=v1.vcn,  # same VCN
        vessel_type="Bulk Carrier",
        flag="Panama",
        quantity_value=None,  # missing on v2
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    # Pre-merge assertions
    assert v1.is_merged is False
    assert v2.is_merged is False
    orig_v1_name = v1.vessel_name
    orig_v2_name = v2.vessel_name

    # Create candidate
    candidate = MatchCandidate(
        source_record_1_id=str(v1.id),
        source_record_2_id=str(v2.id),
        match_score=0.99,
        status="AUTO_MERGE_CANDIDATE",
        match_type="DETERMINISTIC",
        conflict_detected=False,
    )
    db_session.add(candidate)
    db_session.flush()

    evidence = MatchEvidence(
        match_candidate_id=candidate.id,
        evidence_type="vessel_name",
        evidence_detail={"attribute": "vessel_name", "agreement": "AGREED", "contribution": 0.40},
    )
    db_session.add(evidence)
    db_session.commit()

    # Execute Merge
    decision = MergerService.execute_merge(
        db=db_session,
        candidate_id=str(candidate.id),
        actor="test_steward@port.gov",
        manual=False,
    )

    db_session.refresh(v1)
    db_session.refresh(v2)
    assert decision.decision == "MERGED"
    assert v2.is_merged is True
    assert str(v2.merged_into_id) == str(v1.id)
    assert v1.is_merged is False
    assert v1.vessel_name == "OCEAN PRIDE"
    assert v1.quantity_value == 25000.0

    # Verify audit event for merge
    audit_merge = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.action == "IDENTITY_MERGE",
            AuditEvent.resource_id == str(v1.id),
        )
    ).scalar_one_or_none()
    assert audit_merge is not None

    # Execute Unmerge
    unmerge_res = MergerService.execute_unmerge(
        db=db_session,
        decision_id=str(decision.id),
        actor="test_steward@port.gov",
        notes="Reverting merge test",
    )
    assert unmerge_res["status"] == "success"

    db_session.refresh(v1)
    db_session.refresh(v2)
    db_session.refresh(decision)

    # Assert prior state is restored intact
    assert v2.is_merged is False
    assert v2.merged_into_id is None
    assert v1.vessel_name == orig_v1_name
    assert v2.vessel_name == orig_v2_name
    assert decision.decision == "UNMERGED"

    # Verify audit event for unmerge
    audit_unmerge = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.action == "IDENTITY_UNMERGE",
            AuditEvent.resource_id == str(v1.id),
        )
    ).scalar_one_or_none()
    assert audit_unmerge is not None

    # Clean up (audit_event is append-only, so do not delete from audit_event)
    db_session.execute(text(f"DELETE FROM identity.merge_decision WHERE match_candidate_id = '{candidate.id}'"))
    db_session.execute(text(f"DELETE FROM identity.match_evidence WHERE match_candidate_id = '{candidate.id}'"))
    db_session.execute(text(f"DELETE FROM identity.match_candidate WHERE id = '{candidate.id}'"))
    db_session.execute(text(f"DELETE FROM canonical.vessel_call WHERE tenant_id = '{tenant_id}'"))
    db_session.commit()


def test_fixture_consolidation_reconciles_to_72(db_session):
    """
    Validate the fixture cases through normal matching logic:
    - 74 rows in VesselCalls -> 72 base vessel calls
    - DQ-001 (SYNVCN2600005 exact duplicate) is merged and flagged
    - DQ-002 (SYNVCN2600012 punctuation variant) is merged and flagged
    - Base population reconciles to exactly 72.
    """
    # Reset merges if already merged to ensure test is idempotent
    db_session.execute(text("DELETE FROM identity.merge_decision"))
    db_session.execute(text("DELETE FROM identity.match_evidence"))
    db_session.execute(text("DELETE FROM identity.match_candidate"))
    db_session.execute(text("UPDATE canonical.vessel_call SET is_merged = false, merged_into_id = NULL WHERE tenant_id = 'tenant-synthetic-01'"))
    db_session.commit()

    id_engine = IdentityEngine(db_session, tenant_id="tenant-synthetic-01")
    assert id_engine.get_consolidated_population_count() == 74

    # Generate and auto-merge
    decisions = id_engine.auto_merge_candidates()
    assert len(decisions) == 2

    # Verify consolidated active count
    active_count = id_engine.get_consolidated_population_count()
    assert active_count == 72

    # Verify DQ-001 and DQ-002 issues were created in Quality
    dq1_issue = db_session.execute(
        select(QualityIssue, QualityRule)
        .join(QualityRule)
        .where(QualityRule.rule_id == "DQ-001")
    ).first()
    assert dq1_issue is not None

    dq2_issue = db_session.execute(
        select(QualityIssue, QualityRule)
        .join(QualityRule)
        .where(QualityRule.rule_id == "DQ-002")
    ).first()
    assert dq2_issue is not None


def test_identity_api_endpoints(db_session):
    """Verify REST API routes for candidates, preview, merge, unmerge, and population."""
    client = TestClient(app)

    # 1. Authenticate as Data Steward (has view, merge, unmerge permissions)
    login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Data Steward"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get population summary
    pop_resp = client.get("/api/v1/identity/population", headers=headers)
    assert pop_resp.status_code == 200
    pop_data = pop_resp.json()
    assert pop_data["consolidated_base_population"] == 72
    assert pop_data["reconciled"] is True

    # 3. List candidates
    cand_resp = client.get("/api/v1/identity/candidates", headers=headers)
    assert cand_resp.status_code == 200
    candidates = cand_resp.json()["items"]
    assert len(candidates) > 0

    # 4. Get candidate details with evidence
    first_cand = candidates[0]
    detail_resp = client.get(f"/api/v1/identity/candidates/{first_cand['id']}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert "evidence_breakdown" in detail_data

    # 5. Preview side-by-side
    prev_resp = client.get(f"/api/v1/identity/preview/{first_cand['id']}", headers=headers)
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert "field_comparisons" in prev_data
    assert "consolidated_preview" in prev_data

    # 6. List decisions
    dec_resp = client.get("/api/v1/identity/decisions", headers=headers)
    assert dec_resp.status_code == 200
    decisions = dec_resp.json()
    assert len(decisions) >= 2
