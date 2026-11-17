"""Conversation lifecycle. Existing chat records remain readable after migration."""
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException, Query
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
async def suggestions(page:str='',conversation_id:str|None=None,offset:int=Query(default=0,ge=-840,le=840),u=Depends(user),s=Depends(db)):
    if conversation_id:owned_conversation(s,u,conversation_id)
    from .suggestions import suggest
    return await suggest(page,conversation_id,offset,u,s)

@router.post('/quick')
def quick(u=Depends(user),s=Depends(db)):
    return public(resolve_conversation(s,u,None))
