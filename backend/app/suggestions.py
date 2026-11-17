"""Explainable suggestions, permission-scoped and cached; never sends chat messages."""
import hashlib,json,os,time
from datetime import datetime,timezone,timedelta
from pydantic import Field,field_validator
from .schemas import Strict
from .ai_services import rows,revision,put,generate
from .agents import safety,review_answer
from fastapi import HTTPException

class Questions(Strict):
    questions:list[str]=Field(min_length=1,max_length=4)
    @field_validator('questions')
    @classmethod
    def valid(cls,values):
        if any(not q.strip() or len(q)>100 for q in values):raise ValueError('问题长度不合法')
        return [q.strip() for q in values]

async def suggest(page,cid,offset,u,s):
    rev=revision(s,u);hour=(datetime.now(timezone.utc)-timedelta(minutes=offset)).hour
    ctx={'page':page[:40],'hour':hour};result=[]
    def add(text,reason,kind='context'):result.append({'id':hashlib.sha256(text.encode()).hexdigest()[:12],'text':text,'reason':reason,'type':kind})
    if u.consents.get('diet'):
        now=(datetime.now(timezone.utc)-timedelta(minutes=offset)).date()
        meals=[]
        for r in rows(s,u,'food'):
            try:
                when=datetime.fromisoformat(r.data['recorded_at'].replace('Z','+00:00'))
                if (when-timedelta(minutes=offset)).date()==now:meals.append(r.data)
            except (KeyError,ValueError):continue
        if meals:ctx['meals']=meals[-5:];add('根据今天已记录的饮食，下一餐怎么搭配？','依据你已授权的今日饮食记录')
        prefs=rows(s,u,'preferences')
        if prefs and any(prefs[-1].data.values()):ctx['preferences']=prefs[-1].data;add('结合我已填写的饮食偏好，推荐一份简单的下一餐。','依据你已保存并授权的饮食偏好')
        vision=rows(s,u,'vision')
        if vision:ctx['last_scan']=vision[-1].data;add('最近识别的这一餐，还需要补充哪些食材或份量信息？','依据你已授权的最近识餐记录')
    if u.consents.get('health'):
        metrics=rows(s,u,'metric')
        if metrics:ctx['activity']=[r.data for r in metrics[-3:]];add('根据最近活动记录，有什么容易坚持的小习惯？','依据你已授权的身体活动记录')
    if cid:
        history=[r.data for r in rows(s,u,'chat') if r.data.get('conversation_id')==cid and r.data.get('consent_revision')==rev]
        if history:ctx['recent_topic']=history[-1]['question'][:300];add('请把刚才的建议整理成一个可执行的小步骤。','依据当前授权版本的本次对话')
    fingerprint=hashlib.sha256(json.dumps([ctx,rev,cid],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    cache=[r for r in rows(s,u,'suggestions') if r.data.get('fingerprint')==fingerprint and time.time()-r.data.get('time',0)<300]
    if cache:return cache[-1].data['result']
    if u.consents.get('external_ai') and os.getenv('LLM_API_KEY'):
        try:
            generated=await generate(json.dumps({'task':'为用户推荐最多4个可点击的问题，不发送消息。只依据context中实际存在的记录，不推测健康状态，不假装有未提供的信息。无个人资料时只给通用生活方式问题。','context':ctx},ensure_ascii=False),Questions,u,s)
            personal=any(k in ctx for k in ('meals','preferences','last_scan','activity','recent_topic'))
            for q in generated.questions:
                if not safety(q) and not review_answer(q):add(q,'AI 根据已授权上下文生成，供你选择' if personal else '通用建议：AI 提供的生活方式问题','ai' if personal else 'general')
        except HTTPException as e:
            if e.status_code not in (503,422):raise
    if page in ('scan','catalog'):add('如何补充食材和份量，让营养估算更有参考价值？','通用建议：与你当前页面相关','general')
    meal='早餐' if hour<10 else '午餐' if hour<15 else '晚餐'
    for q in [f'推荐一份简单的{meal}搭配。','我只有鸡蛋和西红柿，可以做什么？','怎样让一餐搭配更丰富？','你可以怎样帮助我？']:
        add(q,'通用建议：未据此分析个人健康状况','general')
    unique=list({x['text']:x for x in reversed(result)}.values())[::-1][:4]
    output={'suggestions':unique,'questions':[x['text'] for x in unique],'mode':'context-rules' if any(x['type']!='general' for x in unique) else 'general'}
    put(s,u,'suggestions',{'fingerprint':fingerprint,'time':time.time(),'result':output})
    return output
