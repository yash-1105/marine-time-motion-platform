from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .base import BaseModel


class ReportTemplate(BaseModel):
    __tablename__ = "report_template"
    __table_args__ = {"schema": "analytics"}
    template_id = Column(String(100), nullable=False, unique=True)
    template_version = Column(String(30), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="IMPLEMENTED")  # IMPLEMENTED | DEFERRED
    section_definitions = Column(JSON, nullable=False)


class ReportRun(BaseModel):
    __tablename__ = "report_run"
    __table_args__ = {"schema": "analytics"}
    report_run_id = Column(String(100), nullable=False, unique=True)
    template_id = Column(String(100), nullable=False)
    template_version = Column(String(30), nullable=False)
    tenant_id = Column(String(100), nullable=False, index=True)
    port_id = Column(String(100), nullable=True)
    terminal_id = Column(String(100), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    filters = Column(JSON, nullable=False, default=dict)
    formats = Column(JSON, nullable=False)
    status = Column(String(30), nullable=False, default="QUEUED")
    progress = Column(Integer, nullable=False, default=0)
    requested_by = Column(String(255), nullable=True)
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)


class ReportArtifact(BaseModel):
    __tablename__ = "report_artifact"
    __table_args__ = {"schema": "analytics"}
    report_run_id = Column(ForeignKey("analytics.report_run.id", ondelete="CASCADE"), nullable=False)
    format = Column(String(10), nullable=False)
    storage_key = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    access_scope = Column(JSON, nullable=False, default=dict)


class ReportDelivery(BaseModel):
    __tablename__ = "report_delivery"
    __table_args__ = {"schema": "analytics"}
    report_run_id = Column(ForeignKey("analytics.report_run.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(30), nullable=False)  # EMAIL | IN_APP | DOCUMENT_REPOSITORY
    recipient = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="PENDING")
    attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class ReportSchedule(BaseModel):
    __tablename__ = "report_schedule"
    __table_args__ = {"schema": "analytics"}
    template_id = Column(String(100), nullable=False)
    tenant_id = Column(String(100), nullable=False)
    frequency = Column(String(30), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    filters = Column(JSON, nullable=False, default=dict)
    formats = Column(JSON, nullable=False)
    recipients = Column(JSON, nullable=False, default=list)
