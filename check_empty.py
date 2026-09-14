from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import ServiceRequest, Delay

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("Service Requests:", db.scalar(select(func.count(ServiceRequest.id))))
print("Delays:", db.scalar(select(func.count(Delay.id))))
