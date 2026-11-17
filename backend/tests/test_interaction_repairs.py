import json
from uuid import uuid4

def event(c,state,event,text='',rid=None):
    return c.post('/api/v1/ai/profile/turn',json={'event':event,'text':text,'version':state['version'],'request_id':rid or str(uuid4())})

def test_profile_skip_answer_restore_complete_edit(c):
    initial=c.get('/api/v1/ai/profile').json();assert initial['index']==0
    rid=str(uuid4());r=event(c,initial,'SKIP',rid=rid);assert r.status_code==200
    state=r.json();assert state['index']==1 and state['answers']['allergens'] is None
    assert event(c,initial,'SKIP',rid=rid).json()==state
    assert event(c,initial,'SKIP').status_code==409
    assert c.get('/api/v1/ai/profile').json()==state
    state=event(c,state,'ANSWER','香菜').json();state=event(c,state,'ANSWER','规律吃饭').json()
    for _ in range(2):state=event(c,state,'SKIP').json()
    assert state['status']=='complete' and state['index']==5
    state=event(c,state,'COMPLETE').json();assert state['saved']
    assert c.get('/api/v1/ai/preferences').json()['preferences']=={'avoid':['香菜'],'goal':'规律吃饭'}
    state=event(c,state,'BACK').json();assert state['field']=='likes'
    state=event(c,state,'ANSWER','西红柿, 鸡蛋').json()
    assert event(c,state,'COMPLETE').status_code==200
    assert c.get('/api/v1/ai/preferences').json()['preferences']['likes']==['西红柿','鸡蛋']

def test_profile_validation_does_not_advance_and_all_skips(c):
    state=c.get('/api/v1/ai/profile').json()
    assert event(c,state,'ANSWER',' ').status_code==422
    assert event(c,state,'ANSWER','a'*90).status_code==422
    assert c.get('/api/v1/ai/profile').json()==state
    for _ in range(5):state=event(c,state,'SKIP').json()
    assert set(state['answers'].values())=={None}
    assert event(c,state,'COMPLETE').status_code==200
    assert c.get('/api/v1/ai/preferences').json()['preferences']=={}
    c.put('/api/v1/consents',json={'diet':False,'health':False,'external_ai':False})
    assert c.get('/api/v1/ai/profile').status_code==403

def test_suggestions_permissions_and_context(c,monkeypatch):
    import app.suggestions as suggestions
    from datetime import datetime,timezone
    c.post('/api/v1/food/entries',json={'items':[{'food_id':'rice','grams':100}],'recorded_at':datetime.now(timezone.utc).isoformat()})
    d=c.get('/api/v1/advisor/suggestions?page=plan').json()
    assert d['suggestions'][0]['type']=='context'
    assert '今日饮食' in d['suggestions'][0]['reason']
    c.put('/api/v1/consents',json={'diet':False,'health':False,'external_ai':False})
    original=suggestions.rows
    def checked(s,u,kind):
        assert kind not in ('food','preferences','vision','metric')
        return original(s,u,kind)
    monkeypatch.setattr(suggestions,'rows',checked)
    d=c.get('/api/v1/advisor/suggestions').json()
    assert len(d['suggestions'])==4 and all(x['type']=='general' for x in d['suggestions'])
    assert c.get('/api/v1/advisor/suggestions?conversation_id=not-owned').status_code==404

def test_suggestions_model_cache_and_failure(c,monkeypatch):
    from app.llm import OpenAICompatibleProvider,ProviderUnavailable
    calls=[]
    async def fake(self,prompt,schema,image=None):calls.append(json.loads(prompt));return schema(questions=['怎么安排午餐？'])
    monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setattr(OpenAICompatibleProvider,'generate',fake)
    first=c.get('/api/v1/advisor/suggestions?page=plan').json()
    assert c.get('/api/v1/advisor/suggestions?page=plan').json()==first and len(calls)==1
    assert all(x['type']=='general' for x in first['suggestions'])
    async def fail(*args,**kw):raise ProviderUnavailable('unavailable')
    monkeypatch.setattr(OpenAICompatibleProvider,'generate',fail)
    assert c.get('/api/v1/advisor/suggestions?page=scan').status_code==200

def recipe_result(schema,name='番茄炒蛋'):
    return schema(recipes=[{'name':name,'minutes':15,'ingredients_text':'鸡蛋2个，番茄1个','steps':[{'title':'备料','detail':'切块','heat':'无'},{'title':'炒制','detail':'炒熟','heat':'中火'}],'nutrition':{'kcal':200,'protein':12,'fat':10,'carbs':18},'missing_ingredients':['盐'],'alternatives':['番茄可换成彩椒']}])

def test_custom_recipe_context_and_adjustment(c,monkeypatch):
    from app.recipes import OpenAICompatibleProvider
    prompts=[]
    async def fake(self,prompt,schema,image=None):prompts.append(json.loads(prompt));return recipe_result(schema)
    monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setattr(OpenAICompatibleProvider,'generate',fake)
    body={'pantry':[{'name':'鸡蛋','quantity':2,'unit':'个'},{'name':'egg'},{'name':'番茄'}],'equipment':['炒锅'],'difficulty':'easy','excluded':['花生'],'max_minutes':20}
    r=c.post('/api/v1/recipes/recommend',json=body);assert r.status_code==200,r.text
    d=r.json();sent=prompts[-1]['request']
    assert len(sent['available_ingredients'])==2 and sent['available_ingredients'][0]['quantity']==2
    assert sent['equipment']==['炒锅'] and sent['difficulty']=='easy' and '花生' in sent['banned']
    assert d['recipes'][0]['nutrition']['kcal']==200 and d['recipes'][0]['missing_ingredients']==['盐']
    body.update(previous_id=d['id'],adjustment='换个做法')
    assert c.post('/api/v1/recipes/recommend',json=body).status_code==200
    assert prompts[-1]['request']['previous_recipe'] and prompts[-1]['request']['adjustment']=='换个做法'
    assert c.get('/api/v1/food/entries').json()==[]
    body['previous_id']='another-user-id';assert c.post('/api/v1/recipes/recommend',json=body).status_code==404

def test_recipe_empty_single_and_exclusions(c,monkeypatch):
    from app.recipes import OpenAICompatibleProvider
    monkeypatch.setenv('LLM_API_KEY','test-only')
    assert c.post('/api/v1/recipes/recommend',json={}).status_code==422
    assert c.post('/api/v1/recipes/recommend',json={'pantry':[{'name':'  '}]}).status_code==422
    assert c.post('/api/v1/recipes/recommend',json={'pantry':[{'name':'egg'}],'excluded':['鸡蛋']}).status_code==422
    async def fake(self,prompt,schema,image=None):return recipe_result(schema,'花生番茄炒蛋')
    monkeypatch.setattr(OpenAICompatibleProvider,'generate',fake)
    assert c.post('/api/v1/recipes/recommend',json={'ingredients':['鸡蛋'],'excluded':['peanut']}).status_code==422
    async def ok(self,prompt,schema,image=None):return recipe_result(schema)
    monkeypatch.setattr(OpenAICompatibleProvider,'generate',ok)
    assert c.post('/api/v1/recipes/recommend',json={'pantry':[{'name':'鸡蛋'}]}).status_code==200
