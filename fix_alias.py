from apps.api.models.config import EventAlias, EventDefinition
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import sys

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

aliases = db.execute(select(EventAlias)).scalars().all()
print("Aliases found:", len(aliases))

events = db.execute(select(EventDefinition)).scalars().all()
print("Events found:", len(events))
