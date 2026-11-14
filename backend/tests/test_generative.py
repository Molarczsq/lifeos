from app.ai_schemas import Recipe,ProfileDraft,Preferences,Advice,ToolMeal
from app.knowledge import search
from .helpers import register
from .test_catalog_advisor import FOOD,events
RECIPE={'name':'蔬菜汤','reason':'添加一种蔬菜，丰富下一餐。','items':[{**FOOD,'name':'冬瓜汤','grams':200}],'price_estimate':12,'steps':['煮熟食材'],'alternatives':['可换当季蔬菜']}
def fake_model(monkeypatch,recipe=RECIPE):
    async def generate(self,prompt,schema,image=None):
        if schema==Recipe:return Recipe.model_validate(recipe)
        if schema==ProfileDraft:return ProfileDraft(preferences=Preferences(allergens=['大豆'],goal='饮食多样'),question='平时有什么喜欢的食物？')
        if schema==Advice:return Advice(text='已记录一餐，下一餐可尝试不同蔬菜。',questions=['下一餐如何搭配？'])
        return schema(text='我是智膳AI，可以帮助规划饮食。')
    monkeypatch.setattr('app.llm.OpenAICompatibleProvider.generate',generate)

def test_profile_confirm_skip_and_isolation(c,monkeypatch):
    fake_model(monkeypatch)
    assert c.post('/api/v1/ai/profile/turn',json={'skip':True}).json()['skipped']
    draft=c.post('/api/v1/ai/profile/turn',json={'text':'我对大豆过敏'}).json()
    assert c.get('/api/v1/ai/preferences').json()['preferences']['allergens']==[]
    aid=draft['action']['id']
    assert c.post(f'/api/v1/ai/actions/{aid}/confirm').status_code==200
    assert c.get('/api/v1/ai/preferences').json()['preferences']['allergens']==['大豆']
    register(c,'another_ai')
    assert c.post(f'/api/v1/ai/actions/{aid}/confirm').status_code==404

def test_generated_plan_confirm_idempotent_and_context(c,monkeypatch):
    fake_model(monkeypatch)
    r=c.post('/api/v1/ai/plans',json={'request':'想吃汤','budget':15})
    assert r.status_code==200,r.text
    p=r.json();assert p['mode']=='live-model'
    assert c.get('/api/v1/food/entries').json()==[]
    aid=p['action']['id'];a=c.post(f'/api/v1/ai/actions/{aid}/confirm').json();b=c.post(f'/api/v1/ai/actions/{aid}/confirm').json()
    assert a==b and len(c.get('/api/v1/food/entries').json())==1
    assert c.get('/api/v1/ai/context').json()['day']['meals']==1
    assert c.post('/api/v1/ai/plans',json={'request':'换便宜些','previous_id':p['id']}).status_code==200

def test_restrictions_budget_and_revocation(c,monkeypatch):
    fake_model(monkeypatch)
    assert c.post('/api/v1/ai/plans',json={'budget':5}).status_code==422
    assert c.post('/api/v1/ai/plans',json={'restrictions':['冬瓜']}).status_code==422
    p=c.post('/api/v1/ai/plans',json={}).json();aid=p['action']['id']
    c.put('/api/v1/consents',json={'diet':False,'external_ai':True})
    assert c.post(f'/api/v1/ai/actions/{aid}/confirm').status_code==409
    assert c.get('/api/v1/ai/context').json()['day'] is None
    assert c.post('/api/v1/ai/profile/turn',json={'text':'过敏'}).status_code==403

def test_no_model_does_not_fake_plan(c):
    assert c.post('/api/v1/ai/plans',json={}).status_code==503
    frames=events(c.post('/api/v1/advisor/chat/stream',json={'message':'你好','agent_version':2}))
    assert next(e for e in frames if e['type']=='answer')['mode']=='unavailable'

def test_bm25_rank_and_source():
    docs=search('燕麦 全谷物 主食')
    assert docs[0]['id']=='who-grains'
    assert all(d['version'] and d['scope'] and d['url'].startswith('https://www.who.int/') for d in docs)
    assert search('zzzznohit')==[]

