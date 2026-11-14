"""User-scoped generation and confirm-before-write actions, built on existing Records."""
import os,json,time,hashlib
from uuid import uuid4
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .db import Record,User,db
from .auth import user
from .catalog import catalog_map,estimate,create_food
from .schemas import CatalogInput,Food
from .ai_schemas import Preferences,ProfileTurn,ProfileDraft,PlanRequest,Recipe,ProactiveRequest,Advice
from .llm import OpenAICompatibleProvider,ProviderUnavailable,USAGE_EVENTS
from .agents import safety,review_answer
from .knowledge import search
router=APIRouter(prefix='/api/v1/ai')
def rows(s,u,kind):
    return list(s.scalars(select(Record).where(Record.user_id==u.id,Record.kind==kind).order_by(Record.created_at)))
def put(s,u,kind,data):
    r=Record(id=str(uuid4()),user_id=u.id,kind=kind,data=data);s.add(r);s.commit();return r

def revision(s,u):
    r=rows(s,u,'consent');return r[-1].id if r else 'initial'
def require(u,scope):
    if not u.consents.get(scope): raise HTTPException(403,'需要授权：'+scope)
def preferences(s,u):
    require(u,'diet');r=rows(s,u,'preferences');data=dict(r[-1].data) if r else Preferences().model_dump()
    if not u.consents.get('health'):data['activity']=''
    return data
def context(s,u):
    data={'diet_authorized':bool(u.consents.get('diet'))}
    if u.consents.get('diet'):
        data['preferences']=preferences(s,u);data['recent_meals']=[r.data for r in rows(s,u,'food')[-14:]]
    if u.consents.get('health'): data['optional_activity_records']=[r.data for r in rows(s,u,'metric')[-10:]]
    return data

def day_structure(s,u):
    require(u,'diet');today=datetime.now(timezone.utc).date().isoformat()
    meals=[r.data for r in rows(s,u,'food') if r.data.get('recorded_at','').startswith(today)]
    return {'meals':len(meals),'totals':{k:round(sum(m['totals'][k] for m in meals),1) for k in ('kcal','protein','fat','carbs')},'food_names':list(dict.fromkeys(n for m in meals for n in m.get('food_names',{}).values())),'estimated':True,'day_boundary':'UTC'}

def proposal(s,u,kind,payload,session_id=None):
    r=put(s,u,'action',{'kind':kind,'payload':payload,'status':'pending','revision':revision(s,u),'expires':time.time()+3600,'conversation_id':session_id})
    return {'id':r.id,**r.data}

def owned(s,u,rid,kind):
    r=s.scalar(select(Record).where(Record.id==rid,Record.user_id==u.id,Record.kind==kind).with_for_update())
    if not r: raise HTTPException(404,'记录不存在')
    return r

def restrictions(s,u,extra=()):
    p=preferences(s,u) if u.consents.get('diet') else {}
    return list(dict.fromkeys(p.get('allergens',[])+p.get('avoid',[])+list(extra)))
ALIASES={'大豆':['豆腐','豆浆','酱油','soy'],'蛋':['鸡蛋','鸭蛋','egg'],'奶':['牛奶','奶酪','黄油','乳','milk'],'花生':['花生油','peanut'],'麸质':['小麦','面粉','面条','面包','gluten'],'鸡肉':['鸡胸','鸡腿']}
def check_restrictions(text,banned):
    text=text.lower()
    for item in banned:
        if item.lower() in text or any(a in text for a in ALIASES.get(item,[])):
            raise HTTPException(422,'生成结果包含已声明忌口或过敏原，请修改后重新生成；不能保证交叉接触安全')
async def generate(prompt,schema,u,s):
    require(u,'external_ai')
    events=[];token=USAGE_EVENTS.set(events);before=revision(s,u)
    try:
        result=await OpenAICompatibleProvider().generate(prompt,schema)
        if before!=revision(s,u):raise HTTPException(409,'授权已变更，请重新发起请求')
        return result
    except ProviderUnavailable as e: raise HTTPException(503,str(e)+'；未生成实时AI结果，可手动记录或稍后重试') from None
    finally:
        USAGE_EVENTS.reset(token)
        if events:put(s,u,'ai-usage',{'task':schema.__name__,'calls':events})

