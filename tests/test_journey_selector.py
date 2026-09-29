"""Focused regression coverage for the complete Vessel Journey selector population."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from apps.api.core.database import SessionLocal
from apps.api.main import app
from apps.api.models.auth import SessionRecord
from apps.api.models.canonical import VesselCall
from apps.api.services.auth_service import create_user_session


def test_journey_selector_filters_merges_before_pagination_and_keeps_empty_calls_selectable():
    db = SessionLocal()
    client = TestClient(app)
    suffix = uuid4().hex[:10]
    tenant_id = f"journey-selector-{suffix}"
    session_id = None
    try:
        primaries = [
            VesselCall(
                tenant_id=tenant_id,
                vcn=f"SYNDB{index:07d}-{suffix}",
                vessel_name=f"Selector Vessel {index}",
                is_merged=False,
            )
            for index in range(1, 136)
        ]
        merged = [
            VesselCall(
                tenant_id=tenant_id,
                vcn=f"SOURCE{index:07d}-{suffix}",
                vessel_name=f"Merged Source {index}",
                is_merged=True,
            )
            for index in range(1, 106)
        ]
        db.add_all(primaries + merged)
        db.commit()

        auth = create_user_session(
            db=db,
            user_id=f"user-{suffix}",
            email=f"{suffix}@example.test",
            roles=[],
            permissions=["view"],
            data_scope={"tenant_id": tenant_id, "port_id": "*", "terminal_id": "*"},
        )
        session_id = auth["session_id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        selector = client.get("/api/v1/journey/vessel-calls?limit=200", headers=headers)
        assert selector.status_code == 200
        payload = selector.json()
        assert payload["total"] == 135
        assert len(payload["items"]) == 135
        assert all(not item["journey_available"] for item in payload["items"])

        late_vcn = f"SYNDB0000135-{suffix}"
        searched = client.get(
            f"/api/v1/journey/vessel-calls?search={late_vcn}&limit=10", headers=headers
        )
        assert searched.status_code == 200
        assert searched.json()["total"] == 1
        late = searched.json()["items"][0]
        assert late["vcn"] == late_vcn

        journey = client.get(f"/api/v1/journey/{late['id']}", headers=headers)
        assert journey.status_code == 200
        assert journey.json()["status"] == "UNAVAILABLE"
        assert journey.json()["vcn"] == late_vcn
        assert journey.json()["stages"] == []
    finally:
        db.rollback()
        db.execute(delete(VesselCall).where(VesselCall.tenant_id == tenant_id))
        if session_id:
            db.execute(delete(SessionRecord).where(SessionRecord.jti == session_id))
        db.commit()
        db.close()
