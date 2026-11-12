from sqlalchemy import select
from app.db import Session, CatalogFood, Record
from app.schemas import CatalogInput, DynamicVision
from .test_catalog_advisor import FOOD, upload, photo
from .helpers import register


def test_name_proposal_requires_consent_and_does_not_save(c,monkeypatch):
    async def generate(*args): return CatalogInput(**FOOD)
    monkeypatch.setattr('app.catalog.OpenAICompatibleProvider.generate',generate)
    result=c.post('/api/v1/food/catalog/suggest',json={'name':'番茄汤'})
    assert result.status_code==200 and result.json()['saved'] is False
    with Session() as s: assert not list(s.scalars(select(CatalogFood)))
    c.put('/api/v1/consents',json={'external_ai':False,'diet':False,'health':False})
    assert c.post('/api/v1/food/catalog/suggest',json={'name':'番茄汤'}).status_code==403


def test_plate_preview_is_not_a_catalog_photo(c,monkeypatch):
    async def vision(*args):
        return DynamicVision(items=[{**FOOD,'grams':100,'confidence':.7},{**FOOD,'name':'冬瓜','grams':100,'confidence':.6}],explanation='请确认食材')
    monkeypatch.setattr('app.catalog.FoodVisionAgent.run',vision)
    data=c.post('/api/v1/food/analyze?preview=true',files={'file':('meal.png',photo(),'image/png')}).json()
    assert len(data['proposals'])==2
    assert all(f['image_id'] is None for f in data['proposals'])
    with Session() as s: assert not list(s.scalars(select(CatalogFood)))
    for item in data['proposals']: assert c.post('/api/v1/food/catalog',json=item).status_code==200
    custom=[f for f in c.get('/api/v1/food/catalog').json()['foods'].values() if f['editable']]
    assert all(f['image_status']=='illustration' for f in custom)


def test_batch_repairs_legacy_duplicates_isolated_and_rate_limited(c):
    asset=upload(c)
    ids=[]
    for name in ['汤一','汤二']:
        food=c.post('/api/v1/food/catalog',json={**FOOD,'name':name,'image_id':asset['id']}).json()['food']
        ids.append(food['id'])
    with Session() as s:
        for fid in ids:
            row=s.get(CatalogFood,fid);row.data={k:v for k,v in row.data.items() if not k.startswith('image_')}
            row.data={**row.data,'source':'ai','image_id':asset['id']}
        s.commit()
    foods=c.get('/api/v1/food/catalog').json()['foods']
    assert all(foods[fid]['image_status']=='illustration' for fid in ids)
    job=c.post('/api/v1/food/images/repair').json()
    assert job['processed']==2 and job['status']=='completed'
    assert c.post('/api/v1/food/images/repair').status_code==429
    with Session() as s:
        assert all(s.get(CatalogFood,fid).data['image_id'] is None for fid in ids)
    assert c.get('/api/v1/food/images/jobs').json()[0]['id']==job['id']
    register(c,'image_other')
    assert c.get('/api/v1/food/images/jobs').json()==[]


def test_delete_image_resets_metadata(c):
    asset=upload(c)
    food=c.post('/api/v1/food/catalog',json={**FOOD,'image_id':asset['id']}).json()['food']
    assert food['image_status']=='ready'
    assert c.delete(asset['url']).status_code==200
    changed=c.get('/api/v1/food/catalog').json()['foods'][food['id']]
    assert changed['image_status']=='illustration' and changed['image_url'].endswith('.svg')


def test_curated_reference_photos_are_unique_valid_and_attributed(c):
    import hashlib
    from pathlib import Path
    from PIL import Image
    from app.catalog import PHOTOS
    root=Path(__file__).resolve().parents[2]/'frontend/public'
    hashes=set()
    for photo in PHOTOS.values():
        path=root/photo['file'].lstrip('/')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==photo['sha256']
        hashes.add(photo['sha256'])
        with Image.open(path) as image: image.verify()
        assert photo['source'].startswith('https://commons.wikimedia.org/')
        assert photo['license'] and photo['author']
    assert len(hashes)==6
    foods=c.get('/api/v1/food/catalog').json()['foods']
    assert all(food['image_source']=='licensed-reference' for food in foods.values())
    # Exact matching only: do not misrepresent a complex dish with an ingredient photo.
    f=c.post('/api/v1/food/catalog',json={**FOOD,'name':'西兰花奶油汤'}).json()['food']
    assert f['image_status']=='illustration'


def test_batch_failure_can_be_retried(c):
    fid=c.post('/api/v1/food/catalog',json=FOOD).json()['food']['id']
    with Session() as s:
        row=s.get(CatalogFood,fid);row.data={'name':FOOD['name']};s.commit()
    job=c.post('/api/v1/food/images/repair').json()
    assert job['status']=='partial' and job['failed']==[fid]
    with Session() as s:
        row=s.get(CatalogFood,fid);row.data=FOOD
        record=s.get(Record,job['id']);record.data={**record.data,'started':0};s.commit()
    retry=c.post('/api/v1/food/images/repair').json()
    assert retry['status']=='completed' and retry['processed']==1
