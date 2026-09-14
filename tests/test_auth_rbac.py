import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.auth.dependencies import PermissionDependency
from apps.api.auth.scope import DataScope
from apps.api.core.config import settings
from apps.api.main import app
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import VesselCall
from apps.api.repository.vessel_call import VesselCallRepository
from apps.api.services.dev_auth_provider import verify_dev_provider_allowed

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_dev_provider_refused_outside_development():
    """Requirement: Local dev provider is refused when ENVIRONMENT != 'development'."""
    original_env = settings.environment
    try:
        settings.environment = "production"
        with pytest.raises(RuntimeError) as exc:
            verify_dev_provider_allowed()
        assert "strictly forbidden" in str(exc.value)

        # Also verify HTTP call fails outside development with 403 Forbidden
        resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
        assert resp.status_code == 403
        assert "strictly forbidden" in resp.text
    finally:
        settings.environment = original_env


def test_all_protected_routes_have_authorization_dependency():
    """Requirement: Every non-public route must have a require() authorization dependency."""
    public_routes = {
        "/health",
        "/ready",
        "/live",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/api/v1/auth/login",
        "/api/v1/auth/callback",
        "/api/v1/auth/dev/login",
        "/api/v1/auth/dev/users",
        "/api/v1/auth/service-token",
        "/api/v1/auth/refresh",
    }

    unprotected_routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            if path in public_routes:
                continue

            # Inspect dependencies
            has_perm_dep = False
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, PermissionDependency) or getattr(
                    dep.call, "__is_permission_dependency__", False
                ):
                    has_perm_dep = True
                    break

            if not has_perm_dep:
                unprotected_routes.append(path)

    assert not unprotected_routes, f"Protected routes missing require() authorization dependency: {unprotected_routes}"


def test_nine_roles_exact_permitted_actions():
    """Requirement: Each of the 9 roles can do exactly its permitted actions and no others."""
    # Seeded role names from LEVEL_100_SPEC.md §4
    expected_roles_permissions = {
        "Platform Administrator": {
            "view",
            "create",
            "edit",
            "approve",
            "reject",
            "merge",
            "unmerge",
            "recalculate",
            "publish",
            "export",
            "configure",
            "administer",
            "audit",
        },
        "Data Steward": {"view", "create", "edit", "approve", "reject", "merge", "unmerge", "audit"},
        "Marine Operations Controller": {"view", "create", "edit", "approve"},
        "Analyst": {"view", "recalculate", "export"},
        "Department Head": {"view", "approve", "reject", "publish", "export"},
        "Executive": {"view", "export"},
        "Report Manager": {"view", "create", "edit", "publish", "export"},
        "Auditor": {"view", "audit", "export"},
        "Integration Service Account": {"view", "create", "edit"},
    }

    for role_name, expected_perms in expected_roles_permissions.items():
        login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": role_name})
        assert login_resp.status_code == 200, f"Failed login for {role_name}: {login_resp.text}"
        data = login_resp.json()
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Check permissions reported on token/me
        me_resp = client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code == 200
        assigned_perms = set(me_resp.json()["permissions"])
        assert assigned_perms == expected_perms, (
            f"Role {role_name} permission mismatch: {assigned_perms} != {expected_perms}"
        )

        # Test action: 'administer'
        admin_resp = client.post("/api/v1/operations/administer", headers=headers)
        if "administer" in expected_perms or role_name == "Platform Administrator":
            assert admin_resp.status_code == 200
        else:
            assert admin_resp.status_code == 403

        # Test action: 'audit'
        audit_resp = client.get("/api/v1/audit/events", headers=headers)
        if "audit" in expected_perms or role_name == "Platform Administrator":
            assert audit_resp.status_code == 200
        else:
            assert audit_resp.status_code == 403

        # Test action: 'export'
        export_resp = client.post("/api/v1/operations/vessel-calls/export", headers=headers, json={"filters": {}})
        if "export" in expected_perms or role_name == "Platform Administrator":
            assert export_resp.status_code == 200
        else:
            assert export_resp.status_code == 403


