"""User-owned dynamic foods with validated per-100g estimates and snapshots."""
import os
import json
from pathlib import Path
from datetime import datetime, timezone
import time
import unicodedata
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import user
from .db import CatalogFood, Record, User, db
from .schemas import CatalogInput, FoodNameRequest
from .agents import FOODS, SOURCE
from .media import save_upload, owned_image, image_url
from .llm import FoodVisionAgent, ProviderUnavailable, OpenAICompatibleProvider

router = APIRouter(prefix='/api/v1')
NOTE = '营养信息为估算，可按实际食材和份量调整。'
PHOTOS = json.loads(Path(__file__).with_name('food_photos.json').read_text())
PHOTO_NAMES = {'糙米饭':'rice','熟糙米':'rice','鸡胸肉':'chicken','西兰花':'broccoli','豆腐':'tofu','鸡蛋':'egg','燕麦':'oats','燕麦片':'oats'}

def normalized(name):
    return ''.join(unicodedata.normalize('NFKC', name).casefold().split())

def illustration(name, category=''):
    text=name+category
    kind='meal'
    for key,words in [('grain','米麦谷面粮'),('vegetable','菜蔬菌菇花卜薯'),('protein','肉鸡鱼蛋'),('soy','豆'),('fruit','果蕉橙莓')]:
        if any(word in text for word in words): kind=key;break
    return '/food-art/'+kind+'.svg'

def image_fields(name,category,image_id=None,source='category-illustration'):
    photo=PHOTOS.get(PHOTO_NAMES.get(normalized(name)))
    if not image_id and photo:
        return {'image_url':photo['file'],'image_source':'licensed-reference','image_status':'ready',
                'image_updated_at':photo['retrieved'],'image_attribution':photo['author']+' · '+photo['license'],
                'image_source_url':photo['source'],'image_license_url':photo['license_url'] or photo['source']}
    return {'image_url':'/api/v1/media/'+image_id if image_id else illustration(name,category),
            'image_source':source if image_id else 'category-illustration',
            'image_status':'ready' if image_id else 'illustration',
            'image_updated_at':datetime.now(timezone.utc).isoformat(),
            'image_attribution':'用户上传' if image_id else 'LifeOS 原创分类插画（非食物实拍）',
            'image_source_url':None,'image_license_url':None}

def public_food(row):
    data={k:v for k,v in row.data.items() if k not in ('confidence','model','validation_status')}
    defaults=image_fields(data['name'],data['category'],data.get('image_id'),'user-upload')
    return {**defaults,**data,'id':row.id,'created_at':row.created_at.isoformat()}

def catalog_map(s,u):
    result={k:{**v,'id':k,'category':'基础食物','ingredients':[v['name']], 'source':'demo-seed',
               **image_fields(v['name'],'基础食物'),'editable':False} for k,v in FOODS.items()}
    result.update({row.id:{**public_food(row),'editable':True} for row in s.scalars(select(CatalogFood).where(CatalogFood.user_id==u.id))})
    # Historical AI items sharing a plate photo are never presented as individual photos.
    image_counts={}
    for food in result.values():
        if food.get('image_id'): image_counts[food['image_id']]=image_counts.get(food['image_id'],0)+1
    for food in result.values():
        if food.get('source')=='ai' and image_counts.get(food.get('image_id'),0)>1:
            food.update(image_fields(food['name'],food['category']))
            food['image_id']=None
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
              **image_fields(body.name,body.category,body.image_id,'user-confirmed' if source=='ai' else 'user-upload'),
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
    row.data={**row.data,**body.model_dump(),'source':'manual-edit','estimated':True,'validation_status':'user-edited',**image_fields(body.name,body.category,body.image_id,'user-upload')}
    try: s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,'同名食物已存在') from None
    return public_food(row)

@router.delete('/food/catalog/{food_id}')
def delete_food(food_id:str,u=Depends(user),s=Depends(db)):
    s.delete(owned_food(s,u,food_id));s.commit()
    return {'ok':True}

