import os
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apps.api.main import settings
from apps.api.models import EventDefinition, EventAlias, KPI

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
session = Session()

def load_yaml(filename):
    with open(os.path.join('config', filename), 'r') as f:
        return yaml.safe_load(f)

def seed_events():
    data = load_yaml('events.yaml')
    for event_data in data.get('events', []):
        event = session.query(EventDefinition).filter_by(name=event_data['name']).first()
        if not event:
            event = EventDefinition(
                name=event_data['name'],
                category=event_data.get('category'),
                description=event_data.get('description', '')
            )
            session.add(event)
    session.commit()

def seed_aliases():
    data = load_yaml('aliases.yaml')
    for alias_data in data.get('aliases', []):
        event = session.query(EventDefinition).filter_by(name=alias_data['event_name']).first()
        if event:
            alias = session.query(EventAlias).filter_by(alias=alias_data['alias']).first()
            if not alias:
                alias = EventAlias(
                    event_definition_id=event.id,
                    alias=alias_data['alias'],
                    match_type=alias_data['match_type'],
                    confirmation_state='CONFIRMED'
                )
                session.add(alias)
    session.commit()

def seed_kpis():
    data = load_yaml('kpis.yaml')
    for kpi_data in data.get('kpis', []):
        kpi = session.query(KPI).filter_by(name=kpi_data['name']).first()
        if not kpi:
            kpi = KPI(
                name=kpi_data['name'],
                description=kpi_data.get('description', '')
            )
            session.add(kpi)
    session.commit()

def main():
    print("Seeding events...")
    seed_events()
    print("Seeding aliases...")
    seed_aliases()
    print("Seeding KPIs...")
    seed_kpis()
    print("Seed complete.")

if __name__ == "__main__":
    main()