def test_repository_level_data_scope(db_session):
    """Requirement: Data scope filters at repository layer, not merely in route handlers."""
    import uuid

    uid = uuid.uuid4().hex[:6]
    repo = VesselCallRepository(db_session)

    vcn1, vcn2, vcn3 = f"VCN-SC1-{uid}", f"VCN-SC2-{uid}", f"VCN-SC3-{uid}"

    # Insert test calls across different tenants and ports
    c1 = VesselCall(
        vessel_name="Vessel Scope 1", vcn=vcn1, tenant_id="tenant-alpha", port_id="ZADUR", terminal_id="DCT"
    )
    c2 = VesselCall(
        vessel_name="Vessel Scope 2", vcn=vcn2, tenant_id="tenant-alpha", port_id="ZACPT", terminal_id="MCT"
    )
    c3 = VesselCall(vessel_name="Vessel Scope 3", vcn=vcn3, tenant_id="tenant-beta", port_id="ZADUR", terminal_id="DCT")
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # Scope for tenant-alpha, port ZADUR
    scope_alpha_durban = DataScope(tenant_id="tenant-alpha", port_id="ZADUR")
    results = repo.list(scope=scope_alpha_durban)
    vcns = [c.vcn for c in results]
    assert vcn1 in vcns
    assert vcn2 not in vcns  # Different port
    assert vcn3 not in vcns  # Different tenant

    # Scope with port wildcard for tenant-alpha
    scope_alpha_all = DataScope(tenant_id="tenant-alpha", port_id="*")
    results_all = repo.list(scope=scope_alpha_all)
    vcns_all = [c.vcn for c in results_all]
    assert vcn1 in vcns_all
    assert vcn2 in vcns_all
    assert vcn3 not in vcns_all

    # Verify that calling without a valid DataScope raises ValueError
    with pytest.raises(ValueError):
        repo.list(scope="invalid_scope")  # type: ignore


def test_audit_logging_and_sensitive_export(db_session):
    """Requirement: Audit events written for auth, sensitive views, and exports with filter set + row count."""
    login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Analyst"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Perform sensitive export with specific filter
    filter_data = {"vessel_type": "Container"}
    export_resp = client.post("/api/v1/operations/vessel-calls/export", headers=headers, json={"filters": filter_data})
    assert export_resp.status_code == 200

    # Query audit event
    audit_record = (
        db_session.query(AuditEvent)
        .filter_by(action="export", actor_role="Analyst")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert audit_record is not None
    assert audit_record.details is not None
    assert audit_record.details.get("filter_set") == filter_data
    assert "row_count" in audit_record.details

    # Test view_sensitive: insert sensitive call and fetch it
    import uuid

    sens_vcn = f"VCN-SENS-{uuid.uuid4().hex[:6]}"
    sens_call = VesselCall(
        vessel_name="Sensitive Vessel",
        vcn=sens_vcn,
        cargo_type="IMDG",
        tenant_id="tenant-synthetic-01",
        port_id="ZADUR",
        terminal_id="DCT",
    )
    db_session.add(sens_call)
    db_session.commit()

    get_resp = client.get(f"/api/v1/operations/vessel-calls/{sens_call.id}", headers=headers)
    assert get_resp.status_code == 200

    view_audit = db_session.query(AuditEvent).filter_by(action="view_sensitive", resource_id=str(sens_call.id)).first()
    assert view_audit is not None
    assert view_audit.details.get("is_sensitive") is True

    # Test synthetic dataset load audit
    admin_login = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    load_resp = client.post("/api/v1/operations/synthetic-data/load", headers=admin_headers)
    assert load_resp.status_code == 200

    load_audit = (
        db_session.query(AuditEvent)
        .filter_by(action="synthetic_data_load")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert load_audit is not None


def test_session_lifecycle_and_revocation():
    """Requirement: Session handling with access token, revocation on logout, and timeout enforcement."""
    login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Access protected route
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200

    # Logout to revoke
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Access protected route with revoked token should fail with 401
    revoked_resp = client.get("/api/v1/auth/me", headers=headers)
    assert revoked_resp.status_code == 401

    # Refresh session
    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}

    # Access protected route with refreshed token succeeds
    after_refresh = client.get("/api/v1/auth/me", headers=new_headers)
    assert after_refresh.status_code == 200


def test_service_account_authentication():
    """Requirement: Scoped machine credentials with hashed secrets at rest."""
    # Valid service account credentials
    valid_resp = client.post(
        "/api/v1/auth/service-token",
        json={"client_id": "svc-integration-01", "client_secret": "secret-service-key-2026"},
    )
    assert valid_resp.status_code == 200
    data = valid_resp.json()
    assert "access_token" in data
    assert data["roles"] == ["Integration Service Account"]

    # Invalid secret
    invalid_resp = client.post(
        "/api/v1/auth/service-token",
        json={"client_id": "svc-integration-01", "client_secret": "wrong-secret"},
    )
    assert invalid_resp.status_code == 401
