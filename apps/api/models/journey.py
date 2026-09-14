from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import BaseModel

class JourneyTemplate(BaseModel):
    __tablename__ = 'journey_template'
    __table_args__ = {'schema': 'journey'}
    name = Column(String, nullable=False, unique=True)
    dag_definition = Column(JSON, nullable=False)

class JourneyStage(BaseModel):
    __tablename__ = 'journey_stage'
    __table_args__ = {'schema': 'journey'}
    template_id = Column(ForeignKey('journey.journey_template.id'), nullable=False)
    stage_name = Column(String, nullable=False)

class JourneyInstance(BaseModel):
    __tablename__ = 'journey_instance'
    __table_args__ = {'schema': 'journey'}
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    template_id = Column(ForeignKey('journey.journey_template.id'), nullable=False)
    status = Column(String, nullable=False)

class StageOccurrence(BaseModel):
    __tablename__ = 'stage_occurrence'
    __table_args__ = {'schema': 'journey'}
    journey_instance_id = Column(ForeignKey('journey.journey_instance.id'), nullable=False)
    stage_id = Column(ForeignKey('journey.journey_stage.id'), nullable=False)
    status = Column(String, nullable=False)

class Handover(BaseModel):
    __tablename__ = 'handover'
    __table_args__ = {'schema': 'journey'}
    from_stage_occurrence_id = Column(ForeignKey('journey.stage_occurrence.id'), nullable=False)
    to_stage_occurrence_id = Column(ForeignKey('journey.stage_occurrence.id'), nullable=False)
    status = Column(String, nullable=False)
