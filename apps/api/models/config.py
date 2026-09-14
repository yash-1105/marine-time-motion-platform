from sqlalchemy import Column, ForeignKey, String, Integer, JSON

from .base import BaseModel


class EventDefinition(BaseModel):
    __tablename__ = "event_definition"
    __table_args__ = {"schema": "config"}
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=True)
    description = Column(String, nullable=True)


class EventAlias(BaseModel):
    __tablename__ = "event_alias"
    __table_args__ = {"schema": "config"}
    event_definition_id = Column(ForeignKey("config.event_definition.id"), nullable=False)
    alias = Column(String, nullable=False)
    match_type = Column(String, nullable=False)  # EXACT|CASE_INSENSITIVE|NORMALISED|REGEX|AI_SUGGESTED
    confirmation_state = Column(String, nullable=True)

class ImportTemplate(BaseModel):
    __tablename__ = "import_template"
    __table_args__ = {"schema": "config"}
    name = Column(String, nullable=False, unique=True)
    version = Column(Integer, default=1, nullable=False)
    file_format = Column(String, nullable=False)
    worksheet_name = Column(String, nullable=True)
    field_mappings = Column(JSON, nullable=False) # Maps source columns to canonical target paths
