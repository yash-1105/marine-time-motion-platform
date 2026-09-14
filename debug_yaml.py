from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall
from apps.api.services.quality.engine import DataQualityEngine

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

dq = DataQualityEngine(db)
print(dq.journey_templates)
