from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from .base import BaseModel

class CopilotConversation(BaseModel):
    __tablename__ = "copilot_conversation"; __table_args__ = {"schema": "analytics"}
    conversation_id = Column(String(100), nullable=False, unique=True); tenant_id = Column(String(100), nullable=False, index=True)
    port_id = Column(String(100)); terminal_id = Column(String(100)); owner_id = Column(String(100), nullable=False); title = Column(String(255))

class CopilotMessage(BaseModel):
    __tablename__ = "copilot_message"; __table_args__ = {"schema": "analytics"}
    conversation_id = Column(ForeignKey("analytics.copilot_conversation.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False); content = Column(Text, nullable=False); response_data = Column(JSON); tool_audit = Column(JSON)

class CopilotFeedback(BaseModel):
    __tablename__ = "copilot_feedback"; __table_args__ = {"schema": "analytics"}
    message_id = Column(ForeignKey("analytics.copilot_message.id", ondelete="CASCADE"), nullable=False); rating = Column(String(20), nullable=False); comment = Column(Text)
