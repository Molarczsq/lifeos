"""Conversation lifecycle. Existing chat records remain readable after migration."""
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .auth import user
from .db import Conversation, Record, db
from .schemas import ConversationInput

router=APIRouter(prefix='/api/v1/advisor')

def owned_conversation(s,u,cid):
    row=s.get(Conversation,cid)
    if not row or row.user_id!=u.id: raise HTTPException(404,'对话不存在')
    return row

def resolve_conversation(s,u,cid,title='快捷对话'):
    if cid: return owned_conversation(s,u,cid)
    # Stable per-user quick conversation preserves the original widget's multi-turn behavior.
    cid=str(uuid5(NAMESPACE_URL,'lifeos-quick:'+u.id))
    row=s.get(Conversation,cid)
    if not row:
        row=Conversation(id=cid,user_id=u.id,title='快捷对话')
        s.add(row);s.commit()
    return row

def public(row):
    return {'id':row.id,'title':row.title,'created_at':row.created_at.isoformat()}

@router.get('/conversations')
def conversations(q:str='',u=Depends(user),s=Depends(db)):
    rows=s.scalars(select(Conversation).where(Conversation.user_id==u.id).order_by(Conversation.created_at.desc())).all()
    return [public(row) for row in rows if q[:100].casefold() in row.title.casefold()]

@router.post('/conversations')
def new_conversation(body:ConversationInput,u=Depends(user),s=Depends(db)):
    row=Conversation(id=str(uuid4()),user_id=u.id,title=body.title.strip() or '新的对话')
    s.add(row);s.commit();return public(row)

@router.patch('/conversations/{cid}')
def rename(cid:str,body:ConversationInput,u=Depends(user),s=Depends(db)):
    row=owned_conversation(s,u,cid);row.title=body.title.strip() or '新的对话';s.commit();return public(row)

@router.get('/conversations/{cid}/messages')
def messages(cid:str,u=Depends(user),s=Depends(db)):
    owned_conversation(s,u,cid)
    return [{'id':r.id,**r.data} for r in s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='chat').order_by(Record.created_at)) if r.data.get('conversation_id')==cid]

@router.delete('/conversations/{cid}')
def remove(cid:str,u=Depends(user),s=Depends(db)):
    row=owned_conversation(s,u,cid)
    for record in s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='chat')):
        if record.data.get('conversation_id')==cid: s.delete(record)
    s.delete(row);s.commit();return {'ok':True}

@router.get('/suggestions')
def suggestions(page:str='',conversation_id:str|None=None,u=Depends(user),s=Depends(db)):
    questions=['你可以怎样帮助我？','怎样让一餐搭配更丰富？']
    if page in ('scan','catalog'): questions.insert(0,'这道菜需要补充哪些食材或份量信息？')
    if u.consents.get('diet'):
        today=datetime.now(timezone.utc).date().isoformat()
        rows=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='food')).all()
        if any(r.data.get('recorded_at','').startswith(today) for r in rows): questions.insert(0,'结合今天已记录的饮食，下一餐可以如何搭配？')
    if u.consents.get('health') and s.scalar(select(Record.id).where(Record.user_id==u.id,Record.kind=='metric').limit(1)):
        questions.insert(0,'根据最近活动记录，有什么容易坚持的小习惯？')
    if conversation_id:
        owned_conversation(s,u,conversation_id)
        if any(r.data.get('conversation_id')==conversation_id for r in s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='chat'))):
            questions.append('请把刚才的建议整理成一个可执行的小步骤。')
    return {'questions':questions[:5],'mode':'context-rules'}
