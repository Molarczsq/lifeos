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
    # Deterministic, consent-scoped guesses for what the user may want to ask.
    # These are context rules, never presented as model intent prediction.
    predicted=[];basis=[]
    if u.consents.get('diet'):
        today=datetime.now(timezone.utc).date().isoformat()
        rows=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='food')).all()
        if any(str(r.data.get('recorded_at') or r.created_at or '').startswith(today) for r in rows):
            predicted.append('结合今天已记录的饮食，下一餐可以如何搭配？');basis.append('今日饮食记录')
        elif rows:
            predicted.append('根据最近记录的饮食，下一餐可以怎么调整？');basis.append('近期饮食记录')
        else:
            predicted.append('我还没记录过一餐，怎么开始最省事？');basis.append('暂无饮食记录')
        pref=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='preferences').order_by(Record.created_at.desc())).first()
        if pref and any(pref.data.get(k) for k in ('allergens','avoid','likes','goal')):
            predicted.append('按我保存的饮食偏好，今天适合怎么吃？');basis.append('已保存的饮食偏好')
    else:
        predicted.append('开启饮食上下文授权后，能给我哪些更贴合的建议？');basis.append('未授权饮食上下文')
    if u.consents.get('health') and s.scalar(select(Record.id).where(Record.user_id==u.id,Record.kind=='metric').limit(1)):
        predicted.append('根据最近活动记录，有什么容易坚持的小习惯？');basis.append('身体活动记录')
    if page in ('scan','catalog'):
        predicted.insert(0,'这道菜需要补充哪些食材或份量信息？')
    elif page=='recipes':
        predicted.insert(0,'用手里的食材，十几分钟能做什么？')
    elif page=='plan':
        predicted.insert(0,'按我的预算和忌口，下一餐怎么安排？')
    questions=predicted+['你可以怎样帮助我？','怎样让一餐搭配更丰富？','如何建立规律的作息？']
    if conversation_id:
        owned_conversation(s,u,conversation_id)
        if any(r.data.get('conversation_id')==conversation_id for r in s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='chat'))):
            questions.append('请把刚才的建议整理成一个可执行的小步骤。')
    mode='context-rules'
    if u.consents.get('diet') and u.consents.get('external_ai'):
        from .ai_services import revision
        latest=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='ai-insight').order_by(Record.created_at.desc())).first()
        if latest and latest.data.get('revision')==revision(s,u):
            questions=latest.data.get('questions',[])+questions;mode='ai-and-context'
    return {'questions':list(dict.fromkeys(questions))[:5],'mode':mode,'predicted':bool(predicted),'basis':basis}

@router.post('/quick')
def quick(u=Depends(user),s=Depends(db)):
    return public(resolve_conversation(s,u,None))
