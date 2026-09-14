import hashlib
import os
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apps.api.main import settings
from apps.api.models import (
    EventDefinition,
    EventAlias,
    KPI,
    Role,
    Permission,
    RolePermission,
    User,
    UserRole,
    ServiceAccount,
)

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
session = Session()

ACTIONS = [
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
]


def load_yaml(filename):
    with open(os.path.join("config", filename), "r") as f:
        return yaml.safe_load(f)


def seed_events():
    data = load_yaml("events.yaml")
    for event_data in data.get("events", []):
        event = session.query(EventDefinition).filter_by(name=event_data["name"]).first()
        if not event:
            event = EventDefinition(
                name=event_data["name"],
                category=event_data.get("category"),
                description=event_data.get("description", ""),
            )
            session.add(event)
    session.commit()


def seed_aliases():
    data = load_yaml("aliases.yaml")
    for alias_data in data.get("aliases", []):
        event = session.query(EventDefinition).filter_by(name=alias_data["event_name"]).first()
        if event:
            alias = session.query(EventAlias).filter_by(alias=alias_data["alias"]).first()
            if not alias:
                alias = EventAlias(
                    event_definition_id=event.id,
                    alias=alias_data["alias"],
                    match_type=alias_data["match_type"],
                    confirmation_state="CONFIRMED",
                )
                session.add(alias)
    session.commit()


def seed_kpis():
    data = load_yaml("kpis.yaml")
    for kpi_data in data.get("kpis", []):
        kpi = session.query(KPI).filter_by(name=kpi_data["name"]).first()
        if not kpi:
            kpi = KPI(name=kpi_data["name"], description=kpi_data.get("description", ""))
            session.add(kpi)
    session.commit()


def seed_roles_and_permissions():
    # 1. Seed all permissions
    perm_map = {}
    for action in ACTIONS:
        perm = session.query(Permission).filter_by(action=action).first()
        if not perm:
            perm = Permission(action=action, description=f"Permission to perform {action} actions")
            session.add(perm)
            session.flush()
        perm_map[action] = perm

    # 2. Seed roles from config/roles.yaml
    data = load_yaml("roles.yaml")
    for rdata in data.get("roles", []):
        role = session.query(Role).filter_by(name=rdata["name"]).first()
        if not role:
            role = Role(name=rdata["name"], description=rdata.get("description", ""))
            session.add(role)
            session.flush()

        # Link permissions
        for perm_action in rdata.get("permissions", []):
            if perm_action in perm_map:
                perm_obj = perm_map[perm_action]
                rp = (
                    session.query(RolePermission)
                    .filter_by(role_id=role.id, permission_id=perm_obj.id)
                    .first()
                )
                if not rp:
                    rp = RolePermission(role_id=role.id, permission_id=perm_obj.id)
                    session.add(rp)
    session.commit()


def seed_users():
    data = load_yaml("roles.yaml")
    for rdata in data.get("roles", []):
        role_name = rdata["name"]
        role = session.query(Role).filter_by(name=role_name).first()
        if not role:
            continue

        prefix = role_name.lower().replace(" ", "_")
        email = f"{prefix}@port.local"
        user = session.query(User).filter_by(email=email).first()
        if not user:
            user = User(
                email=email,
                full_name=f"{role_name} User",
                tenant_id="tenant-synthetic-01",
                port_id="*" if "Administrator" in role_name or "Auditor" in role_name or "Executive" in role_name else "ZADUR",
                terminal_id="*" if "Administrator" in role_name else "DCT",
                is_active=True,
                is_synthetic=True,
            )
            session.add(user)
            session.flush()

            ur = session.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first()
            if not ur:
                ur = UserRole(user_id=user.id, role_id=role.id)
                session.add(ur)
    session.commit()


def seed_service_accounts():
    role = session.query(Role).filter_by(name="Integration Service Account").first()
    if not role:
        return

    client_id = "svc-integration-01"
    raw_secret = "secret-service-key-2026"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

    sa = session.query(ServiceAccount).filter_by(client_id=client_id).first()
    if not sa:
        sa = ServiceAccount(
            client_id=client_id,
            client_secret_hash=secret_hash,
            name="PMS Connector Service Account",
            role_id=role.id,
            tenant_id="tenant-synthetic-01",
            port_id="ZADUR",
            terminal_id="DCT",
            is_active=True,
        )
        session.add(sa)
    session.commit()


def main():
    print("Seeding events...")
    seed_events()
    print("Seeding aliases...")
    seed_aliases()
    print("Seeding KPIs...")
    seed_kpis()
    print("Seeding roles and permissions...")
    seed_roles_and_permissions()
    print("Seeding users...")
    seed_users()
    print("Seeding service accounts...")
    seed_service_accounts()
    print("Seed complete.")


if __name__ == "__main__":
    main()
