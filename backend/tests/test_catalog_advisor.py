import io
import json
from PIL import Image
from sqlalchemy import select
from app import main
from app.db import Session, CatalogFood, MediaAsset
from app.schemas import DynamicVision
from .helpers import register

FOOD={'name':'番茄牛肉汤','category':'汤羹','ingredients':['番茄','牛肉'],'kcal':72,'protein':6,'fat':3,'carbs':5}

def photo(color='red'):
    out=io.BytesIO();Image.new('RGB',(20,20),color).save(out,format='PNG');return out.getvalue()

def upload(c):
    r=c.post('/api/v1/media',files={'file':('meal.png',photo(),'image/png')})
    assert r.status_code==200
    return r.json()

def conversation(c,title='我的对话'):
    r=c.post('/api/v1/advisor/conversations',json={'title':title})
    assert r.status_code==200
    return r.json()['id']

def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]

def test_catalog_crud_dedup_and_snapshot(c):
    first=c.post('/api/v1/food/catalog',json=FOOD).json()
    assert first['created'] is True
    fid=first['food']['id']
    assert c.post('/api/v1/food/catalog',json={**FOOD,'name':' 番茄牛肉汤 '}).json()['created'] is False
    assert fid in c.get('/api/v1/food/catalog?q=牛肉').json()['foods']
    record=c.post('/api/v1/food/entries',json={'items':[{'food_id':fid,'grams':200}]}).json()
    assert record['totals']['kcal']==144
    assert record['food_names'][fid]==FOOD['name']
    assert c.put('/api/v1/food/catalog/'+fid,json={**FOOD,'kcal':80}).status_code==200
    assert c.delete('/api/v1/food/catalog/'+fid).status_code==200
    assert fid not in c.get('/api/v1/food/catalog').json()['foods']
    assert c.get('/api/v1/food/entries').json()[0]['totals']['kcal']==144
    assert c.post('/api/v1/food/entries',json={'items':[{'food_id':fid,'grams':20}]}).status_code==422

def test_food_image_validation_dedup_and_user_isolation(c):
    asset=upload(c)
    assert upload(c)['id']==asset['id']
    assert c.get(asset['url']).headers['content-type']=='image/jpeg'
    assert c.post('/api/v1/media',files={'file':('bad.png',b'bad','image/png')}).status_code==422
    assert c.post('/api/v1/media',files={'file':('bad.svg',b'<svg/>','image/svg+xml')}).status_code==415
    food=c.post('/api/v1/food/catalog',json={**FOOD,'image_id':asset['id']}).json()['food']
    register(c,'catalog_other')
    assert c.get(asset['url']).status_code==404
    assert food['id'] not in c.get('/api/v1/food/catalog').json()['foods']
    assert c.put('/api/v1/food/catalog/'+food['id'],json=FOOD).status_code==404
    assert c.post('/api/v1/food/catalog',json={**FOOD,'image_id':asset['id']}).status_code==404
    assert c.post('/api/v1/food/catalog',json={**FOOD,'image_id':'https://evil.example/a'}).status_code==404

def test_vision_adds_unknown_food_and_reuses_image(c,monkeypatch):
    calls=[]
    async def vision(self,image,catalog):
        calls.append(image)
        return DynamicVision(items=[{**FOOD,'grams':220,'confidence':.65}],explanation='看起来是一碗番茄牛肉汤。')
    monkeypatch.setattr('app.catalog.FoodVisionAgent.run',vision)
    r=c.post('/api/v1/food/analyze',files={'file':('meal.png',photo(),'image/png')})
    assert r.status_code==200
    data=r.json();fid=data['items'][0]['food_id']
    assert '置信度' not in data['warning']
    foods=c.get('/api/v1/food/catalog').json()['foods']
    assert foods[fid]['source']=='ai' and foods[fid]['image_url']
    assert 'confidence' not in foods[fid]
    with Session() as s:
        assert s.get(CatalogFood,fid).data['confidence']==.65
    again=c.post('/api/v1/food/analyze',files={'file':('meal.png',photo(),'image/png')}).json()
    assert again['cached'] and len(calls)==1
    assert again['items']==data['items']