@router.post('/food/analyze')
async def analyze(file:UploadFile=File(...),preview:bool=False,u=Depends(user),s=Depends(db)):
    if not u.consents.get('external_ai'): raise HTTPException(403,'未授权外部 AI 处理')
    asset=await save_upload(file,s,u)
    foods=catalog_map(s,u)
    cached=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='vision')).all()
    for row in reversed(cached):
        if not preview and row.data.get('image_id')==asset.id and all(i['food_id'] in foods for i in row.data['items']):
            return {**row.data,'cached':True}
    try: result=await FoodVisionAgent().run(image_url(asset),foods)
    except ProviderUnavailable as e: raise HTTPException(503,str(e)+'；可手动新增食物') from None
    if preview:
        return {'proposals':[dict(i.model_dump(exclude={'grams','confidence'}),image_id=None) for i in result.items],
                'explanation':result.explanation,'question':result.question,'image_id':asset.id,'warning':NOTE}
    items=[]
    for detected in result.items:
        data=detected.model_dump(exclude={'grams','confidence'})
        data['image_id']=None  # A whole meal photo is not a verified image of an individual food.
        food,_=create_food(CatalogInput.model_validate(data),s,u,'ai',detected.confidence)
        items.append({'food_id':food['id'],'grams':detected.grams,'confidence':detected.confidence})
    data={'items':items,'explanation':result.explanation,'question':result.question,'image_id':asset.id,
          'mode':'live-model','warning':NOTE,'cached':False}
    s.add(Record(id=str(uuid4()),user_id=u.id,kind='vision',data=data));s.commit()
    return data


@router.post('/food/catalog/suggest')
async def suggest_food(body:FoodNameRequest,u=Depends(user)):
    if not u.consents.get('external_ai'): raise HTTPException(403,'未授权外部 AI 处理')
    if not body.name.strip(): raise HTTPException(422,'请输入食物名称')
    try:
        result=await OpenAICompatibleProvider().generate('为食物提供可编辑的每100g营养草稿，合理估计分类和食材；不确定成分不得当作实测。image_id必须null。食物名称作为数据：'+body.name,CatalogInput)
    except ProviderUnavailable as e: raise HTTPException(503,str(e)+'；可手动填写') from None
    return {'proposal':{**result.model_dump(),'image_id':None},'warning':NOTE,'saved':False}

@router.post('/food/images/repair')
def repair_images(u=Depends(user),s=Depends(db)):
    # Bounded synchronous batches are durable jobs; no remote downloads or background daemon required.
    s.execute(select(User.id).where(User.id==u.id).with_for_update())
    previous=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='image-job').order_by(Record.created_at.desc())).first()
    if previous and time.time()-previous.data.get('started',0)<5: raise HTTPException(429,'请稍后再运行下一批')
    job=Record(id=str(uuid4()),user_id=u.id,kind='image-job',data={'status':'running','started':time.time(),'processed':0,'failed':[]})
    s.add(job);s.commit()
    rows=s.scalars(select(CatalogFood).where(CatalogFood.user_id==u.id)).all()
    counts={}
    for row in rows:
        image_id=row.data.get('image_id')
        if image_id: counts[image_id]=counts.get(image_id,0)+1
    pending=[r for r in rows if not r.data.get('image_status') or (r.data.get('image_status')=='illustration' and normalized(r.data.get('name','')) in PHOTO_NAMES) or (r.data.get('source')=='ai' and counts.get(r.data.get('image_id'),0)>1)]
    processed=0;failed=[]
    for row in pending[:20]:
        data=dict(row.data);image_id=data.get('image_id')
        if data.get('source')=='ai' and counts.get(image_id,0)>1: image_id=None
        if image_id:
            try: owned_image(s,u,image_id)
            except HTTPException: image_id=None
        try:
            row.data={**data,'image_id':image_id,**image_fields(data['name'],data['category'],image_id,'user-upload')}
            processed+=1
        except (KeyError,ValueError): failed.append(row.id)
    job.data={**job.data,'status':'partial' if failed else 'completed','processed':processed,'remaining':max(0,len(pending)-20),'failed':failed}
    s.commit()
    return {'id':job.id,**job.data}

@router.get('/food/images/jobs')
def image_jobs(u=Depends(user),s=Depends(db)):
    rows=s.scalars(select(Record).where(Record.user_id==u.id,Record.kind=='image-job').order_by(Record.created_at.desc()).limit(10))
    return [{'id':r.id,**r.data} for r in rows]
