"""Model-only cooking guide: unavailability, mocked generation and failure."""

def test_recipes_requires_model(c):
    r=c.post('/api/v1/recipes/recommend',json={'ingredients':['chicken','broccoli']})
    assert r.status_code==503
    assert 'AI 做菜服务暂不可用' in r.json()['detail']
    c.put('/api/v1/consents',json={'external_ai':True})
    # consent alone is not enough: no provider key is configured
    assert c.post('/api/v1/recipes/recommend',json={}).status_code==503

def test_recipes_generated_by_mock_model(c, monkeypatch):
    from app import recipes
    async def fake_generate(self,prompt,schema,image=None):
        return schema(recipes=[
            {'name':'蒜香鸡胸炒西兰花','minutes':15,'ingredients_text':'鸡胸肉 120g、西兰花 150g',
             'items':[{'food_id':'chicken','grams':120},{'food_id':'broccoli','grams':150},{'food_id':'invented-id','grams':50}],
             'steps':[{'title':'备料','detail':'切片','heat':'无需开火'},{'title':'炒制','detail':'下锅快炒','heat':'大火'}],
             'heat_tips':'大火快炒','note':'模拟输出'},
            {'name':'清炒时蔬','minutes':10,'ingredients_text':'西兰花 150g','items':[],
             'steps':[{'title':'焯水','detail':'水开下锅','heat':'大火'},{'title':'翻炒','detail':'快炒出锅','heat':'大火'}],
             'heat_tips':'快炒','note':''},
        ])
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(recipes.OpenAICompatibleProvider,'generate',fake_generate)
    c.put('/api/v1/consents',json={'external_ai':True})
    r=c.post('/api/v1/recipes/recommend',json={'ingredients':['chicken','broccoli'],'allergens':['花生']})
    assert r.status_code==200
    data=r.json()
    assert data['mode']=='live-model' and data['estimated'] is True
    assert len(data['recipes'])==2
    assert all(row['source']=='live-model' for row in data['recipes'])
    first=data['recipes'][0]
    assert first['name']=='蒜香鸡胸炒西兰花'
    assert {i['food_id'] for i in first['items']}=={'chicken','broccoli'}
    assert first['matched_ingredients']==2
    assert len(first['steps'])==2 and all(step['heat'] for step in first['steps'])
    assert '按实际食材核对' in data['note'] and '花生' in data['note']
    c.post('/api/v1/food/entries',json={'items':first['items'],'label':first['name']})
    assert c.get('/api/v1/food/entries').json()

def test_recipes_model_failure_is_explicit(c, monkeypatch):
    from app import recipes
    async def failing(self,prompt,schema,image=None):
        raise recipes.ProviderUnavailable('模拟模型不可用')
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(recipes.OpenAICompatibleProvider,'generate',failing)
    c.put('/api/v1/consents',json={'external_ai':True})
    r=c.post('/api/v1/recipes/recommend',json={'ingredients':['chicken']})
    assert r.status_code==503
    assert 'AI 模型不可用' in r.json()['detail']