@router.get('/preferences')
def get_preferences(u=Depends(user),s=Depends(db)):
    r=rows(s,u,'preferences');return {'preferences':r[-1].data if r else Preferences().model_dump(),'authorized':bool(u.consents.get('diet'))}
@router.post('/profile/turn')
async def profile_turn(body:ProfileTurn,u=Depends(user),s=Depends(db)):
    require(u,'diet')
    if body.skip:return {'skipped':True,'question':'可以随时回来补充。先记录一餐，或告诉我下一餐的想法。','action':None}
    if safety(body.text):raise HTTPException(422,safety(body.text))
    p=preferences(s,u)
    result=await generate(json.dumps({'task':'对话式饮食建档：只提取用户明确说出的偏好，合并已有偏好；未知留空，不推测疾病。只追问一个最必要问题，先问过敏/忌口，再问目标和习惯。不要求年龄性别身体指标。', 'existing':p,'user':body.text},ensure_ascii=False),ProfileDraft,u,s)
    if result.preferences.activity and not u.consents.get('health'):raise HTTPException(403,'日常活动信息需要身体健康上下文授权')
    if review_answer(result.question+' '+json.dumps(result.preferences.model_dump(),ensure_ascii=False)):raise HTTPException(422,'请使用一般饮食偏好描述')
    return {'question':result.question,'action':proposal(s,u,'preferences',result.preferences.model_dump())}

@router.post('/plans')
async def plan(body:PlanRequest,u=Depends(user),s=Depends(db)):
    if safety(body.request):raise HTTPException(422,safety(body.request))
    previous=None
    if body.previous_id:
        require(u,'diet')
        previous=owned(s,u,body.previous_id,'plan').data
        if previous.get('revision')!=revision(s,u):raise HTTPException(409,'授权已变更，请重新规划')
    banned=restrictions(s,u,body.restrictions)
    result=await generate(json.dumps({'task':'生成一份下一餐方案，不使用固定食谱。items包含每100g估计营养、建议克数；所有数值是估计不是实测。必须排除banned，包括别名和调味料；不确定是否含过敏原时不要使用。按预算生成。给出步骤和替代方案。不得开药诊断。', 'request':body.model_dump(),'banned':banned,'context':context(s,u),'catalog':[f for f in catalog_map(s,u).values() if u.consents.get('diet') or not f.get('editable')][:60],'previous':previous,'evidence':search(body.request)},ensure_ascii=False),Recipe,u,s)
    catalog=catalog_map(s,u)
    for item in result.items:
        known=next((f for f in catalog.values() if f['name']==item.name and (u.consents.get('diet') or not f.get('editable'))),None)
        if known:
            for key in ('kcal','protein','fat','carbs'):setattr(item,key,known[key])
    payload=result.model_dump();check_restrictions(json.dumps(payload,ensure_ascii=False),banned)
    if result.price_estimate>body.budget:raise HTTPException(422,'生成方案超过预算，请重新规划')
    if review_answer(result.reason+' '.join(result.steps+result.alternatives)):raise HTTPException(422,'生成结果未通过安全审查')
    totals={k:round(sum(i[k]*i['grams']/100 for i in payload['items']),1) for k in ('kcal','protein','fat','carbs')}
    record=put(s,u,'plan',{'recipe':payload,'totals':totals,'mode':'live-model','estimated':True,'banned':banned,'revision':revision(s,u)})
    action=proposal(s,u,'recipe',{'recipe':payload,'banned':banned})
    return {'id':record.id,**record.data,'action':action,'citations':search(body.request)}

@router.get('/actions/{action_id}')
def get_action(action_id:str,u=Depends(user),s=Depends(db)):
    r=owned(s,u,action_id,'action');return {'id':r.id,**r.data}
