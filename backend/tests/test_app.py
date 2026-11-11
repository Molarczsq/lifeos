import os
os.environ['DATABASE_URL']='sqlite://'
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import main
from app.db import Base, Session
from app.schemas import MealRequest, Metric
from app.agents import nutrition, NutritionPlannerAgent, safety
engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
main.engine=engine
Session.configure(bind=engine)
@pytest.fixture()
def c():
    Base.metadata.drop_all(engine);main.limits.clear()
    with TestClient(main.app) as c:
        r=c.post('/api/v1/auth/register',json={'email':'test@example.com','password':'secure-test-pass'})
        assert r.status_code==200
        yield c

def test_nutrition():
    assert nutrition([{'food_id':'chicken','grams':100}])['totals']['protein']==31

def test_allergen_and_budget():
    p=NutritionPlannerAgent()
    assert all(m['id']!='tofu' for m in p.run(MealRequest(allergens=['大豆']),[]))
    assert p.run(MealRequest(allergens=['未知过敏原']),[])==[]
    assert all(m['price']<=15 for m in p.run(MealRequest(budget=15),[]))
    assert p.run(MealRequest(budget=1),[])==[]

def test_food_crud_and_isolation(c):
    r=c.post('/api/v1/food/entries',json={'items':[{'food_id':'rice','grams':150}]})
    assert r.status_code==200
    rid=r.json()['id']
    assert len(c.get('/api/v1/food/entries').json())==1
    c.post('/api/v1/auth/register',json={'email':'other@example.com','password':'secure-test-pass'})
    assert c.get('/api/v1/food/entries').json()==[]
    assert c.delete('/api/v1/records/'+rid).status_code==404

def test_invalid_food(c):
    for item in [{'food_id':'rice','grams':-5},{'food_id':'invented','grams':50}]:
        assert c.post('/api/v1/food/entries',json={'items':[item]}).status_code==422

def test_consent_chat_and_delete(c):
    assert c.post('/api/v1/health/insights').status_code==403
    c.put('/api/v1/consents',json={'health':True})
    assert c.post('/api/v1/health/insights').status_code==200
    r=c.post('/api/v1/advisor/chat/stream',json={'message':'下一餐蔬菜怎么选'})
    assert 'text/event-stream' in r.headers['content-type']
    assert 'who-diversity' in r.text
    assert '"type": "done"' in r.text
    assert len(c.get('/api/v1/advisor/sessions').json())==1
    c.delete('/api/v1/data')
    assert c.get('/api/v1/data/export').json()['records']==[]
    assert c.post('/api/v1/health/insights').status_code==403

def test_import_atomic_duplicates(c):
    data='kind,value,unit,recorded_at\nsteps,6000,steps,2025-01-01T08:00:00Z\n'
    for count in [1,0]:
        r=c.post('/api/v1/health/import',files={'file':('sample.csv',data)})
        assert r.status_code==200 and r.json()['imported']==count
    bad=data+'sleep,99,hours,2025-01-02T08:00:00Z\n'
    assert c.post('/api/v1/health/import',files={'file':('bad.csv',bad)}).status_code==422
    assert len(c.get('/api/v1/health/metrics').json())==1

def test_csrf_auth_logout(c):
    assert c.post('/api/v1/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/api/v1/auth/logout').status_code==200
    assert c.get('/api/v1/food/entries').status_code==401

def test_safety(c):
    assert '急救' in safety('我现在胸痛')
    assert '药物' in safety('给我处方')
    r=c.post('/api/v1/advisor/chat/stream',json={'message':'呼吸困难'})
    assert '急救' in r.text

def test_no_key_vision(c):
    import io
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(20,20)).save(b,format='PNG')
    assert c.post('/api/v1/food/analyze',files={'file':('a.png',b.getvalue())}).status_code==403
    c.put('/api/v1/consents',json={'external_ai':True})
    assert c.post('/api/v1/food/analyze',files={'file':('a.png',b.getvalue())}).status_code==503

def test_feedback(c):
    c.post('/api/v1/meals/feedback',json={'meal_id':'green','action':'dislike'})
    meals=c.post('/api/v1/meals/recommend',json={}).json()['meals']
    assert all(m['id']!='green' for m in meals)

def test_consent_revisions_bound_chat_history(c, monkeypatch):
    captured=[]
    async def fake_plan(*args): return ['nutrition_search']
    async def fake_generate(self,prompt,schema,image=None):
        import json
        captured.append(json.loads(prompt))
        return schema(text='均衡饮食，注意食物多样性。')
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(main,'plan_tools',fake_plan)
    monkeypatch.setattr(main.OpenAICompatibleProvider,'generate',fake_generate)
    c.put('/api/v1/consents',json={'external_ai':True,'diet':True})
    for text in ['蔬菜','怎么做']:
        assert c.post('/api/v1/advisor/chat/stream',json={'message':text}).status_code==200
    assert len(captured[1]['history_same_consent_revision'])==1
    c.put('/api/v1/consents',json={'external_ai':True,'diet':False})
    c.post('/api/v1/advisor/chat/stream',json={'message':'继续'})
    assert captured[2]['history_same_consent_revision']==[]
    assert 'food_log' not in captured[2]['authorized_tool_results']

def test_counterfactual_and_mystery_rotation(c):
    payload={'items':[{'food_id':'rice','grams':100}]}
    assert c.post('/api/v1/meals/simulate',json=payload).status_code==403
    c.put('/api/v1/consents',json={'diet':True})
    result=c.post('/api/v1/meals/simulate',json=payload).json()
    assert result['after']['kcal']==123 and result['before']['kcal']==0
    assert c.get('/api/v1/food/entries').json()==[]
    first=c.post('/api/v1/meals/mystery-box',json={}).json()['meal']['id']
    second=c.post('/api/v1/meals/mystery-box',json={}).json()['meal']['id']
    assert first!=second
