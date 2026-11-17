"""Deterministic, versioned onboarding. Skips are null, never inferred answers."""
import re
from uuid import uuid5, NAMESPACE_URL
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from .db import Record
from .ai_schemas import Preferences

FIELDS=[('allergens','有哪些过敏食物？请用逗号分隔；明确没有可填写“无”，不确定可跳过。'),('avoid','有什么不想吃的食材？请用逗号分隔。'),('goal','你想怎样改善日常饮食？'),('habits','平时的用餐时间和习惯是怎样的？'),('likes','你喜欢哪些食物或口味？请用逗号分隔。')]

def state(s,u):
    if not u.consents.get('diet'):raise HTTPException(403,'请先开启饮食上下文授权')
    rid=str(uuid5(NAMESPACE_URL,'lifeos-onboarding:'+u.id))
    row=s.get(Record,rid)
    if not row:
        row=Record(id=rid,user_id=u.id,kind='onboarding',data={'index':0,'version':0,'answers':{},'saved':False,'last_request':None})
        s.add(row)
        try:s.commit()
        except IntegrityError:s.rollback();row=s.get(Record,rid)
    return row

def public(row):
    d=row.data;i=d['index'];complete=i>=len(FIELDS)
    return {**d,'status':'complete' if complete else 'asking','total':len(FIELDS),'field':None if complete else FIELDS[i][0],'question':'问题已完成，请核对并保存已填写的信息。' if complete else FIELDS[i][1],'fields':[{'key':k,'question':q} for k,q in FIELDS]}

def turn(body,s,u):
    row=state(s,u);old=row.data
    if body.request_id and body.request_id==old.get('last_request'):return public(row)
    if body.version!=old['version']:raise HTTPException(409,'建档进度已更新，请刷新进度后重试')
    d={**old,'answers':dict(old['answers']),'version':old['version']+1,'last_request':body.request_id,'saved':False};i=d['index']
    if body.event in ('ANSWER','SKIP'):
        if i>=len(FIELDS):raise HTTPException(409,'问题已结束，请选择修改或保存')
        text=body.text.strip()
        if body.event=='ANSWER' and not text:raise HTTPException(422,'请输入回答，或选择跳过')
        key=FIELDS[i][0]
        value=None if body.event=='SKIP' else text
        if value is not None and key in ('allergens','avoid','likes'):
            value=[] if value in ('无','没有','none','None') else list(dict.fromkeys(x.strip() for x in re.split('[,，、;；\n]',value) if x.strip()))
        if value is not None:
            try:Preferences.model_validate({key:value})
            except ValidationError:raise HTTPException(422,'回答格式或长度不正确，请简短填写，列表用逗号分隔') from None
        d['answers'][key]=value;d['index']=i+1
    elif body.event=='BACK':d['index']=max(0,i-1)
    elif body.event=='COMPLETE':
        if i<len(FIELDS):raise HTTPException(409,'请先完成或跳过剩余问题')
        parsed=Preferences.model_validate({k:v for k,v in d['answers'].items() if v is not None}).model_dump(exclude_unset=True)
        from uuid import uuid4
        s.add(Record(id=str(uuid4()),user_id=u.id,kind='preferences',data=parsed));d['saved']=True
    else:raise HTTPException(422,'不支持的建档事件')
    changed=s.execute(update(Record).where(Record.id==row.id,Record.data['version'].as_integer()==old['version']).values(data=d).execution_options(synchronize_session=False))
    if changed.rowcount!=1:s.rollback();raise HTTPException(409,'建档进度已更新，请刷新进度后重试')
    s.commit();s.refresh(row);return public(row)