def test_unclear_image_and_unavailable_model(c,monkeypatch):
    from app.llm import ProviderUnavailable
    async def unclear(*args): return DynamicVision(items=[],explanation='',question='可以告诉我主要食材和大约份量吗？')
    monkeypatch.setattr('app.catalog.FoodVisionAgent.run',unclear)
    response=c.post('/api/v1/food/analyze',files={'file':('a.png',photo(),'image/png')}).json()
    assert response['items']==[] and response['question']
    async def unavailable(*args): raise ProviderUnavailable('模型不可用')
    monkeypatch.setattr('app.catalog.FoodVisionAgent.run',unavailable)
    assert c.post('/api/v1/food/analyze',files={'file':('b.png',photo('blue'),'image/png')}).status_code==503
    with Session() as s: assert list(s.scalars(select(CatalogFood)))==[]

def test_catalog_edit_duplicate_and_bounds(c):
    a=c.post('/api/v1/food/catalog',json=FOOD).json()['food']['id']
    b=c.post('/api/v1/food/catalog',json={**FOOD,'name':'冬瓜汤'}).json()['food']['id']
    assert c.put('/api/v1/food/catalog/'+b,json=FOOD).status_code==409
    assert c.post('/api/v1/food/catalog',json={**FOOD,'kcal':-1}).status_code==422
    assert c.post('/api/v1/food/catalog',json={**FOOD,'name':'  '}).status_code==422
    assert c.get('/api/v1/food/catalog').json()['foods'][a]['name']==FOOD['name']

def test_conversation_sse_crud_and_isolation(c):
    cid=conversation(c)
    r=c.post('/api/v1/advisor/chat/stream',json={'message':'下一餐蔬菜怎么选','conversation_id':cid})
    frames=events(r)
    assert frames[0]=={'type':'session','id':cid}
    assert any(e['type']=='step' for e in frames)
    assert frames[-1]['type']=='done'
    rows=c.get(f'/api/v1/advisor/conversations/{cid}/messages').json()
    assert len(rows)==1
    other=conversation(c,'另一段对话')
    assert c.get(f'/api/v1/advisor/conversations/{other}/messages').json()==[]
    assert c.patch(f'/api/v1/advisor/conversations/{cid}',json={'title':'餐食计划'}).status_code==200
    assert len(c.get('/api/v1/advisor/conversations?q=餐食').json())==1
    register(c,'session_other')
    assert c.get(f'/api/v1/advisor/conversations/{cid}/messages').status_code==404
    assert c.post('/api/v1/advisor/chat/stream',json={'message':'你好','conversation_id':cid}).status_code==404
    assert c.delete(f'/api/v1/advisor/conversations/{cid}').status_code==404

def test_multi_turn_boundaries_regenerate_and_image(c,monkeypatch):
    prompts=[]
    async def planner(*args):return ['nutrition_search']
    async def generate(self,prompt,schema,image=None):
        prompts.append((json.loads(prompt),image));return schema(text='我是智膳，帮助你规划均衡饮食。')
    monkeypatch.setenv('LLM_API_KEY','test')
    monkeypatch.setattr(main,'plan_tools',planner)
    monkeypatch.setattr(main.OpenAICompatibleProvider,'generate',generate)
    cid=conversation(c);other=conversation(c,'独立对话');asset=upload(c)
    for message in ['你好','继续']:
        c.post('/api/v1/advisor/chat/stream',json={'message':message,'conversation_id':cid})
    assert len(prompts[-1][0]['history_same_consent_revision'])==1
    c.post('/api/v1/advisor/chat/stream',json={'message':'看图片','conversation_id':other,'image_id':asset['id']})
    assert prompts[-1][0]['history_same_consent_revision']==[] and prompts[-1][1].startswith('data:image/jpeg')
    last=c.get(f'/api/v1/advisor/conversations/{cid}/messages').json()[-1]
    c.post('/api/v1/advisor/chat/stream',json={'message':'继续','conversation_id':cid,'regenerate_id':last['id']})
    assert len(c.get(f'/api/v1/advisor/conversations/{cid}/messages').json())==2
    c.put('/api/v1/consents',json={})
    assert c.post('/api/v1/advisor/chat/stream',json={'message':'图片','conversation_id':other,'image_id':asset['id']}).status_code==403
    assert c.get('/api/v1/advisor/suggestions?conversation_id='+cid).status_code==200
    assert c.delete('/api/v1/advisor/conversations/'+cid).status_code==200
    assert c.get('/api/v1/advisor/conversations/'+cid+'/messages').status_code==404