def test_agent_tools_propose_not_write(c,monkeypatch):
    fake_model(monkeypatch);monkeypatch.setenv('LLM_API_KEY','test')
    async def calls(*args):return [('add_meal',ToolMeal(items=[{'food_id':'rice','grams':100}]))]
    monkeypatch.setattr('app.ai_advisor.plan_calls',calls)
    frames=events(c.post('/api/v1/advisor/chat/stream',json={'message':'记100g米饭','agent_version':2}))
    answer=next(e for e in frames if e['type']=='answer')
    assert len(answer['actions'])==1 and not c.get('/api/v1/food/entries').json()
    aid=answer['actions'][0]['id'];assert c.post(f'/api/v1/ai/actions/{aid}/confirm').status_code==200

def test_proactive_cached_and_privacy(c,monkeypatch):
    fake_model(monkeypatch)
    assert c.post('/api/v1/ai/insights',json={}).json()['mode']=='empty'
    c.post('/api/v1/food/entries',json={'items':[{'food_id':'rice','grams':100}]})
    assert c.post('/api/v1/ai/insights',json={}).json()['mode']=='live-model'
    assert c.post('/api/v1/ai/insights',json={}).json()['cached']
    c.put('/api/v1/consents',json={'diet':False,'external_ai':True})
    assert c.post('/api/v1/ai/insights',json={}).status_code==403

def test_handoff_ownership_and_deleted_connections(c,monkeypatch):
    fake_model(monkeypatch)
    p=c.post('/api/v1/ai/plans',json={}).json()
    register(c,'handoff_other')
    assert c.post('/api/v1/advisor/chat/stream',json={'message':'解释','agent_version':2,'plan_id':p['id']}).status_code==404
    assert c.get('/api/v1/health/connections').status_code==404


def test_recipe_tool_and_revoked_plan_context(c,monkeypatch):
    from app.ai_schemas import PlanRequest
    fake_model(monkeypatch);monkeypatch.setenv('LLM_API_KEY','test')
    async def calls(*args):return [('plan_recipe',PlanRequest(request='蔬菜汤'))]
    monkeypatch.setattr('app.ai_advisor.plan_calls',calls)
    answer=next(e for e in events(c.post('/api/v1/advisor/chat/stream',json={'message':'帮我生成蔬菜汤菜谱','agent_version':2})) if e['type']=='answer')
    assert answer['actions'][0]['kind']=='recipe'
    assert c.get('/api/v1/food/entries').json()==[]
    p=c.post('/api/v1/ai/plans',json={}).json()
    c.put('/api/v1/consents',json={'diet':False,'external_ai':True})
    assert c.post('/api/v1/ai/plans',json={'previous_id':p['id']}).status_code==403
    c.put('/api/v1/consents',json={'diet':True,'external_ai':True})
    assert c.post('/api/v1/advisor/chat/stream',json={'message':'解释','agent_version':2,'plan_id':p['id']}).status_code==409

def test_v2_stream_and_two_round_food_lookup(c,monkeypatch):
    from app.ai_schemas import NameArgs
    monkeypatch.setenv('LLM_API_KEY','test')
    seen=[]
    async def calls(question,history,u,observations=None):
        seen.append(observations)
        if observations is None:return [('get_food_nutrition',NameArgs(name='糙米',prepare_meal=True))]
        assert observations['get_food_nutrition:0']['foods'][0]['id']=='rice'
        return [('add_meal',ToolMeal(items=[{'food_id':'rice','grams':100}]))]
    async def stream(*args):
        yield {'type':'draft','text':'请确认'}
        yield {'type':'final','text':'请确认这份餐食草稿后保存。'}
    monkeypatch.setattr('app.ai_advisor.plan_calls',calls)
    monkeypatch.setattr('app.ai_advisor.stream_answer',stream)
    frames=events(c.post('/api/v1/advisor/chat/stream',json={'message':'记100克糙米饭','agent_version':2,'stream':True}))
    assert len(seen)==2 and any(e['type']=='draft' for e in frames)
    assert next(e for e in frames if e['type']=='answer')['actions']
    assert not c.get('/api/v1/food/entries').json()
