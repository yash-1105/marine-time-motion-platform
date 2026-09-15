from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.copilot import CopilotConversation, CopilotFeedback, CopilotMessage
from apps.api.services.audit import log_audit_event
from apps.api.services.copilot.service import CopilotService, tenant
router=APIRouter(prefix="/copilot",tags=["Copilot"])
class Ask(BaseModel): question:str=Field(min_length=1,max_length=4000); conversation_id:str|None=None
class Feedback(BaseModel): rating:str=Field(pattern="^(UP|DOWN)$"); comment:str|None=Field(None,max_length=1000)
@router.post("/ask")
def ask(body:Ask, request:Request, db:Session=Depends(get_db), principal:UserPrincipal=Depends(require("view","copilot"))):
 try: response,msg=CopilotService(db,principal).ask(body.question,body.conversation_id)
 except ValueError as e: raise HTTPException(400,str(e))
 log_audit_event(db,"copilot_request",principal.user_id,principal.email,",".join(principal.roles),"copilot_conversation",response["conversation_id"],correlation_id=getattr(request.state,"correlation_id",None),details={"scope":principal.data_scope.model_dump(),"provider":response["provider"],"tool":response["tool"],"evidence":response["evidence"],"response":response["answer"]})
 return response
@router.get("/conversations")
def conversations(db:Session=Depends(get_db),principal:UserPrincipal=Depends(require("view","copilot"))):
 rows=db.execute(select(CopilotConversation).where(CopilotConversation.tenant_id==tenant(principal),CopilotConversation.owner_id==principal.user_id).order_by(CopilotConversation.updated_at.desc())).scalars();return [{"conversation_id":x.conversation_id,"title":x.title,"created_at":x.created_at} for x in rows]
@router.post("/messages/{message_id}/feedback")
def feedback(message_id:str, body:Feedback,request:Request,db:Session=Depends(get_db),principal:UserPrincipal=Depends(require("view","copilot"))):
 msg=db.get(CopilotMessage,message_id)
 if not msg: raise HTTPException(404,"Message not found")
 f=CopilotFeedback(message_id=msg.id,rating=body.rating,comment=body.comment);db.add(f);db.commit();log_audit_event(db,"copilot_feedback",principal.user_id,principal.email,details={"message_id":message_id,"rating":body.rating});return {"status":"RECORDED"}