def test_delete_data_clears_new_private_entities(c):
    upload(c);conversation(c);c.post('/api/v1/food/catalog',json=FOOD)
    export=c.get('/api/v1/data/export').json()
    assert export['conversations'] and len(export['catalog'])==7
    assert c.delete('/api/v1/data').status_code==200
    assert c.get('/api/v1/advisor/conversations').json()==[]
    assert len(c.get('/api/v1/food/catalog').json()['foods'])==6
    with Session() as s: assert not list(s.scalars(select(MediaAsset)))

def test_streamed_drafts_validate_before_storage(c,monkeypatch):
    async def planner(*args): return ['nutrition_search']
    async def stream(*args):
        yield {'type':'draft','text':'你好'}
        yield {'type':'validated','text':'你好，我是智膳。'}
    monkeypatch.setenv('LLM_API_KEY','test')
    monkeypatch.setattr(main,'plan_tools',planner)
    monkeypatch.setattr(main,'stream_answer',stream)
    cid=conversation(c)
    data=events(c.post('/api/v1/advisor/chat/stream',json={'message':'你好','stream':True,'conversation_id':cid}))
    assert any(e['type']=='draft' and e['text']=='你好' for e in data)
    assert data[-2]['mode']=='live-model'
    rows=c.get('/api/v1/advisor/conversations/'+cid+'/messages').json()
    assert rows[0]['text']=='你好，我是智膳。'
    from app.llm import ProviderUnavailable
    async def failed(*args):
        yield {'type':'draft','text':'未校验的片段'}
        raise ProviderUnavailable('broken stream')
    monkeypatch.setattr(main,'stream_answer',failed)
    data=events(c.post('/api/v1/advisor/chat/stream',json={'message':'继续','stream':True,'conversation_id':cid}))
    assert {'type':'draft','text':''} in data
    rows=c.get('/api/v1/advisor/conversations/'+cid+'/messages').json()
    assert rows[-1]['mode']=='fallback' and '未校验的片段' not in rows[-1]['text']

def test_safety_response_persists_in_selected_conversation(c):
    cid=conversation(c)
    c.post('/api/v1/advisor/chat/stream',json={'message':'我胸痛','conversation_id':cid,'stream':True})
    rows=c.get('/api/v1/advisor/conversations/'+cid+'/messages').json()
    assert rows[0]['mode']=='safety' and '急救' in rows[0]['text']

def test_legacy_chat_migration(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SQLSession
    from app.db import Base, User, Record, Conversation, initialize_schema
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    Base.metadata.create_all(engine)
    with SQLSession(engine) as s:
        s.add(User(id='owner',username='legacy',password='hash'))
        s.commit()
        s.add(Record(id='old-chat',user_id='owner',kind='chat',data={'question':'你好','text':'你好','mode':'rules'}));s.commit()
    initialize_schema(engine);initialize_schema(engine)
    with SQLSession(engine) as s:
        rows=list(s.scalars(select(Conversation)))
        assert len(rows)==1
        assert s.get(Record,'old-chat').data['conversation_id']==rows[0].id

def test_malformed_vision_output_is_not_persisted(c,monkeypatch):
    import httpx
    async def post(self,url,**kwargs):
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"items":[{"name":"未知菜"}],"explanation":""}'}}]},request=httpx.Request('POST',url))
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    assert c.post('/api/v1/food/analyze',files={'file':('meal.png',photo(),'image/png')}).status_code==503
    with Session() as s: assert list(s.scalars(select(CatalogFood)))==[]


def test_disconnected_request_does_not_save_partial_turn(c,monkeypatch):
    import asyncio
    from app.db import User,Record
    from app.schemas import Chat
    async def planner(*args):return ['nutrition_search']
    async def stream(*args):
        yield {'type':'draft','text':'临时草稿'}
        yield {'type':'validated','text':'完整回答'}
    class Disconnected:
        async def is_disconnected(self):return True
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(main,'plan_tools',planner)
    monkeypatch.setattr(main,'stream_answer',stream)
    cid=conversation(c)
    with Session() as s:
        u=s.scalar(select(User))
        async def run():
            return [e async for e in main.AdvisorOrchestrator().run(Chat(message='你好',stream=True,conversation_id=cid),u,s,Disconnected())]
        result=asyncio.run(run())
        assert not any(e['type']=='answer' for e in result)
        assert list(s.scalars(select(Record).where(Record.kind=='chat')))==[]
