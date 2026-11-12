"""User-owned dynamic foods with validated per-100g estimates and snapshots."""
import os
import unicodedata
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import user
from .db import CatalogFood, Record, db
from .schemas import CatalogInput
from .agents import FOODS, SOURCE
from .media import save_upload, owned_image, image_url
from .llm import FoodVisionAgent, ProviderUnavailable

router = APIRouter(prefix='/api/v1')
NOTE = '营养信息为估算，可按实际食材和份量调整。'

def normalized(name):
    return ''.join(unicodedata.normalize('NFKC', name).casefold().split())

def public_food(row):
    data={k:v for k,v in row.data.items() if k not in ('confidence','model','validation_status')}
    return {**data,'id':row.id,'created_at':row.created_at.isoformat(),
            'image_url':'/api/v1/media/'+data['image_id'] if data.get('image_id') else None}

def catalog_map(s,u):
    result={k:{**v,'id':k,'category':'基础食物','ingredients':[v['name']], 'source':'demo-seed',
               'image_url':None,'editable':False} for k,v in FOODS.items()}
    result.update({row.id:{**public_food(row),'editable':True} for row in s.scalars(select(CatalogFood).where(CatalogFood.user_id==u.id))})
    return result

def create_food(body,s,u,source='manual',confidence=None):
    if body.image_id: owned_image(s,u,body.image_id)
    name=normalized(body.name)
    existing=s.scalar(select(CatalogFood).where(CatalogFood.user_id==u.id, CatalogFood.normalized_name==name))
    if existing: return public_food(existing),False
    for key,value in FOODS.items():
        if normalized(value['name'])==name: return {**value,'id':key,'editable':False},False
    row=CatalogFood(id=str(uuid4()),user_id=u.id,normalized_name=name,
        data={**body.model_dump(),'source':source,'estimated':True,'confidence':confidence,
              'model':os.getenv('LLM_MODEL','') if source=='ai' else None,'validation_status':'schema-validated'})
    s.add(row)
    try: s.commit()
    except IntegrityError:
        s.rollback()
        row=s.scalar(select(CatalogFood).where(CatalogFood.user_id==u.id,CatalogFood.normalized_name==name))
        if not row: raise HTTPException(409,'食物名称冲突，请刷新后重试')
        return public_food(row),False
    return public_food(row),True

def owned_food(s,u,food_id):
    row=s.get(CatalogFood,food_id)
    if not row or row.user_id!=u.id: raise HTTPException(404,'自建食物不存在')
    return row

def estimate(items, catalog):
    if any(i['food_id'] not in catalog for i in items): raise HTTPException(422,'食物不存在，请刷新目录后重选')
    totals={k:round(sum(catalog[i['food_id']][k]*i['grams']/100 for i in items),1) for k in ('kcal','protein','fat','carbs')}
    return {'totals':totals,'kcal_range':[round(totals['kcal']*.75),round(totals['kcal']*1.3)],
            'source':{'label':NOTE,'verified':False},
            'food_names':{i['food_id']:catalog[i['food_id']]['name'] for i in items}}

@router.get('/food/catalog')
def list_foods(q:str='',u=Depends(user),s=Depends(db)):
    foods=catalog_map(s,u)
    return {'foods':{k:v for k,v in foods.items() if normalized(q[:100]) in normalized(v['name'])},'source':SOURCE}

@router.post('/food/catalog')
def add_food(body:CatalogInput,u=Depends(user),s=Depends(db)):
    food,created=create_food(body,s,u)
    return {'food':food,'created':created}

@router.put('/food/catalog/{food_id}')
def edit_food(food_id:str,body:CatalogInput,u=Depends(user),s=Depends(db)):
    row=owned_food(s,u,food_id)
    if body.image_id: owned_image(s,u,body.image_id)
    if any(normalized(v['name'])==normalized(body.name) for v in FOODS.values()): raise HTTPException(409,'与基础食物同名')
    row.normalized_name=normalized(body.name)
    row.data={**row.data,**body.model_dump(),'source':'manual-edit','estimated':True,'validation_status':'user-edited'}
    try: s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,'同名食物已存在') from None
    return public_food(row)

@router.delete('/food/catalog/{food_id}')
def delete_food(food_id:str,u=Depends(user),s=Depends(db)):
    s.delete(owned_food(s,u,food_id));s.commit()
    return {'ok':True}

@router.post('/food/analyze')
async def analyze(file:UploadFile=File(...),u=Depends(user),s=Depends(db)):
    if not u.consents.get('external_ai'): raise HTTPException(403,'未授权外部 AI 处理')
    asset=await save_upload(file,s,u)
    foods=catalog_map(s,u)
    cached=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='vision')).all()
    for row in reversed(cached):
        if row.data.get('image_id')==asset.id and all(i['food_id'] in foods for i in row.data['items']):
            return {**row.data,'cached':True}
    try: result=await FoodVisionAgent().run(image_url(asset),foods)
    except ProviderUnavailable as e: raise HTTPException(503,str(e)+'；可手动新增食物') from None
    items=[]
    for detected in result.items:
        data=detected.model_dump(exclude={'grams','confidence'})
        data['image_id']=asset.id  # Never trust image references produced by the model.
        food,_=create_food(CatalogInput.model_validate(data),s,u,'ai',detected.confidence)
        items.append({'food_id':food['id'],'grams':detected.grams,'confidence':detected.confidence})
    data={'items':items,'explanation':result.explanation,'question':result.question,'image_id':asset.id,
          'mode':'live-model','warning':NOTE,'cached':False}
    s.add(Record(id=str(uuid4()),user_id=u.id,kind='vision',data=data));s.commit()
    return data
