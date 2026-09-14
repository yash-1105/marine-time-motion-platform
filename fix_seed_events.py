import polars as pl
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.config import EventDefinition

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

workbook = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
events = workbook["Events"]["Event_Name"].unique().to_list()

for e in events:
    if not db.execute(select(EventDefinition).where(EventDefinition.name == e)).scalar_one_or_none():
        new_def = EventDefinition(name=e, category="Generated")
        db.add(new_def)

db.commit()
print("Events seeded.")