@router.post('/actions/{action_id}/confirm')
def confirm(action_id:str,u=Depends(user),s=Depends(db)):
    s.execute(select(User.id).where(User.id==u.id).with_for_update())
    r=owned(s,u,action_id,'action');d=r.data
    if d['status']=='confirmed':return {'status':'confirmed','record_id':d.get('record_id')}
    if d['status']!='pending' or d['expires']<time.time():raise HTTPException(409,'操作已取消或过期，请重新生成')
    if d['revision']!=revision(s,u):raise HTTPException(409,'授权已变更，请重新生成操作')
    payload=d['payload'];kind=d['kind']
    if kind=='preferences':
        require(u,'diet');parsed=Preferences.model_validate(payload).model_dump();record=Record(id=str(uuid4()),user_id=u.id,kind='preferences',data=parsed)
    elif kind in ('meal','recipe'):
        require(u,'diet')
        if kind=='recipe':
            recipe=Recipe.model_validate(payload['recipe']);check_restrictions(json.dumps(recipe.model_dump(),ensure_ascii=False),restrictions(s,u,payload.get('banned',[])))
            items=[]
            for item in recipe.items:
                food=CatalogInput.model_validate(item.model_dump(exclude={'grams'})).model_copy(update={'image_id':None})
                # This is the explicit confirmation boundary. Catalog creation remains deduplicated.
                f,_=create_food(food,s,u,'ai-confirmed',commit=False);items.append({'food_id':f['id'],'grams':item.grams})
            parsed=Food(items=items,label=recipe.name)
        else:parsed=Food.model_validate(payload)
        foods=catalog_map(s,u);check_restrictions(' '.join(foods[i.food_id]['name']+' '.join(foods[i.food_id]['ingredients']) for i in parsed.items if i.food_id in foods),restrictions(s,u))
        data={**parsed.model_dump(mode='json'),**estimate([i.model_dump() for i in parsed.items],foods)}
        record=Record(id=str(uuid4()),user_id=u.id,kind='food',data=data)
    else:raise HTTPException(422,'不支持的操作')
    s.add(record);r.data={**d,'status':'confirmed','record_id':record.id};s.commit()
    return {'status':'confirmed','record_id':record.id}
@router.post('/actions/{action_id}/cancel')
def cancel(action_id:str,u=Depends(user),s=Depends(db)):
    r=owned(s,u,action_id,'action')
    if r.data['status']=='pending':r.data={**r.data,'status':'cancelled'};s.commit()
    return {'status':r.data['status']}

@router.get('/context')
def get_context(u=Depends(user),s=Depends(db)):
    return {'authorized':bool(u.consents.get('diet')),'day':day_structure(s,u) if u.consents.get('diet') else None}
@router.post('/insights')
async def insight(body:ProactiveRequest,u=Depends(user),s=Depends(db)):
    require(u,'diet');require(u,'external_ai')
    ctx=context(s,u);fingerprint=hashlib.sha256(json.dumps(ctx,sort_keys=True).encode()).hexdigest()
    recent=[r for r in rows(s,u,'ai-insight') if r.data.get('revision')==revision(s,u)]
    if recent and recent[-1].data.get('fingerprint')==fingerprint and time.time()-recent[-1].data['time']<1800:return {**recent[-1].data,'cached':True}
    if recent and time.time()-recent[-1].data['time']<30:return {**recent[-1].data,'cached':True,'cooldown':True}
    docs=search('饮食 下一餐 多样 蔬菜')
    if not ctx.get('recent_meals'):return {'mode':'empty','text':'先确认并记录一餐，再生成有依据的今日饮食摘要。','questions':['我可以怎样记录第一餐？'],'citations':[]}
    result=await generate(json.dumps({'task':'基于已记录饮食生成简短摘要和下一餐行动，先结论再依据，不把缺少记录说成没有进食，不诊断营养缺乏，最多三个后续问题。','context':ctx,'event':body.event,'evidence':docs},ensure_ascii=False),Advice,u,s)
    blocked=review_answer(result.text)
    if blocked:raise HTTPException(422,blocked)
    data={**result.model_dump(),'mode':'live-model','fingerprint':fingerprint,'time':time.time(),'revision':revision(s,u),'citations':docs}
    put(s,u,'ai-insight',data);return data

@router.get('/usage')
def usage(u=Depends(user),s=Depends(db)):
    calls=[c for r in rows(s,u,'ai-usage') for c in r.data['calls']]
    return {'calls':len(calls),'known_prompt_tokens':sum(c.get('prompt_tokens') or 0 for c in calls),'known_completion_tokens':sum(c.get('completion_tokens') or 0 for c in calls),'unknown_usage_calls':sum(c.get('prompt_tokens') is None for c in calls),'estimated_cost_usd':round(sum(c['estimated_cost_usd'] for c in calls if c.get('estimated_cost_usd') is not None),8) if any(c.get('estimated_cost_usd') is not None for c in calls) else None}
