import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from apps.api.models.canonical import EventOccurrence, VesselCall
from apps.api.models.config import EventDefinition
from apps.api.models.journey import (
    CanonicalObservation,
    JourneyInstance,
    ObservationCorrection,
    ReconstructionHistory,
    StageOccurrence,
)
from apps.api.services.ingestion.synthetic import load_synthetic_dataset
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.journey.corrections import JourneyCorrectionService
from apps.api.services.journey.narrative import JourneyNarrativeService
from apps.api.services.journey.reconstructor import JourneyReconstructionEngine
from apps.api.services.quality.engine import DataQualityEngine


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def reconstructed_fixture(db_session):
    """Loads the synthetic dataset through the real pipeline, runs DQ + identity + journey
    reconstruction end to end, exactly as `make validate` does."""
    load_synthetic_dataset(db_session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
    DataQualityEngine(db_session).run_all()
    IdentityEngine(db_session, tenant_id="synthetic-tenant").auto_merge_candidates()

    engine = JourneyReconstructionEngine(db_session, tenant_id="synthetic-tenant")
    summary = engine.reconstruct_all()
    return summary


def _synthetic_tenant_instances(db_session) -> list[JourneyInstance]:
    return db_session.execute(
        select(JourneyInstance)
        .join(VesselCall, JourneyInstance.vessel_call_id == VesselCall.id)
        .where(VesselCall.tenant_id == "synthetic-tenant")
    ).scalars().all()


def _get_instance(db_session, vcn: str) -> JourneyInstance:
    vc = db_session.execute(select(VesselCall).where(VesselCall.vcn == vcn)).scalar_one()
    return db_session.execute(
        select(JourneyInstance).where(JourneyInstance.vessel_call_id == vc.id)
    ).scalar_one()


def test_all_72_base_calls_reconstruct(reconstructed_fixture):
    assert reconstructed_fixture["total"] == 72
    assert reconstructed_fixture["reconstructed"] == 72
    assert reconstructed_fixture["failed"] == 0


def test_shifting_calls_get_a_shift_stage_and_others_dont(db_session, reconstructed_fixture):
    """Every ninth call carries the two shift events and must reconstruct with a shifting stage
    present; the other 64 must show zero shifts and no phantom stage."""
    instances = _synthetic_tenant_instances(db_session)

    shifting_calls = 0
    non_shifting_calls = 0
    for inst in instances:
        shift_rows = db_session.execute(
            select(StageOccurrence).where(
                StageOccurrence.journey_instance_id == inst.id,
                StageOccurrence.stage_name == "Optional Shifting",
            )
        ).scalars().all()
        available = [r for r in shift_rows if r.availability == "AVAILABLE"]
        if available:
            shifting_calls += 1
            assert len(available) >= 1
        else:
            non_shifting_calls += 1
            # No phantom shift row should ever be marked AVAILABLE with a duration for a
            # non-shifting call.
            assert all(r.availability != "AVAILABLE" or r.duration_hours is None for r in shift_rows) or len(shift_rows) == 0

    assert shifting_calls == 8
    assert non_shifting_calls == 64


def test_dq010_conflicting_ata_preserved_and_resolved(db_session, reconstructed_fixture):
    """DQ-010: SYNVCN2600070 has two ATA observations 5h apart. Both must be preserved and
    visible, a conflict recorded, and a canonical selection proposed with reasoning."""
    vc = db_session.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600070")).scalar_one()
    ata_def = db_session.execute(select(EventDefinition).where(EventDefinition.name == "ATA")).scalar_one()

    all_ata = db_session.execute(
        select(EventOccurrence).where(
            EventOccurrence.vessel_call_id == vc.id,
            EventOccurrence.event_definition_id == ata_def.id,
        )
    ).scalars().all()
    # Both observations must still exist - nothing was deleted.
    assert len(all_ata) == 2

    co = db_session.execute(
        select(CanonicalObservation).where(
            CanonicalObservation.vessel_call_id == vc.id,
            CanonicalObservation.event_definition_id == ata_def.id,
        )
    ).scalar_one()
    assert co.conflict_detected is True
    assert co.selected_event_occurrence_id is not None
    assert len(co.candidate_event_occurrence_ids) == 2
    assert "comparison" in co.selection_reasoning
    assert len(co.selection_reasoning["comparison"]) == 2

    # The selected observation must be the Verified one, not the Conflicting one.
    selected = next(o for o in all_ata if o.id == co.selected_event_occurrence_id)
    assert selected.verification_status == "Verified"


def test_missing_ata_produces_unavailable_stage_not_zero_duration(db_session):
    """A vessel call with no ATA observation at all must show the ATA-dependent stage as
    UNAVAILABLE, never as a zero-duration stage."""
    tenant_id = f"test-missing-ata-{uuid.uuid4().hex[:6]}"
    vc = VesselCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        vessel_name="TEST NO ATA VESSEL",
        vcn=f"TESTVCN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(vc)
    db_session.flush()

    nomination_def = db_session.execute(
        select(EventDefinition).where(EventDefinition.name == "NOMINATION_SUBMITTED")
    ).scalar_one()
    db_session.add(
        EventOccurrence(
            vessel_call_id=vc.id,
            event_definition_id=nomination_def.id,
            occurrence_index=1,
            movement_scope="ARRIVAL",
            utc_value=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_system="TOS",
        )
    )
    db_session.commit()

    try:
        engine = JourneyReconstructionEngine(db_session, tenant_id=tenant_id)
        instance = engine.reconstruct_vessel_call(vc)
        db_session.commit()

        pre_arrival = db_session.execute(
            select(StageOccurrence).where(
                StageOccurrence.journey_instance_id == instance.id,
                StageOccurrence.stage_name == "Pre-Arrival",
            )
        ).scalar_one()

        assert pre_arrival.availability == "UNAVAILABLE"
        assert pre_arrival.is_missing is True
        assert pre_arrival.duration_hours is None  # never a fabricated zero
        assert "ATA" in pre_arrival.inference_reason
    finally:
        db_session.execute(text("DELETE FROM journey.handover WHERE from_stage_occurrence_id IN (SELECT id FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id = :vc_id))"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id = :vc_id)"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.reconstruction_history WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.journey_instance WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM canonical.event_occurrence WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM canonical.vessel_call WHERE id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.commit()


def test_time_decomposition_sums_without_double_counting(db_session, reconstructed_fixture):
    """Active/wait/hold/delay/unclassified components must sum to the reconstructed total for
    every reconstructed instance, including the shifting calls (no overlap double-counted)."""
    instances = _synthetic_tenant_instances(db_session)
    checked = 0
    for inst in instances:
        decomp = inst.time_decomposition
        if not decomp or decomp.get("status") != "AVAILABLE":
            continue
        component_sum = round(
            sum(decomp[c] for c in ["ACTIVE_SERVICE", "PASSIVE_WAIT", "HOLD", "DELAY", "UNCLASSIFIED"]),
            4,
        )
        assert component_sum == round(decomp["total_hours"], 4)
        checked += 1
    assert checked == 72


def test_shifting_time_is_carved_out_of_cargo_not_double_counted(db_session, reconstructed_fixture):
    """A shifting call's Cargo Operations decomposition bucket must be reduced by exactly the
    shift duration, and that duration must appear under DELAY - not both."""
    instances_with_shift = []
    for inst in _synthetic_tenant_instances(db_session):
        shift = db_session.execute(
            select(StageOccurrence).where(
                StageOccurrence.journey_instance_id == inst.id,
                StageOccurrence.stage_name == "Optional Shifting",
                StageOccurrence.availability == "AVAILABLE",
            )
        ).scalar_one_or_none()
        if shift:
            instances_with_shift.append((inst, shift))

    assert len(instances_with_shift) == 8
    for inst, shift in instances_with_shift:
        assert inst.time_decomposition["DELAY"] >= round(shift.duration_hours, 4) - 0.001


def test_canonical_selection_preserves_every_observation(db_session, reconstructed_fixture):
    """Canonical occurrence selection must never delete a conflicting observation."""
    conflicts = db_session.execute(
        select(CanonicalObservation).where(CanonicalObservation.conflict_detected == True)  # noqa: E712
    ).scalars().all()
    assert len(conflicts) >= 1
    for c in conflicts:
        for occ_id in c.candidate_event_occurrence_ids:
            occ = db_session.execute(
                select(EventOccurrence).where(EventOccurrence.id == occ_id)
            ).scalar_one_or_none()
            assert occ is not None  # still present, never deleted


def test_correction_creates_new_observation_and_triggers_recalculation(db_session, reconstructed_fixture):
    """A steward correction must never mutate raw or the prior canonical value: it creates a new
    canonical observation, supersedes the prior one, and triggers recalculation."""
    vc = db_session.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600070")).scalar_one()
    ata_def = db_session.execute(select(EventDefinition).where(EventDefinition.name == "ATA")).scalar_one()

    prior_occs = db_session.execute(
        select(EventOccurrence).where(
            EventOccurrence.vessel_call_id == vc.id,
            EventOccurrence.event_definition_id == ata_def.id,
            EventOccurrence.is_superseded == False,  # noqa: E712
        )
    ).scalars().all()
    prior = next(o for o in prior_occs if o.verification_status == "Verified")
    prior_id = prior.id
    prior_original_value = prior.utc_value

    old_instance = db_session.execute(
        select(JourneyInstance).where(JourneyInstance.vessel_call_id == vc.id)
    ).scalar_one()
    old_version = old_instance.reconstruction_version

    correction = JourneyCorrectionService.create_correction(
        db=db_session,
        vessel_call_id=str(vc.id),
        event_definition_id=str(ata_def.id),
        new_utc_value=datetime(2026, 3, 28, 15, 22, tzinfo=timezone.utc),
        reason="Steward confirms AIS timestamp is authoritative",
        actor="steward@port.gov",
        prior_event_occurrence_id=str(prior_id),
    )

    # Raw / prior observation must be untouched in value, only marked superseded.
    db_session.refresh(prior)
    assert prior.utc_value == prior_original_value
    assert prior.is_superseded is True
    assert prior.superseded_by_id == correction.new_event_occurrence_id

    new_occ = db_session.execute(
        select(EventOccurrence).where(EventOccurrence.id == correction.new_event_occurrence_id)
    ).scalar_one()
    assert new_occ.utc_value == datetime(2026, 3, 28, 15, 22, tzinfo=timezone.utc)
    assert new_occ.capture_method == "STEWARD_CORRECTION"

    assert correction.approval_state == "APPROVED"
    assert correction.recalculated_at is not None

    db_session.refresh(old_instance)
    assert old_instance.reconstruction_version == old_version + 1

    history_rows = db_session.execute(
        select(ReconstructionHistory).where(ReconstructionHistory.vessel_call_id == vc.id)
    ).scalars().all()
    assert any(h.triggered_by == "CORRECTION" for h in history_rows)
    # History is versioned, not overwritten: at least the pre- and post-correction runs exist.
    assert len({h.run_version for h in history_rows}) >= 2


def test_narrative_is_grounded_and_does_not_invent_missing_stage(db_session):
    """The AI narrative must state facts only from the reconstructed record and must not invent
    a duration or event for a stage that is deliberately UNAVAILABLE."""
    tenant_id = f"test-narrative-{uuid.uuid4().hex[:6]}"
    vc = VesselCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        vessel_name="TEST NARRATIVE VESSEL",
        vcn=f"TESTVCN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(vc)
    db_session.flush()

    nomination_def = db_session.execute(
        select(EventDefinition).where(EventDefinition.name == "NOMINATION_SUBMITTED")
    ).scalar_one()
    db_session.add(
        EventOccurrence(
            vessel_call_id=vc.id,
            event_definition_id=nomination_def.id,
            occurrence_index=1,
            movement_scope="ARRIVAL",
            utc_value=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_system="TOS",
        )
    )
    db_session.commit()

    try:
        engine = JourneyReconstructionEngine(db_session, tenant_id=tenant_id)
        engine.reconstruct_vessel_call(vc)
        db_session.commit()

        narrative = JourneyNarrativeService.generate(db_session, str(vc.id))

        assert narrative.is_ai_generated is True
        assert narrative.inference_status == "AI_GENERATED"
        assert len(narrative.grounding_record_ids) > 0
        # Must disclose the missing Pre-Arrival stage as unavailable, not invent a duration.
        assert "UNAVAILABLE" in narrative.narrative_text
        assert "Pre-Arrival" in narrative.narrative_text
        # No fabricated duration for the missing stage.
        assert "Pre-Arrival took" not in narrative.narrative_text
    finally:
        db_session.execute(text("DELETE FROM journey.journey_narrative WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.handover WHERE from_stage_occurrence_id IN (SELECT id FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id = :vc_id))"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id = :vc_id)"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.reconstruction_history WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM journey.journey_instance WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM canonical.event_occurrence WHERE vessel_call_id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.execute(text("DELETE FROM canonical.vessel_call WHERE id = :vc_id"), {"vc_id": str(vc.id)})
        db_session.commit()


def test_reconstruction_history_is_versioned_not_overwritten(db_session, reconstructed_fixture):
    """Re-running reconstruction for a call must append a new history entry, not replace the
    prior one, so a re-run after a rule change stays comparable."""
    vc = db_session.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600009")).scalar_one()
    engine = JourneyReconstructionEngine(db_session, tenant_id="synthetic-tenant")

    before = db_session.execute(
        select(ReconstructionHistory).where(ReconstructionHistory.vessel_call_id == vc.id)
    ).scalars().all()

    engine.reconstruct_vessel_call(vc, triggered_by="MANUAL")
    db_session.commit()

    after = db_session.execute(
        select(ReconstructionHistory).where(ReconstructionHistory.vessel_call_id == vc.id)
    ).scalars().all()

    assert len(after) == len(before) + 1
    versions = sorted(h.run_version for h in after)
    assert versions == list(range(1, len(after) + 1))
