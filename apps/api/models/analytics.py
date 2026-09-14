from sqlalchemy import Column, Float, ForeignKey, String

from .base import BaseModel


class LeadTimeDefinition(BaseModel):
    __tablename__ = "lead_time_definition"
    __table_args__ = {"schema": "analytics"}
    name = Column(String, nullable=False, unique=True)
    start_event = Column(String, nullable=False)
    end_event = Column(String, nullable=False)


class LeadTimeResult(BaseModel):
    __tablename__ = "lead_time_result"
    __table_args__ = {"schema": "analytics"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    definition_id = Column(ForeignKey("analytics.lead_time_definition.id"), nullable=False)
    duration_hours = Column(Float, nullable=True)


class KPI(BaseModel):
    __tablename__ = "kpi"
    __table_args__ = {"schema": "analytics"}
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)


class KPIFormulaVersion(BaseModel):
    __tablename__ = "kpi_formula_version"
    __table_args__ = {"schema": "analytics"}
    kpi_id = Column(ForeignKey("analytics.kpi.id"), nullable=False)
    version = Column(String, nullable=False)
    expression = Column(String, nullable=False)


class KPIResult(BaseModel):
    __tablename__ = "kpi_result"
    __table_args__ = {"schema": "analytics"}
    kpi_id = Column(ForeignKey("analytics.kpi.id"), nullable=False)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=True)
    value = Column(Float, nullable=True)
    status = Column(String, nullable=False)  # OK|UNAVAILABLE|NO_SOURCE_DATA
