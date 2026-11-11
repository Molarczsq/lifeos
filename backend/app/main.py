import os, json, time, secrets, hashlib, hmac, base64, io, csv
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from PIL import Image
from .db import Base, engine, db, User, Record
from .schemas import Auth, Consent, Food, MealRequest, Metric, Chat, Answer, Feedback
from .agents import FOODS, SOURCE, nutrition, search, safety, NutritionPlannerAgent, HealthInsightAgent
from .llm import OpenAICompatibleProvider, FoodVisionAgent, ProviderUnavailable, plan_tools

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield
app=FastAPI(title='智膳 LifeOS',version='0.1.0',lifespan=lifespan)
P='/api/v1'
limits=defaultdict(deque)
@app.middleware('http')
async def guard(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin not in os.getenv('ALLOWED_ORIGINS','http://localhost:3000').split(','): return Response('Origin forbidden',403)
    if int(request.headers.get('content-length','0'))>6_000_000: return Response('Payload too large',413)
    key=request.client.host if request.client else 'local'
    now=time.monotonic(); q=limits[key]
    while q and q[0]<now-60: q.popleft()
    if len(q)>=180: return Response('Too many requests',429)
    q.append(now)
    result=await call_next(request)
    result.headers['Cache-Control']='no-store'
    result.headers['X-Content-Type-Options']='nosniff'
    return result

def digest(t): return hashlib.sha256(t.encode()).hexdigest()
def password(p,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def user(request:Request,s=Depends(db)):
    token=request.cookies.get('lifeos_session','')
    u=s.scalar(select(User).where(User.token_hash==digest(token))) if token else None
    if not u or u.token_expires<time.time(): raise HTTPException(401,'请登录')
    return u

def records(s,u,kind):
    return [{'id':r.id,**r.data} for r in s.scalars(select(Record).where(Record.user_id==u.id,Record.kind==kind).order_by(Record.created_at))]
def put(s,u,kind,data):
    r=Record(id=str(uuid4()),user_id=u.id,kind=kind,data=data);s.add(r);s.commit();return {'id':r.id,**data}
def require(u,scope):
    if not u.consents.get(scope): raise HTTPException(403,'未授权：'+scope)
@app.get(P+'/healthz')
def healthz(): return {'status':'ok','ai':'configured-unverified' if os.getenv('LLM_API_KEY') else 'rules','nutrition':'demo-estimates','retrieval':'lexical'}
@app.post(P+'/auth/register')
def register(body:Auth,response:Response,s=Depends(db)):
    email=body.email.lower()
    if s.scalar(select(User).where(User.email==email)): raise HTTPException(409,'邮箱已注册')
    u=User(id=str(uuid4()),email=email,password=password(body.password),consents={});s.add(u);s.commit()
    return login(body,response,s)
@app.post(P+'/auth/login')
def login(body:Auth,response:Response,s=Depends(db)):
    u=s.scalar(select(User).where(User.email==body.email.lower()))
    if not u or not hmac.compare_digest(u.password,password(body.password,u.password.split(':')[0])): raise HTTPException(401,'邮箱或密码不正确')
    token=secrets.token_urlsafe(32);u.token_hash=digest(token);u.token_expires=time.time()+86400;s.commit()
    response.set_cookie('lifeos_session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE','false')=='true',max_age=86400)
    return {'email':u.email,'consents':u.consents}
@app.post(P+'/auth/logout')
def logout(response:Response,u=Depends(user),s=Depends(db)):
    u=s.get(User,u.id);u.token_hash=None;s.commit();response.delete_cookie('lifeos_session');return {'ok':True}
@app.get(P+'/me')
def me(u=Depends(user)): return {'email':u.email,'consents':u.consents}
@app.put(P+'/consents')
def consents(body:Consent,u=Depends(user),s=Depends(db)):
    u=s.get(User,u.id);u.consents=body.model_dump();s.commit();put(s,u,'consent',{'scopes':u.consents});return u.consents
@app.get(P+'/food/catalog')
def catalog(u=Depends(user)): return {'foods':FOODS,'source':SOURCE}
@app.post(P+'/food/analyze')
async def analyze(file:UploadFile=File(...),u=Depends(user)):
    require(u,'external_ai')
    data=await file.read(5_000_001)
    if len(data)>5_000_000: raise HTTPException(413,'图片须小于5MB')
    try:
        im=Image.open(io.BytesIO(data));
        if im.width*im.height>20_000_000: raise ValueError('图片像素过大')
        im.verify()
        im=Image.open(io.BytesIO(data)); im.thumbnail((1200,1200)); out=io.BytesIO();im.convert('RGB').save(out,format='JPEG',quality=80)
    except Exception: raise HTTPException(422,'无法读取图片') from None
    try: result=await FoodVisionAgent().run('data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode(),FOODS)
    except ProviderUnavailable as e: raise HTTPException(503,str(e)+'；请手动选择食物与份量')
    if any(i.food_id not in FOODS for i in result.items): raise HTTPException(502,'模型返回未知食物，请手动输入')
    return {**result.model_dump(),'mode':'live-model','warning':'份量、油盐与隐藏成分无法准确测定；置信度未经校准，请人工修正。'}
@app.post(P+'/food/entries')
def add_food(body:Food,u=Depends(user),s=Depends(db)):
    if any(i.food_id not in FOODS for i in body.items): raise HTTPException(422,'未知食物')
    return put(s,u,'food',{**body.model_dump(mode='json'),**nutrition([i.model_dump() for i in body.items])})
@app.get(P+'/food/entries')
def foods(u=Depends(user),s=Depends(db)): return records(s,u,'food')
@app.delete(P+'/records/{record_id}')
def remove(record_id:str,u=Depends(user),s=Depends(db)):
    r=s.get(Record,record_id)
    if not r or r.user_id!=u.id: raise HTTPException(404,'记录不存在')
    s.delete(r);s.commit();return {'ok':True}
@app.post(P+'/meals/recommend')
def recommend(body:MealRequest,u=Depends(user),s=Depends(db)):
    return {'meals':NutritionPlannerAgent().run(body,records(s,u,'feedback'),records(s,u,'food')[-7:] if u.consents.get('diet') else None),'mode':'rules','note':'价格为演示估计；尚未根据个人疾病或医疗目标定制'}
@app.post(P+'/meals/mystery-box')
def mystery(body:MealRequest,u=Depends(user),s=Depends(db)):
    meals=NutritionPlannerAgent().run(body,records(s,u,'feedback'),records(s,u,'food')[-7:] if u.consents.get('diet') else None)
    past=records(s,u,'mystery')
    if len(meals)>1 and past and meals[0]['id']==past[-1]['meal_id']: meals=meals[1:]+meals[:1]
    if meals: put(s,u,'mystery',{'meal_id':meals[0]['id']})
    return {'meal':meals[0] if meals else None,'mode':'rules'}
@app.post(P+'/meals/feedback')
def feedback(body:Feedback,u=Depends(user),s=Depends(db)): return put(s,u,'feedback',body.model_dump())
@app.get(P+'/health/metrics')
def metrics(u=Depends(user),s=Depends(db)): return records(s,u,'metric')
def duplicate(rows,m): return any(all(r.get(k)==m.get(k) for k in ('kind','recorded_at','source')) for r in rows)
@app.post(P+'/health/metrics')
def metric(body:Metric,u=Depends(user),s=Depends(db)):
    data=body.model_dump(mode='json')
    if duplicate(records(s,u,'metric'),data): raise HTTPException(409,'重复采样时间和来源')
    return put(s,u,'metric',data)
@app.post(P+'/health/import')
async def import_metrics(file:UploadFile=File(...),u=Depends(user),s=Depends(db)):
    raw=await file.read(1_000_001)
    if len(raw)>1_000_000: raise HTTPException(413,'文件过大')
    try:
        content=raw.decode('utf-8-sig'); rows=json.loads(content) if (file.filename or '').endswith('.json') else list(csv.DictReader(io.StringIO(content)))
        if not isinstance(rows,list) or len(rows)>1000: raise ValueError('最多1000行')
        parsed=[Metric.model_validate({**r,'source':'import'}).model_dump(mode='json') for r in rows]
    except Exception: raise HTTPException(422,'导入失败；请检查类型、单位、时间和文件格式，未写入任何记录') from None
    existing=records(s,u,'metric'); count=0
    for m in parsed:
        if not duplicate(existing,m): s.add(Record(id=str(uuid4()),user_id=u.id,kind='metric',data=m));existing.append(m);count+=1
    s.commit();return {'imported':count,'duplicates':len(parsed)-count}
@app.get(P+'/health/connections')
def connections(u=Depends(user)):
    return [{'name':n,'status':'import-only','description':'尚未接入官方授权；请使用用户导出文件或手动录入'} for n in ['Apple HealthKit','Health Connect','微信运动','小米健康']]
@app.post(P+'/health/insights')
def insights(u=Depends(user),s=Depends(db)):
    require(u,'health');return HealthInsightAgent().run(records(s,u,'metric'))
@app.get(P+'/knowledge/search')
def knowledge(q:str='',u=Depends(user)): return {'documents':search(q[:2000]),'method':'lexical'}
@app.get(P+'/advisor/sessions')
def sessions(u=Depends(user),s=Depends(db)): return records(s,u,'chat')
class AdvisorOrchestrator:
    async def run(self,body,u,s):
        blocked=safety(body.message)
        if blocked: yield {'type':'answer','text':blocked,'mode':'safety','citations':[]};return
        yield {'type':'step','name':'权限检查完成'}
        allowed=['nutrition_search','meal_plan','mystery_box']
        if u.consents.get('diet'): allowed.append('food_log')
        if u.consents.get('health'): allowed.append('health_trends')
        selected=['nutrition_search']+[n for n in ('food_log','health_trends') if n in allowed]
        live=u.consents.get('external_ai') and os.getenv('LLM_API_KEY')
        if live:
            try:
                selected=await plan_tools(OpenAICompatibleProvider(),body.message,allowed)
                if 'nutrition_search' not in selected: selected.append('nutrition_search')
                yield {'type':'step','name':'模型 Function Calling 规划已校验'}
            except ProviderUnavailable:
                yield {'type':'step','name':'模型规划不可用，使用确定性工具路径'}
        context={};docs=[]
        for name in selected:
            if name=='food_log':
                require(u,'diet');context[name]=records(s,u,'food')[-14:]
            elif name=='health_trends':
                require(u,'health');context[name]=HealthInsightAgent().run(records(s,u,'metric')[-100:])
            elif name=='nutrition_search':
                docs=search(body.message);context[name]=docs
            else:
                req=MealRequest(mode='surprise' if name=='mystery_box' else 'healthy')
                candidates=NutritionPlannerAgent().run(req,records(s,u,'feedback'))
                context[name]={'assumptions':'默认预算30元；尚未提供过敏原，食用前必须核实', 'meals':candidates[:1] if name=='mystery_box' else candidates}
            yield {'type':'step','name':'已执行工具：'+name}
        revisions=records(s,u,'consent');revision=revisions[-1]['id'] if revisions else 'initial'
        history=[{'question':r['question'],'answer':r['text']} for r in records(s,u,'chat') if r.get('consent_revision')==revision][-6:]
        fallback='目前为规则模式。'+(' '.join(d['text'] for d in docs) or '你可以先记录一餐或一项活动，再观察连续多天的变化。')
        mode='rules'; answer=fallback
        if live:
            try:
                result=await OpenAICompatibleProvider().generate(json.dumps({'question':body.message,'history_same_consent_revision':history,'authorized_tool_results':context},ensure_ascii=False),Answer)
                answer=safety(result.text) or result.text;mode='live-model'
            except ProviderUnavailable: answer=fallback+' 模型暂时不可用，已降级。';mode='fallback'
        result={'text':answer,'mode':mode,'citations':docs}
        put(s,u,'chat',{'question':body.message,**result,'consent_revision':revision})
        yield {'type':'answer',**result}
@app.post(P+'/advisor/chat/stream')
async def chat(body:Chat,u=Depends(user),s=Depends(db)):
    async def events():
        async for event in AdvisorOrchestrator().run(body,u,s):
            yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
        yield 'data: '+json.dumps({'type':'done'})+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
@app.get(P+'/data/export')
def export(u=Depends(user),s=Depends(db)):
    return {'version':1,'consents':u.consents,'records':[{'id':r.id,'kind':r.kind,'data':r.data} for r in s.scalars(select(Record).where(Record.user_id==u.id))]}
@app.delete(P+'/data')
def erase(u=Depends(user),s=Depends(db)):
    s.execute(delete(Record).where(Record.user_id==u.id));u=s.get(User,u.id);u.consents={};s.commit();return {'ok':True}

@app.get(P+'/openapi.json',include_in_schema=False)
def versioned_openapi(): return app.openapi()

@app.post(P+'/meals/simulate')
def simulate(body:Food,u=Depends(user),s=Depends(db)):
    require(u,'diet')
    if any(i.food_id not in FOODS for i in body.items): raise HTTPException(422,'未知食物')
    current=records(s,u,'food')
    now=datetime.now(timezone.utc).date()
    today=[r for r in current if datetime.fromisoformat(r['recorded_at']).astimezone(timezone.utc).date()==now]
    before={k:round(sum(r['totals'][k] for r in today),1) for k in ['kcal','protein','fat','carbs']}
    added=nutrition([i.model_dump() for i in body.items])['totals']
    return {'before':before,'after':{k:round(before[k]+added[k],1) for k in before},'estimated':True,'day_boundary':'UTC','note':'仅为已记录饮食加本餐的估计，不代表医学预测或个人目标；不会保存餐食'}
